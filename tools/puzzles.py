"""Personalised tactics trainer — the free replacement for Diamond puzzles.

Two decks, both drilled from the terminal:

  own      — your actual blunders from data/blunders.json, replayed as puzzles
  lichess  — puzzles from the CC0 Lichess database, filtered to the rating band
             and the tactical motifs that your own blunders say you miss

The motif profile is derived by replaying each blunder and asking what the
opponent could have done to you: mate, a hanging piece, a fork, a pin, a
skewer. That is a measurement of your weaknesses, not a guess.

Usage:
  python tools/puzzles.py profile              weakness profile -> reports/puzzles.md
  python tools/puzzles.py fetch [--min 1300] [--max 1800] [--per-theme 150]
                                               stream the Lichess DB -> data/puzzle_deck.json
  python tools/puzzles.py drill [n] [--deck own|lichess|mixed]
                                               train in the terminal
  python tools/puzzles.py export               data/own_blunders.pgn for a Lichess study

`fetch` streams 304MB and never writes it to disk (this folder is synced).
Requires python-chess and zstandard (`python -m pip install zstandard`).
"""

import csv
import io
import json
import random
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
BLUNDERS = ROOT / "data" / "blunders.json"
DECK = ROOT / "data" / "puzzle_deck.json"
DRILL_LOG = ROOT / "data" / "drill_log.json"
PUZZLE_DB = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
HEADERS = {"User-Agent": "chess-improvement-toolkit (jdardash@ucsc.edu)"}

PIECE_CP = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 320,
            chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 10000}
DIAGONALS = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
ORTHOGONALS = [(1, 0), (-1, 0), (0, 1), (0, -1)]
DIRECTIONS = {chess.BISHOP: DIAGONALS, chess.ROOK: ORTHOGONALS,
              chess.QUEEN: DIAGONALS + ORTHOGONALS}

# Motifs we can detect locally -> the Lichess theme tags to drill them with.
THEME_MAP = {
    "mate": ["mateIn1", "mateIn2", "backRankMate", "mate"],
    "hangingPiece": ["hangingPiece", "capturingDefender"],
    "fork": ["fork", "doubleCheck"],
    "pin": ["pin"],
    "skewer": ["skewer", "xRayAttack"],
    "opening": ["opening"],
    "middlegame": ["middlegame"],
    "endgame": ["endgame", "rookEndgame", "pawnEndgame", "queenEndgame"],
}


# ---------------------------------------------------------------- motifs

def see(board: chess.Board, square: int) -> int:
    """Material the side to move wins by capturing on `square` (centipawns)."""
    victim = board.piece_at(square)
    if victim is None:
        return 0
    caps = [m for m in board.legal_moves
            if m.to_square == square and board.is_capture(m)]
    if not caps:
        return 0
    cheapest = min(caps, key=lambda m: PIECE_CP[board.piece_at(m.from_square).piece_type])
    board.push(cheapest)
    gain = PIECE_CP[victim.piece_type] - see(board, square)
    board.pop()
    return max(0, gain)


def forked_targets(board: chess.Board, by_square: int,
                   victim_colour: chess.Color) -> int:
    """Pieces of victim_colour that the piece on by_square actually wins:
    dearer than the attacker, or undefended. Merely being attacked does not
    count, or every developing move looks like a fork."""
    attacker = board.piece_at(by_square)
    if attacker is None:
        return 0
    attacker_cp = PIECE_CP[attacker.piece_type]
    n = 0
    for sq in board.attacks(by_square):
        p = board.piece_at(sq)
        if not p or p.color != victim_colour:
            continue
        if PIECE_CP[p.piece_type] >= 300 and (
                PIECE_CP[p.piece_type] > attacker_cp
                or not board.attackers(victim_colour, sq)):
            n += 1
    return n


def line_motif(board: chess.Board, slider_sq: int,
               victim_colour: chess.Color) -> str | None:
    """Pin or skewer from a slider: the first two pieces along one ray both
    belong to the victim. Cheap piece in front of a dearer one is a pin; dearer
    in front is a skewer."""
    piece = board.piece_at(slider_sq)
    if piece is None or piece.piece_type not in DIRECTIONS:
        return None
    f0, r0 = chess.square_file(slider_sq), chess.square_rank(slider_sq)
    for df, dr in DIRECTIONS[piece.piece_type]:
        found = []
        f, r = f0 + df, r0 + dr
        while 0 <= f < 8 and 0 <= r < 8 and len(found) < 2:
            p = board.piece_at(chess.square(f, r))
            if p:
                found.append(p)
            f, r = f + df, r + dr
        if len(found) < 2 or any(p.color != victim_colour for p in found):
            continue
        v1, v2 = PIECE_CP[found[0].piece_type], PIECE_CP[found[1].piece_type]
        # Only count lines that cost real material: a minor or better skewered
        # against a rook, queen or king. Pawn-in-front-of-knight is not a motif
        # worth drilling.
        if v2 >= 500 and v1 >= 300 and v2 > v1:
            return "pin"
        if v1 >= 500 and 300 <= v2 < v1:
            return "skewer"
    return None


def motifs_of(blunder: dict) -> list[str]:
    """Replay one blunder and name what the opponent was handed."""
    tags = set()
    try:
        board = chess.Board(blunder["fen"])
        board.push_san(blunder["played"])
    except (ValueError, KeyError):
        return []

    me = not board.turn  # I just moved; opponent is to move
    for reply in board.legal_moves:
        board.push(reply)
        if board.is_checkmate():
            tags.add("mate")
        board.pop()
        if "mate" in tags:
            break

    # Material simply left on the board for them.
    for sq, piece in board.piece_map().items():
        if piece.color == me and see(board, sq) >= 200:
            tags.add("hangingPiece")
            break

    for reply in board.legal_moves:
        if board.is_capture(reply):
            continue
        board.push(reply)
        # Only credit a motif if the piece creating it is safe there — a fork
        # I can simply capture is not a tactic I fell for.
        if see(board, reply.to_square) == 0:
            if forked_targets(board, reply.to_square, me) >= 2:
                tags.add("fork")
            motif = line_motif(board, reply.to_square, me)
            if motif:
                tags.add(motif)
        board.pop()
        if {"fork", "pin", "skewer"} <= tags:
            break

    tags.add(blunder.get("phase", "middlegame"))
    return sorted(tags)


def build_profile() -> dict:
    if not BLUNDERS.exists():
        sys.exit("No data/blunders.json — run tools/engine_review.py first.")
    blunders = json.loads(BLUNDERS.read_text(encoding="utf-8"))
    counts = Counter()
    fast = Counter()
    for b in blunders:
        tags = motifs_of(b)
        b["motifs"] = tags
        counts.update(tags)
        if (b.get("think_seconds") or 99) < 5:
            fast.update(tags)
    # Persist the tags so the drill deck can group your own blunders by motif.
    BLUNDERS.write_text(json.dumps(blunders, indent=1), encoding="utf-8")
    return {"n_blunders": len(blunders), "motifs": counts,
            "motifs_when_rushed": fast, "blunders": blunders}


def cmd_profile() -> None:
    prof = build_profile()
    counts, n = prof["motifs"], prof["n_blunders"]
    lines = [
        "# Tactics profile — built from your own blunders",
        f"Generated {datetime.now(timezone.utc).date()} from {n} blunders in "
        "data/blunders.json.",
        "",
        "Each blunder was replayed to ask what the opponent was handed. A "
        "blunder can carry several tags.",
        "",
        "## What your blunders give away",
        "",
        "| Motif | Blunders | Share | Of those, played in under 5s |",
        "| --- | --- | --- | --- |",
    ]
    for motif, c in counts.most_common():
        rushed = prof["motifs_when_rushed"][motif]
        lines.append(f"| {motif} | {c} | {100 * c / max(1, n):.0f}% | "
                     f"{rushed} ({100 * rushed / max(1, c):.0f}%) |")

    tactical = [m for m, _ in counts.most_common()
                if m in ("mate", "hangingPiece", "fork", "pin", "skewer")]
    themes = sorted({t for m in tactical[:4] for t in THEME_MAP[m]})
    lines += [
        "",
        "## Drill set this implies",
        "",
        f"Top motifs: {', '.join(tactical[:4]) or 'none detected'}.",
        f"Lichess themes to filter on: `{','.join(themes)}`",
        "",
        "```",
        "python tools/puzzles.py fetch",
        "python tools/puzzles.py drill 20",
        "```",
        "",
        "Read the rushed column before the volume column. A motif you only miss "
        "when moving in under five seconds is a discipline problem, and more "
        "puzzles will not fix it.",
    ]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "puzzles.md").write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data" / "tactics_profile.json").write_text(
        json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "n_blunders": n, "motifs": dict(counts),
                    "motifs_when_rushed": dict(prof["motifs_when_rushed"]),
                    "themes": themes}, indent=1), encoding="utf-8")
    print("\n".join(lines))


# ---------------------------------------------------------------- fetch

def cmd_fetch(argv: list[str]) -> None:
    import zstandard

    def flag(name: str, default: int) -> int:
        return int(argv[argv.index(name) + 1]) if name in argv else default

    lo, hi = flag("--min", 1300), flag("--max", 1800)
    per_theme = flag("--per-theme", 150)

    prof_path = ROOT / "data" / "tactics_profile.json"
    if not prof_path.exists():
        sys.exit("Run `python tools/puzzles.py profile` first.")
    themes = set(json.loads(prof_path.read_text(encoding="utf-8"))["themes"])
    if not themes:
        sys.exit("No themes in the profile — nothing to filter on.")

    print(f"Streaming {PUZZLE_DB}\n  rating {lo}-{hi}, themes: "
          f"{', '.join(sorted(themes))}, cap {per_theme}/theme")
    kept: dict[str, list] = {t: [] for t in themes}
    seen = 0
    req = urllib.request.Request(PUZZLE_DB, headers=HEADERS)
    dctx = zstandard.ZstdDecompressor()
    with urllib.request.urlopen(req, timeout=120) as resp, \
            dctx.stream_reader(resp) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        for row in csv.DictReader(text):
            seen += 1
            if seen % 500_000 == 0:
                got = sum(len(v) for v in kept.values())
                print(f"  scanned {seen:,} rows, kept {got}")
            try:
                rating = int(row["Rating"])
                plays = int(row.get("NbPlays") or 0)
                popularity = int(row.get("Popularity") or 0)
            except (ValueError, TypeError):
                continue
            if not (lo <= rating <= hi) or plays < 100 or popularity < 80:
                continue
            row_themes = set((row.get("Themes") or "").split())
            hit = row_themes & themes
            if not hit:
                continue
            if all(len(kept[t]) >= per_theme for t in hit):
                continue
            entry = {"id": row["PuzzleId"], "fen": row["FEN"],
                     "moves": row["Moves"].split(), "rating": rating,
                     "themes": sorted(row_themes),
                     "url": f"https://lichess.org/training/{row['PuzzleId']}"}
            for t in hit:
                if len(kept[t]) < per_theme:
                    kept[t].append(entry)
            if all(len(v) >= per_theme for v in kept.values()):
                print(f"  every theme full after {seen:,} rows — stopping early")
                break

    by_id = {p["id"]: p for bucket in kept.values() for p in bucket}
    DECK.write_text(json.dumps(
        {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "rating_band": [lo, hi], "rows_scanned": seen,
         "per_theme": {t: len(v) for t, v in kept.items()},
         "puzzles": list(by_id.values())}, indent=1), encoding="utf-8")
    print(f"\nKept {len(by_id)} unique puzzles -> data/puzzle_deck.json")
    for t, v in sorted(kept.items()):
        print(f"  {t}: {len(v)}")


# ---------------------------------------------------------------- drill

FILES = "abcdefgh"


def render(board: chess.Board, flip: bool) -> str:
    ranks = range(7, -1, -1) if not flip else range(8)
    files = range(8) if not flip else range(7, -1, -1)
    out = []
    for r in ranks:
        row = [f"{r + 1} "]
        for f in files:
            piece = board.piece_at(chess.square(f, r))
            row.append(f" {piece.symbol() if piece else '.'}")
        out.append("".join(row))
    out.append("   " + " ".join(FILES if not flip else FILES[::-1]))
    return "\n".join(out)


def own_puzzles() -> list[dict]:
    if not BLUNDERS.exists():
        return []
    out = []
    for b in json.loads(BLUNDERS.read_text(encoding="utf-8")):
        try:
            board = chess.Board(b["fen"])
            best = board.parse_san(b["best"])
        except (ValueError, KeyError):
            continue
        out.append({"id": f"own-{b['url'].rsplit('/', 1)[-1]}-{b['move_no']}",
                    "deck": "own", "fen": b["fen"], "moves": [best.uci()],
                    "rating": None, "themes": b.get("motifs", []),
                    "url": b["url"], "played": b["played"],
                    "date": b.get("date"), "phase": b.get("phase")})
    return out


def lichess_puzzles() -> list[dict]:
    if not DECK.exists():
        return []
    return [dict(p, deck="lichess")
            for p in json.loads(DECK.read_text(encoding="utf-8"))["puzzles"]]


def cmd_drill(argv: list[str]) -> None:
    n = next((int(a) for a in argv if a.isdigit()), 15)
    which = argv[argv.index("--deck") + 1] if "--deck" in argv else "mixed"

    own, lich = own_puzzles(), lichess_puzzles()
    if which == "own":
        pool = own
    elif which == "lichess":
        pool = lich
    else:
        pool = own + lich
    if not pool:
        sys.exit("Empty deck. Run `profile` (+ `fetch` for the Lichess deck) first.")

    random.shuffle(pool)
    pool = pool[:n]
    print(f"{len(pool)} puzzles. Enter a move (SAN like Nxe5, or UCI like g1f3). "
          "Commands: hint, skip, quit.\n")

    results = []
    right = 0
    for i, p in enumerate(pool, 1):
        board = chess.Board(p["fen"])
        line = [chess.Move.from_uci(u) for u in p["moves"]]
        if p["deck"] == "lichess":
            board.push(line.pop(0))  # opponent's move sets the puzzle up
        solver = board.turn
        tag = (f"rating {p['rating']}" if p.get("rating")
               else f"your blunder, {p.get('date', '?')}")
        print(f"--- {i}/{len(pool)}  [{p['deck']}, {tag}]")
        print(render(board, flip=(solver == chess.BLACK)))
        print(f"{'White' if solver else 'Black'} to move.")

        solved, gave_up = True, False
        while line:
            want = line.pop(0)
            answer = None
            while answer is None:
                raw = input("  your move: ").strip()
                if raw in ("quit", "q"):
                    finish(results, right, i - 1)
                    return
                if raw in ("skip", "s"):
                    gave_up, solved = True, False
                    break
                if raw in ("hint", "h"):
                    piece = board.piece_at(want.from_square)
                    print(f"  hint: move the {chess.piece_name(piece.piece_type)} "
                          f"on {chess.square_name(want.from_square)}")
                    continue
                try:
                    answer = board.parse_san(raw)
                except ValueError:
                    try:
                        answer = chess.Move.from_uci(raw)
                        if answer not in board.legal_moves:
                            raise ValueError
                    except ValueError:
                        print("  not a legal move here — try again")
                        answer = None
            if gave_up:
                break
            if answer != want:
                print(f"  no — {board.san(want)} was the move")
                solved = False
                break
            print("  correct")
            board.push(want)
            if line:
                board.push(line.pop(0))  # opponent's forced reply
                print(render(board, flip=(solver == chess.BLACK)))

        if solved and not gave_up:
            right += 1
        else:
            print(f"  review: {p['url']}")
            if p["deck"] == "own":
                print(f"  you played {p['played']} here")
        results.append({"id": p["id"], "deck": p["deck"], "themes": p["themes"],
                        "rating": p.get("rating"), "solved": solved and not gave_up})
        print()

    finish(results, right, len(pool))


def finish(results: list[dict], right: int, done: int) -> None:
    if not done:
        return
    print(f"\n{right}/{done} solved ({100 * right / done:.0f}%).")
    by_theme = {}
    for r in results:
        for t in r["themes"]:
            hit, tot = by_theme.get(t, (0, 0))
            by_theme[t] = (hit + int(r["solved"]), tot + 1)
    if by_theme:
        print("By theme:")
        for t, (hit, tot) in sorted(by_theme.items(), key=lambda kv: kv[1][0] / kv[1][1]):
            print(f"  {t}: {hit}/{tot}")
    log = json.loads(DRILL_LOG.read_text(encoding="utf-8")) if DRILL_LOG.exists() else []
    log.append({"date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "solved": right, "attempted": done, "results": results})
    DRILL_LOG.write_text(json.dumps(log, indent=1), encoding="utf-8")
    print(f"Logged to data/drill_log.json ({len(log)} sessions).")


# ---------------------------------------------------------------- export

def cmd_export() -> None:
    puzzles = own_puzzles()
    if not puzzles:
        sys.exit("No blunders to export — run tools/engine_review.py first.")
    out = ROOT / "data" / "own_blunders.pgn"
    with out.open("w", encoding="utf-8") as fh:
        for p in puzzles:
            board = chess.Board(p["fen"])
            game = chess.pgn.Game()
            game.setup(board)
            game.headers["Event"] = f"Own blunder — {p.get('phase', '?')}"
            game.headers["Site"] = p["url"]
            game.headers["Date"] = (p.get("date") or "????.??.??").replace("-", ".")
            game.headers["White"] = "Solve" if board.turn else "Opponent"
            game.headers["Black"] = "Opponent" if board.turn else "Solve"
            game.headers["Result"] = "*"
            node = game.add_variation(chess.Move.from_uci(p["moves"][0]))
            node.comment = f"You played {p['played']} here."
            print(game, file=fh, end="\n\n")
    print(f"Wrote {len(puzzles)} positions -> {out}")
    print("Import at https://lichess.org/study — Add chapter, From PGN, paste "
          "the file. Each blunder becomes a chapter you can drill with the "
          "engine off.")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "profile"
    argv = sys.argv[2:]
    if cmd == "profile":
        cmd_profile()
    elif cmd == "fetch":
        cmd_fetch(argv)
    elif cmd == "drill":
        cmd_drill(argv)
    elif cmd == "export":
        cmd_export()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

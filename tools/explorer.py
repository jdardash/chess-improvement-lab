"""Opening explorer and repertoire leak-finder — the free Opening Explorer.

Builds a move tree from your own chess.com games, then for each position you
reach often, asks two questions:

  1. How do you actually score from here?  (your games — always available)
  2. What do players in your rating band play, and how do they score?
     (the Lichess opening explorer — an online API)

A "leak" is a position you reach repeatedly where your usual move scores well
below what the pool gets from the same position. That is worth more than
knowing twenty moves of theory.

The Lichess explorer has been unreliable through 2026 (see lichess-org/lila
issue 19610). When it is unreachable this still reports your own tree, and
falls back to the Lichess cloud eval API to flag objectively dubious choices.
Responses are cached in data/explorer_cache.json so re-runs are cheap.

Usage: python tools/explorer.py [username] [--since YYYY-MM-DD] [--class rapid]
                               [--min-games 4] [--max-ply 16] [--no-api]
Writes reports/openings.md.
"""

import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "data" / "explorer_cache.json"
HEADERS = {"User-Agent": "chess-improvement-toolkit (jdardash@ucsc.edu)"}
EXPLORER = "https://explorer.lichess.org/lichess"
CLOUD_EVAL = "https://lichess.org/api/cloud-eval"
THROTTLE = 1.1  # seconds between API calls; Lichess asks for roughly this

ECO_RE = re.compile(r'\[ECOUrl "https://www\.chess\.com/openings/([^"]+)"\]')


def arg(name: str, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


USERNAME = (sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
            else "joshuadardashti").lower()
SINCE = datetime.strptime(arg("--since", "2025-01-01"), "%Y-%m-%d").replace(
    tzinfo=timezone.utc).timestamp()
TIME_CLASS = arg("--class", "rapid")
MIN_GAMES = int(arg("--min-games", 4))
MAX_PLY = int(arg("--max-ply", 16))
USE_API = "--no-api" not in sys.argv

CACHE = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
API_DEAD = False


def get_json(url: str, timeout: int = 20) -> dict | None:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def explorer_lookup(uci_line: list[str], band: str) -> dict | None:
    """Pool statistics for a position, or None if the service is unavailable."""
    global API_DEAD
    key = f"{band}|{','.join(uci_line)}"
    if key in CACHE:
        return CACHE[key]
    if not USE_API or API_DEAD:
        return None
    url = EXPLORER + "?" + urllib.parse.urlencode({
        "variant": "standard", "speeds": TIME_CLASS, "ratings": band,
        # Ask for a wide move list: share-of-pool is computed over what comes
        # back, so a short list would report 0% for anything ranked below it and
        # wrongly flag it as offbeat.
        "play": ",".join(uci_line), "topGames": 0, "recentGames": 0, "moves": 20,
    })
    try:
        data = get_json(url)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429, 503):
            print(f"  explorer unavailable (HTTP {e.code}) — continuing with "
                  f"your own games only")
            API_DEAD = True
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        API_DEAD = True
        return None
    time.sleep(THROTTLE)
    slim = {
        "total": data["white"] + data["draws"] + data["black"],
        "moves": [{"san": m["san"], "uci": m["uci"],
                   "n": m["white"] + m["draws"] + m["black"],
                   "score": round(100 * (m["white"] + 0.5 * m["draws"])
                                  / max(1, m["white"] + m["draws"] + m["black"]), 1)}
                  for m in data["moves"]],
    }
    CACHE[key] = slim
    return slim


def cloud_eval(fen: str) -> int | None:
    """Community cloud evaluation in centipawns, White's point of view."""
    key = f"eval|{fen}"
    if key in CACHE:
        return CACHE[key]
    if not USE_API:
        return None
    url = CLOUD_EVAL + "?" + urllib.parse.urlencode({"fen": fen, "multiPv": 1})
    try:
        data = get_json(url)
        cp = data["pvs"][0].get("cp")
        if cp is None:  # a mate score; treat as decisive
            mate = data["pvs"][0].get("mate", 0)
            cp = 10000 if mate > 0 else -10000
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            KeyError, IndexError, json.JSONDecodeError):
        return None
    time.sleep(THROTTLE)
    CACHE[key] = cp
    return cp


def load_games() -> list[dict]:
    out = []
    for f in sorted((ROOT / "data" / "games").glob("*.json")):
        for g in json.loads(f.read_text(encoding="utf-8"))["games"]:
            if (g.get("rules") == "chess" and g.get("pgn")
                    and g["end_time"] >= SINCE
                    and (TIME_CLASS == "all" or g.get("time_class") == TIME_CLASS)):
                out.append(g)
    return out


def build_tree(games: list[dict]) -> dict:
    """node key = 'white|e2e4,e7e5' -> stats about the position AND what I did."""
    tree = defaultdict(lambda: {"n": 0, "pts": 0.0, "moves": defaultdict(
        lambda: {"n": 0, "pts": 0.0, "san": "", "eco": ""})})
    for g in games:
        white = g["white"]["username"].lower() == USERNAME
        side = "white" if white else "black"
        me = g[side]
        result = me["result"]
        pts = 1.0 if result == "win" else (
            0.5 if result in ("agreed", "repetition", "stalemate",
                              "insufficient", "insufficientmaterial",
                              "50move", "timevsinsufficient") else 0.0)
        eco = (ECO_RE.search(g["pgn"]).group(1).replace("-", " ")
               if ECO_RE.search(g["pgn"]) else "")
        game = chess.pgn.read_game(io.StringIO(g["pgn"]))
        if game is None:
            continue
        board = game.board()
        line: list[str] = []
        for node in game.mainline():
            if len(line) >= MAX_PLY:
                break
            move = node.move
            my_turn = (board.turn == chess.WHITE) == white
            if my_turn:
                key = f"{side}|{','.join(line)}"
                entry = tree[key]
                entry["n"] += 1
                entry["pts"] += pts
                entry["fen"] = board.fen()
                mv = entry["moves"][move.uci()]
                mv["n"] += 1
                mv["pts"] += pts
                mv["san"] = board.san(move)
                mv["eco"] = mv["eco"] or eco
            board.push(move)
            line.append(move.uci())
    return tree


def main() -> None:
    games = load_games()
    if not games:
        sys.exit(f"No {TIME_CLASS} games since "
                 f"{datetime.fromtimestamp(SINCE, timezone.utc).date()} in data/games/.")
    print(f"Building opening tree from {len(games)} {TIME_CLASS} games "
          f"(max {MAX_PLY} ply, min {MIN_GAMES} games per node)...")
    tree = build_tree(games)

    nodes = [(k, v) for k, v in tree.items() if v["n"] >= MIN_GAMES]
    nodes.sort(key=lambda kv: (-kv[1]["n"], len(kv[0])))
    print(f"{len(nodes)} positions reached at least {MIN_GAMES} times.")

    findings = []
    for key, entry in nodes:
        side, _, line_str = key.partition("|")
        line = [u for u in line_str.split(",") if u]
        my_move, mv = max(entry["moves"].items(), key=lambda kv: kv[1]["n"])
        if mv["n"] < MIN_GAMES:
            continue
        my_score = 100 * mv["pts"] / mv["n"]

        pool = explorer_lookup(line, "1000,1200,1400") if USE_API else None
        pool_move = pool_score = pool_share = None
        best_alt = None
        if pool and pool["total"] >= 100 and pool["moves"]:
            total_moves = sum(m["n"] for m in pool["moves"])
            mine = next((m for m in pool["moves"] if m["uci"] == my_move), None)
            pool_move = pool["moves"][0]["san"]
            pool_score = mine["score"] if mine else None
            # Absent from a 20-move list means genuinely rare, not unknown.
            pool_share = 100 * mine["n"] / max(1, total_moves) if mine else 0.0
            playable = [m for m in pool["moves"] if m["n"] >= 50]
            if playable:
                top = max(playable, key=lambda m: m["score"])
                if top["uci"] != my_move:
                    best_alt = top

        findings.append({
            "side": side, "line": line, "ply": len(line), "my_uci": my_move,
            "n": mv["n"], "my_move": mv["san"], "my_score": round(my_score, 1),
            "eco": mv["eco"], "fen": entry.get("fen"),
            "pool_top": pool_move, "pool_score_for_my_move": pool_score,
            "pool_share_of_my_move": (round(pool_share, 1)
                                      if pool_share is not None else None),
            "pool_better": ({"san": best_alt["san"], "score": best_alt["score"]}
                            if best_alt else None),
        })

    # Objective sanity check on your most-repeated choices. Independent of the
    # explorer, so it still works when that service is down: the cloud eval is
    # served from lichess.org itself.
    CLOUD_BUDGET = 12
    for f in sorted(findings, key=lambda x: -x["n"])[:CLOUD_BUDGET]:
        if not f.get("fen"):
            continue
        board = chess.Board(f["fen"])
        try:
            board.push(chess.Move.from_uci(f["my_uci"]))
        except (ValueError, AssertionError):
            continue
        cp = cloud_eval(board.fen())
        if cp is None:
            continue
        # Store from your point of view, not White's.
        f["cloud_cp"] = cp if f["side"] == "white" else -cp

    CACHE_PATH.write_text(json.dumps(CACHE, indent=1), encoding="utf-8")

    def san_line(line: list[str]) -> str:
        b = chess.Board()
        out = []
        for u in line:
            m = chess.Move.from_uci(u)
            if b.turn == chess.WHITE:
                out.append(f"{b.fullmove_number}.{b.san(m)}")
            else:
                out.append(b.san(m))
            b.push(m)
        return " ".join(out) or "(start)"

    # A leak is a line you play often and score badly in. Weight by volume so
    # a 30% score over 12 games outranks a 0% score over 4.
    leaks = sorted((f for f in findings if f["n"] >= MIN_GAMES and f["my_score"] < 45),
                   key=lambda f: (f["my_score"] - 50) * f["n"])[:20]

    lines = [
        "# Opening report — your own tree",
        f"Generated {datetime.now(timezone.utc).date()} from {len(games)} "
        f"{TIME_CLASS} games since "
        f"{datetime.fromtimestamp(SINCE, timezone.utc).date()}.",
        "",
    ]
    if not USE_API:
        lines.append("_Run without the Lichess API (--no-api): your own games only._")
    elif API_DEAD:
        lines.append("_The Lichess opening explorer was unreachable on this run, "
                     "so pool comparison columns are blank. Your own numbers "
                     "below are unaffected._")
    lines += [
        "",
        "## Biggest leaks — lines you repeat and lose from",
        "",
        "Score is your points per game as a percentage: 100 = always win, "
        "50 = break even.",
        "",
        "| Line | You play | Games | Your score | Pool plays | Pool's best |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f in leaks:
        pool_top = f["pool_top"] or "—"
        better = (f"{f['pool_better']['san']} ({f['pool_better']['score']}%)"
                  if f["pool_better"] else "—")
        lines.append(
            f"| {f['side']}: {san_line(f['line'])} | **{f['my_move']}** | "
            f"{f['n']} | {f['my_score']:.0f}% | {pool_top} | {better} |")

    common = sorted(findings, key=lambda f: -f["n"])[:15]
    lines += [
        "", "## Most-repeated positions (whatever the score)", "",
        "| Line | You play | Games | Your score | Share of pool playing it |",
        "| --- | --- | --- | --- | --- |",
    ]
    for f in common:
        share = ("—" if f["pool_share_of_my_move"] is None
                 else f"{f['pool_share_of_my_move']}%")
        lines.append(f"| {f['side']}: {san_line(f['line'])} | {f['my_move']} | "
                     f"{f['n']} | {f['my_score']:.0f}% | {share} |")

    offbeat = [f for f in findings
               if f["pool_share_of_my_move"] is not None
               and f["pool_share_of_my_move"] < 2.0]
    if offbeat:
        lines += ["", "## Where you leave the beaten path", "",
                  "Moves fewer than 2% of players in your band choose. Not "
                  "automatically wrong — but you are on your own here.", ""]
        for f in sorted(offbeat, key=lambda f: -f["n"])[:12]:
            lines.append(f"- {f['side']}: {san_line(f['line'])} **{f['my_move']}** "
                         f"— {f['pool_share_of_my_move']}% of the pool, "
                         f"you: {f['n']} games at {f['my_score']:.0f}%")

    judged = [f for f in findings if f.get("cloud_cp") is not None]
    if judged:
        lines += [
            "", "## Objective check (Lichess cloud eval)", "",
            "Deep community evaluation of the position after your usual move, "
            "from your side, measured against the normal opening edge for that "
            "colour (+0.20 for White, -0.25 for Black). Being 0.30 down as "
            "Black is not a leak, it is just Black.", "",
            "| Line | You play | Eval after | Verdict |",
            "| --- | --- | --- | --- |",
        ]
        for f in sorted(judged, key=lambda x: x["cloud_cp"]):
            cp = f["cloud_cp"]
            delta = cp - (20 if f["side"] == "white" else -25)
            verdict = ("clearly worse" if delta <= -70 else
                       "slightly worse" if delta <= -35 else
                       "normal" if delta < 35 else "better than usual")
            lines.append(f"| {f['side']}: {san_line(f['line'])} | "
                         f"{f['my_move']} | {cp / 100:+.2f} | {verdict} |")

    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / "openings.md").write_text("\n".join(lines), encoding="utf-8")
    (ROOT / "data" / "openings.json").write_text(
        json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "username": USERNAME, "time_class": TIME_CLASS,
                    "explorer_available": bool(USE_API and not API_DEAD),
                    "positions": findings}, indent=1), encoding="utf-8")
    print("\n".join(lines))
    print("\nReport: reports/openings.md, data: data/openings.json")


if __name__ == "__main__":
    main()

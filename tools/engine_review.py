"""Stockfish game review of recent rapid games — the free Game Review.

For every move you played in recent rapid games, measures the centipawn loss,
classifies the move (brilliant/great/best/excellent/good/inaccuracy/mistake/
blunder), scores per-move and per-game accuracy with the Lichess formula, tags
each with game phase and your think time, then writes:

  reports/blunders.md  — blunder-rate report plus a per-game review table
  data/blunders.json   — the blunder log (input to tools/puzzles.py)
  data/review.json     — per-game accuracy + every below-par move

Requires python-chess and tools/stockfish/stockfish-windows-x86-64-avx2.exe.

Usage: python tools/engine_review.py [username] [since YYYY-MM-DD] [limit]
  limit is either a fixed depth ("d16", the default) or seconds per position
  ("0.1"). Depth is the reproducible one and is what chess.com's numbers are
  comparable to; below about d16 the engine is too weak and flatters your moves,
  inflating accuracy by ~10 points.
"""

import io
import json
import math
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn

USERNAME = (sys.argv[1] if len(sys.argv) > 1 else "joshuadardashti").lower()
SINCE = datetime.strptime(
    sys.argv[2] if len(sys.argv) > 2 else "2025-01-01", "%Y-%m-%d"
).replace(tzinfo=timezone.utc).timestamp()
LIMIT_ARG = sys.argv[3] if len(sys.argv) > 3 else "d16"

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "tools" / "stockfish" / "stockfish-windows-x86-64-avx2.exe"
CAP = 1000  # clamp evals to +/-10 pawns

BLUNDER, MISTAKE = 200, 100  # centipawn-loss thresholds (blunder log)

# Win-percentage drop thresholds for move classification, in percentage points.
# Win% is eval-context aware, so a 300cp drop in an already-lost position is
# correctly not called a blunder.
WP_EXCELLENT, WP_GOOD, WP_INACCURACY, WP_MISTAKE = 2.0, 5.0, 10.0, 20.0
ONLY_MOVE_GAP = 25.0  # 2nd-best this much worse in win% => the move was "great"
SAC_CP = 200          # material a "brilliant" must genuinely hand over (SEE)

PIECE_CP = {chess.PAWN: 100, chess.KNIGHT: 300, chess.BISHOP: 320,
            chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 10000}

LABELS = ("brilliant", "great", "best", "excellent", "good",
          "inaccuracy", "mistake", "blunder")


def win_percent(cp: float) -> float:
    """Lichess: centipawns -> expected score, 0-100, from the mover's side."""
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(wp_before: float, wp_after: float) -> float:
    """Lichess per-move accuracy from the win-percentage drop."""
    if wp_after >= wp_before:
        return 100.0
    raw = 103.1668 * math.exp(-0.04354 * (wp_before - wp_after)) - 3.1669
    return max(0.0, min(100.0, raw))


def game_accuracy(accs: list[float], wps: list[float]) -> float | None:
    """Lichess game accuracy: mean of a volatility-weighted mean and the
    harmonic mean, so a single howler in a quiet game hurts more than in a
    sharp one."""
    if not accs:
        return None
    window = max(2, min(8, len(wps) // 10))
    weights = []
    for i in range(len(accs)):
        chunk = wps[max(0, i - window):i + window + 1]
        weights.append(statistics.pstdev(chunk) if len(chunk) > 1 else 0.0)
    total_w = sum(weights)
    weighted = (sum(a * w for a, w in zip(accs, weights)) / total_w
                if total_w > 0 else sum(accs) / len(accs))
    harmonic = len(accs) / sum(1 / max(a, 1e-3) for a in accs)
    return round((weighted + harmonic) / 2, 1)


def see(board: chess.Board, square: int) -> int:
    """Static exchange evaluation: material the side to move wins by starting
    a capture sequence on `square`, in centipawns. Standard swap-off with the
    option to decline, so it never returns negative. Recomputing legal moves
    each ply means x-rays are handled for free."""
    victim = board.piece_at(square)
    if victim is None:
        return 0
    captures = [m for m in board.legal_moves
                if m.to_square == square and board.is_capture(m)]
    if not captures:
        return 0
    cheapest = min(captures,
                   key=lambda m: PIECE_CP[board.piece_at(m.from_square).piece_type])
    board.push(cheapest)
    gain = PIECE_CP[victim.piece_type] - see(board, square)
    board.pop()
    return max(0, gain)


def classify(drop: float, played: chess.Move, best: chess.Move | None,
             second_drop: float | None, sacrifice_cp: int,
             wp_before: float, wp_after: float) -> str:
    """chess.com-style label for one move."""
    if drop >= WP_MISTAKE:
        return "blunder"
    if drop >= WP_INACCURACY:
        return "mistake"
    if drop >= WP_GOOD:
        return "inaccuracy"
    if drop >= WP_EXCELLENT:
        return "good"
    # Everything below here is a fine move; decide how fine. Brilliant means a
    # real material sacrifice that still holds up, in a game that was neither
    # already won nor already lost — otherwise every desperado gets a medal.
    if (sacrifice_cp >= SAC_CP and drop < 1.0
            and 10 < wp_before < 90 and wp_after >= 45):
        return "brilliant"
    if (played == best and drop < 1.0 and second_drop is not None
            and second_drop >= ONLY_MOVE_GAP):
        return "great"
    if played == best:
        return "best"
    return "excellent"


def load_recent_rapid() -> list[dict]:
    games = []
    for f in sorted((ROOT / "data" / "games").glob("*.json")):
        for g in json.loads(f.read_text(encoding="utf-8"))["games"]:
            if (g.get("rules") == "chess" and g.get("time_class") == "rapid"
                    and g["end_time"] >= SINCE and g.get("pgn")):
                games.append(g)
    return games


def phase_of(board: chess.Board) -> str:
    if board.fullmove_number <= 10:
        return "opening"
    pieces = len(board.piece_map()) - 2  # exclude kings
    return "endgame" if pieces <= 10 else "middlegame"


def parse_limit(arg: str) -> tuple[chess.engine.Limit, str]:
    if arg.lower().startswith("d"):
        d = int(arg[1:])
        return chess.engine.Limit(depth=d), f"depth {d}"
    t = float(arg)
    return chess.engine.Limit(time=t), f"{t}s/move"


def main() -> None:
    games = load_recent_rapid()
    limit, limit_label = parse_limit(LIMIT_ARG)
    print(f"Reviewing {len(games)} rapid games since "
          f"{datetime.fromtimestamp(SINCE, timezone.utc).date()} "
          f"at {limit_label}...")

    engine = chess.engine.SimpleEngine.popen_uci(str(ENGINE))
    engine.configure({"Threads": 2, "Hash": 128})

    blunder_log = []
    per_game = []
    labels_total = Counter()
    labels_by_time = {}      # bucket -> Counter of labels
    cpl_by_time = Counter()  # think-time bucket -> blunder count
    moves_by_time = Counter()
    cpl_by_phase = Counter()
    moves_by_phase = Counter()
    all_accuracies = []

    for i, g in enumerate(games, 1):
        side = chess.WHITE if g["white"]["username"].lower() == USERNAME else chess.BLACK
        game = chess.pgn.read_game(io.StringIO(g["pgn"]))
        if game is None:
            continue
        tc = g.get("time_control", "")
        increment = float(tc.split("+")[1]) if "+" in tc else 0.0
        try:
            prev_clock = float(tc.split("+")[0]) if "/" not in tc else None
        except ValueError:
            prev_clock = None
        board = game.board()
        my_cpl = []
        my_accs = []
        my_wps = []
        game_labels = Counter()
        game_blunders = 0
        below_par = []  # every inaccuracy-or-worse, for data/review.json

        for node in game.mainline():
            move = node.move
            mover = board.turn
            if mover != side:
                board.push(move)
                continue

            info = engine.analyse(board, limit, multipv=2)
            top = info[0]
            sb = max(-CAP, min(CAP, top["score"].pov(side).score(mate_score=CAP + 500)))
            best_move = top["pv"][0] if top.get("pv") else None
            best_san = board.san(best_move) if best_move else "?"
            second_drop = None
            if len(info) > 1:
                s2 = max(-CAP, min(CAP, info[1]["score"].pov(side).score(mate_score=CAP + 500)))
                second_drop = max(0.0, win_percent(sb) - win_percent(s2))

            san = board.san(move)
            fen = board.fen()
            fullmove = board.fullmove_number
            ph = phase_of(board)
            captured = board.piece_at(move.to_square)
            gained = PIECE_CP[chess.PAWN] if board.is_en_passant(move) else (
                PIECE_CP[captured.piece_type] if captured else 0)
            board.push(move)
            sac_cp = see(board, move.to_square) - gained

            info_after = engine.analyse(board, limit)
            sa = max(-CAP, min(CAP,
                     info_after["score"].pov(side).score(mate_score=CAP + 500)))

            cpl = max(0, sb - sa)
            wp_before, wp_after = win_percent(sb), win_percent(sa)
            drop = max(0.0, wp_before - wp_after)
            acc = move_accuracy(wp_before, wp_after)
            label = classify(drop, move, best_move, second_drop, sac_cp,
                             wp_before, wp_after)

            my_cpl.append(cpl)
            my_accs.append(acc)
            my_wps.append(wp_after)
            game_labels[label] += 1
            labels_total[label] += 1

            # clock in PGN is post-increment: think = prev - clk + inc
            clk = node.clock()
            think = (max(0.0, prev_clock - clk + increment)
                     if (prev_clock is not None and clk is not None)
                     else None)
            if clk is not None:
                prev_clock = clk
            bucket = ("unknown" if think is None else
                      "<5s" if think < 5 else
                      "5-15s" if think < 15 else
                      "15-60s" if think < 60 else ">60s")
            moves_by_time[bucket] += 1
            moves_by_phase[ph] += 1
            labels_by_time.setdefault(bucket, Counter())[label] += 1

            record = {
                "url": g.get("url"),
                "date": datetime.fromtimestamp(
                    g["end_time"], timezone.utc).strftime("%Y-%m-%d"),
                "color": "white" if side else "black",
                "move_no": fullmove,
                "played": san,
                "best": best_san,
                "eval_before": sb,
                "eval_after": sa,
                "cp_loss": cpl,
                "classification": label,
                "accuracy": round(acc, 1),
                "wp_before": round(wp_before, 1),
                "wp_after": round(wp_after, 1),
                "phase": ph,
                "think_seconds": round(think, 1) if think is not None else None,
                "fen": fen,
                "result": g["white" if side else "black"]["result"],
            }
            if label in ("inaccuracy", "mistake", "blunder"):
                below_par.append(record)
            # Keep the historical blunder log on its original cp definition so
            # data/blunders.json stays comparable across runs.
            if cpl >= BLUNDER and abs(sb) < 800:
                game_blunders += 1
                cpl_by_time[bucket] += 1
                cpl_by_phase[ph] += 1
                blunder_log.append(record)

        acc_game = game_accuracy(my_accs, my_wps)
        if acc_game is not None:
            all_accuracies.append(acc_game)
        their_acc = (g.get("accuracies") or {}).get("white" if side else "black")
        per_game.append({
            "url": g.get("url"),
            "chesscom_accuracy": their_acc,
            "date": datetime.fromtimestamp(
                g["end_time"], timezone.utc).strftime("%Y-%m-%d"),
            "color": "white" if side else "black",
            "opponent": g["black" if side else "white"]["username"],
            "accuracy": acc_game,
            "acpl": round(sum(my_cpl) / len(my_cpl)) if my_cpl else 0,
            "moves": len(my_cpl),
            "blunders": game_blunders,
            "labels": dict(game_labels),
            "below_par": below_par,
            "result": g["white" if side else "black"]["result"],
        })
        if i % 10 == 0:
            print(f"  {i}/{len(games)} games done")

    engine.quit()

    (ROOT / "data" / "blunders.json").write_text(
        json.dumps(blunder_log, indent=1), encoding="utf-8")
    (ROOT / "data" / "review.json").write_text(
        json.dumps({"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "username": USERNAME, "limit": limit_label,
                    "games": per_game}, indent=1), encoding="utf-8")

    n_moves = sum(moves_by_time.values())
    n_bl = len(blunder_log)
    mean_acc = (sum(all_accuracies) / len(all_accuracies)) if all_accuracies else 0
    lines = [
        "# Engine game review — recent rapid games",
        f"Generated {datetime.now(timezone.utc).date()}; "
        f"{len(games)} games, {n_moves} of my moves analyzed at {limit_label}.",
        "",
        f"**Mean accuracy: {mean_acc:.1f}** over {len(all_accuracies)} games, "
        f"using the Lichess accuracy formula.",
        "",
        f"Total blunders (>= {BLUNDER}cp loss in undecided positions): {n_bl} "
        f"— one every {n_moves // max(1, n_bl)} moves, "
        f"{n_bl / max(1, len(games)):.1f} per game.",
        "",
    ]

    # Self-calibration: on games where chess.com published its own number (one
    # free Game Review a day), show how far this differs. chess.com uses CAPS2,
    # not the Lichess formula, and runs materially lower at club level — so
    # track the offset rather than assuming the two are interchangeable.
    paired = [(g["accuracy"], g["chesscom_accuracy"]) for g in per_game
              if g["accuracy"] is not None and g["chesscom_accuracy"] is not None]
    if paired:
        diffs = [m - t for m, t in paired]
        lines += [
            f"Calibration: on the {len(paired)} game(s) here where chess.com "
            f"published its own accuracy, this scores "
            f"{sum(d for d in diffs) / len(diffs):+.1f} points "
            f"vs theirs (mine {sum(m for m, _ in paired) / len(paired):.1f}, "
            f"chess.com {sum(t for _, t in paired) / len(paired):.1f}). "
            f"Expected: chess.com's CAPS2 weights position complexity and reads "
            f"lower. Compare this number against itself over time, not against "
            f"theirs.",
            "",
        ]

    lines += ["## Move classification"]
    for lb in LABELS:
        if labels_total[lb]:
            lines.append(f"- {lb}: {labels_total[lb]} "
                         f"({100 * labels_total[lb] / max(1, n_moves):.1f}%)")
    lines += ["", "## Blunder rate by think time"]
    for b in ("<5s", "5-15s", "15-60s", ">60s", "unknown"):
        if moves_by_time[b]:
            lines.append(f"- {b}: {cpl_by_time[b]} blunders in "
                         f"{moves_by_time[b]} moves "
                         f"({100 * cpl_by_time[b] / moves_by_time[b]:.1f}%)")
    lines += ["", "## Blunder rate by phase"]
    for ph in ("opening", "middlegame", "endgame"):
        if moves_by_phase[ph]:
            lines.append(f"- {ph}: {cpl_by_phase[ph]} blunders in "
                         f"{moves_by_phase[ph]} moves "
                         f"({100 * cpl_by_phase[ph] / moves_by_phase[ph]:.1f}%)")

    rated = [g for g in per_game if g["accuracy"] is not None]
    lines += ["", "## Worst 15 games by accuracy", "",
              "| Date | Colour | Acc | ACPL | Blunders | Result | Link |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for g in sorted(rated, key=lambda x: x["accuracy"])[:15]:
        lines.append(f"| {g['date']} | {g['color']} | {g['accuracy']} | "
                     f"{g['acpl']} | {g['blunders']} | {g['result']} | "
                     f"{g['url']} |")

    worst = sorted(blunder_log, key=lambda b: -b["cp_loss"])[:15]
    lines += ["", "## 15 worst blunders (review these positions)", ""]
    for b in worst:
        t = f"{b['think_seconds']}s" if b["think_seconds"] is not None else "?"
        lines.append(f"- {b['date']} move {b['move_no']} as {b['color']}: "
                     f"played {b['played']} (best {b['best']}), "
                     f"{b['eval_before']:+} -> {b['eval_after']:+} "
                     f"[{b['phase']}, thought {t}] {b['url']}")
    (ROOT / "reports" / "blunders.md").write_text("\n".join(lines),
                                                  encoding="utf-8")
    print("\n".join(lines[:30]))
    print(f"\nFull log: data/blunders.json ({n_bl} entries), "
          f"per-game review: data/review.json, report: reports/blunders.md")


if __name__ == "__main__":
    main()

"""Analyze downloaded chess.com games and write a markdown report.

Reads data/games/*.json (produced by fetch_games.py), computes results,
openings, terminations, game phase of losses, and clock usage (move speed,
time left when losing), then writes reports/analysis.md and data/summary.json.

Stdlib only. Usage: python tools/analyze.py [username]
"""

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

USERNAME = (sys.argv[1] if len(sys.argv) > 1 else "joshuadardashti").lower()
ROOT = Path(__file__).resolve().parent.parent
RECENT_SINCE = datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()

CLK_RE = re.compile(r"\[%clk (\d+):(\d+):(\d+(?:\.\d+)?)\]")
ECO_URL_RE = re.compile(r'\[ECOUrl "https://www\.chess\.com/openings/([^"]+)"\]')
LOSS_CODES = {"checkmated", "timeout", "resigned", "abandoned", "lose"}
DRAW_CODES = {"agreed", "repetition", "stalemate", "insufficientmaterial",
              "insufficient", "50move", "timevsinsufficient"}


def clock_seconds(m: re.Match) -> float:
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def base_time(tc: str) -> float | None:
    """'600+5' -> 600; daily '1/86400' -> None (no live clock)."""
    if "/" in tc:
        return None
    return float(tc.split("+")[0])


def opening_family(pgn: str) -> str | None:
    m = ECO_URL_RE.search(pgn)
    if not m:
        return None
    slug = m.group(1)
    # First 2-4 words of the slug is the family; trim move suffixes like "-3.Bb5"
    words = [w for w in slug.split("-") if not re.match(r"^\d", w)][:4]
    return " ".join(words) if words else None


def load_games() -> list[dict]:
    games = []
    for f in sorted((ROOT / "data" / "games").glob("*.json")):
        games.extend(json.loads(f.read_text(encoding="utf-8"))["games"])
    return [g for g in games if g.get("rules") == "chess"]


def my_side(g: dict) -> str | None:
    if g["white"]["username"].lower() == USERNAME:
        return "white"
    if g["black"]["username"].lower() == USERNAME:
        return "black"
    return None


def analyze(games: list[dict]) -> dict:
    per_class = defaultdict(lambda: {
        "n": 0, "w": 0, "l": 0, "d": 0,
        "loss_term": Counter(), "win_term": Counter(),
        "loss_len": [], "openings": defaultdict(lambda: [0, 0, 0]),
        "fast_losses": 0, "clocked_losses": 0, "loss_time_left_frac": [],
        "snap_moves": 0, "timed_moves": 0, "accuracy": [],
        "rating_series": [],
    })

    for g in games:
        side = my_side(g)
        if side is None:
            continue
        me, opp = g[side], g["black" if side == "white" else "white"]
        res = me["result"]
        if res == "win":
            outcome = "w"
        elif res in LOSS_CODES:
            outcome = "l"
        elif res in DRAW_CODES:
            outcome = "d"
        else:
            continue

        s = per_class[g.get("time_class", "?")]
        s["n"] += 1
        s[outcome] += 1
        s["rating_series"].append((g["end_time"], me["rating"]))

        pgn = g.get("pgn", "")
        n_moves = len(re.findall(r"\d+\. ", pgn))

        if outcome == "l":
            s["loss_term"][res] += 1  # my result code: checkmated/resigned/timeout
            s["loss_len"].append(n_moves)
        elif outcome == "w":
            s["win_term"][opp["result"]] += 1  # how the opponent lost

        fam = opening_family(pgn)
        if fam:
            o = s["openings"][(side, fam)]
            o[{"w": 0, "l": 1, "d": 2}[outcome]] += 1

        if acc := g.get("accuracies"):
            s["accuracy"].append(acc[side])

        # Clock analysis: clk comments alternate white/black from move 1
        clks = [clock_seconds(m) for m in CLK_RE.finditer(pgn)]
        base = base_time(g.get("time_control", "/"))
        if clks and base:
            mine = clks[0::2] if side == "white" else clks[1::2]
            if mine:
                # per-move thinking time (ignores increment => conservative)
                prev = [base] + mine[:-1]
                spent = [max(0.0, p - c) for p, c in zip(prev, mine)]
                s["timed_moves"] += len(spent)
                s["snap_moves"] += sum(1 for t in spent if t < 3.0)
                if outcome == "l":
                    s["clocked_losses"] += 1
                    frac = mine[-1] / base
                    s["loss_time_left_frac"].append(frac)
                    if res != "timeout" and frac > 0.5:
                        s["fast_losses"] += 1
    return per_class


def summarize(per_class: dict, label: str) -> list[str]:
    lines = [f"## {label}", ""]
    for tc in ("rapid", "blitz", "bullet", "daily"):
        if tc not in per_class:
            continue
        s = per_class[tc]
        lines.append(f"### {tc} — {s['n']} games: "
                     f"{s['w']}W / {s['l']}L / {s['d']}D "
                     f"({100 * s['w'] / s['n']:.0f}% wins)")
        series = sorted(s["rating_series"])
        lines.append(f"- Rating: {series[0][1]} (first) -> {series[-1][1]} (last)")
        if s["l"]:
            terms = ", ".join(f"{k} {v} ({100*v/s['l']:.0f}%)"
                              for k, v in s["loss_term"].most_common())
            lines.append(f"- How I lose: {terms}")
        if s["w"]:
            terms = ", ".join(f"{k} {v} ({100*v/s['w']:.0f}%)"
                              for k, v in s["win_term"].most_common())
            lines.append(f"- How I win: {terms}")
        if s["loss_len"]:
            short = sum(1 for n in s["loss_len"] if n <= 20)
            mid = sum(1 for n in s["loss_len"] if 20 < n <= 40)
            long_ = len(s["loss_len"]) - short - mid
            lines.append(f"- Losses by length: <=20 moves {short}, "
                         f"21-40 {mid}, >40 {long_} "
                         f"(median {sorted(s['loss_len'])[len(s['loss_len'])//2]})")
        if s["timed_moves"]:
            lines.append(f"- Snap moves (<3s think): {s['snap_moves']} of "
                         f"{s['timed_moves']} timed moves "
                         f"({100*s['snap_moves']/s['timed_moves']:.0f}%)")
        if s["clocked_losses"]:
            fr = s["loss_time_left_frac"]
            lines.append(f"- Non-timeout losses with >50% clock remaining: "
                         f"{s['fast_losses']} of {s['clocked_losses']} "
                         f"({100*s['fast_losses']/s['clocked_losses']:.0f}%); "
                         f"median time left when losing: {100*sorted(fr)[len(fr)//2]:.0f}% of base")
        if s["accuracy"]:
            lines.append(f"- Mean accuracy (where chess.com computed it): "
                         f"{sum(s['accuracy'])/len(s['accuracy']):.1f} "
                         f"over {len(s['accuracy'])} games")
        min_games = 3 if s["n"] < 200 else 5
        best = sorted(((k, v) for k, v in s["openings"].items() if sum(v) >= min_games),
                      key=lambda kv: -sum(kv[1]))[:8]
        if best:
            lines.append("- Most-played openings (side, family: W-L-D):")
            for (side, fam), (w, l, d) in best:
                lines.append(f"    - {side} {fam}: {w}-{l}-{d}")
        lines.append("")
    return lines


def main() -> None:
    games = load_games()
    all_stats = analyze(games)
    recent = [g for g in games if g["end_time"] >= RECENT_SINCE]
    recent_stats = analyze(recent)

    report = ["# Game analysis — joshuadardashti",
              f"Generated {datetime.now(timezone.utc).date()} from "
              f"{len(games)} standard games.", ""]
    report += summarize(recent_stats, "Recent games (since 2025-01-01) — what matters now")
    report += summarize(all_stats, "Full history (2020-2026) — context")

    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    (out / "analysis.md").write_text("\n".join(report), encoding="utf-8")

    def plain(stats):
        return {tc: {k: (dict(v) if isinstance(v, (Counter,)) else
                         {f"{a}|{b}": x for (a, b), x in v.items()}
                         if isinstance(v, defaultdict) else v)
                     for k, v in s.items() if k != "rating_series"}
                for tc, s in stats.items()}
    (ROOT / "data" / "summary.json").write_text(
        json.dumps({"recent": plain(recent_stats), "all": plain(all_stats)},
                   indent=1, default=str), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()

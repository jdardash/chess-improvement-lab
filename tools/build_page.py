"""Build chess.html: one self-contained learning page from everything in this repo.

Reads the JSON that the rest of the toolkit writes, joins it to the vendored web
app in tools/vendor/, and emits a single file that opens from disk with no server
and no network. Run it last in the monthly ritual:

    python tools/fetch_games.py
    python tools/analyze.py
    python tools/engine_review.py
    python tools/puzzles.py profile
    python tools/explorer.py
    python tools/build_page.py        <- this

Every input is optional. A missing file blanks its section and is reported in the
build manifest rather than crashing the build.

Rebuilding the vendored bundle (only needed when tools/webapp/src changes):

    cd tools/webapp && npm install
    npx esbuild src/app.js --bundle --format=iife --minify --target=es2022 \
        --outfile=../vendor/bundle.js
"""

from __future__ import annotations

import io
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
VENDOR = ROOT / "tools" / "vendor"
IMPORTED = DATA / "imported"
OUT = ROOT / "chess.html"
USERNAME = "joshuadardashti"

# engine_review reads sys.argv at import time to pick up an override username.
# Neutralise argv so importing it here cannot pick up our own flags, then reuse
# its game filter and phase rule so this page cannot drift from the reports.
_argv, sys.argv = sys.argv, [sys.argv[0]]
sys.path.insert(0, str(ROOT / "tools"))
from engine_review import load_recent_rapid, phase_of  # noqa: E402
sys.argv = _argv

MANIFEST: list[str] = []


def note(msg: str) -> None:
    MANIFEST.append(msg)
    print(f"  {msg}")


def read_json(path: Path, default):
    if not path.exists():
        note(f"MISSING  {path.relative_to(ROOT)} — section will be blank")
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        note(f"INVALID  {path.relative_to(ROOT)}: {exc}")
        return default


# --------------------------------------------------------------------- ratings

def rating_series(time_class: str = "rapid") -> tuple[list[dict], dict]:
    """Every rated game's post-game rating, oldest first, plus the peak."""
    points = []
    for path in sorted((DATA / "games").glob("*.json")):
        try:
            games = json.loads(path.read_text(encoding="utf-8"))["games"]
        except (json.JSONDecodeError, KeyError):
            note(f"SKIPPED  unreadable archive {path.name}")
            continue
        for g in games:
            if g.get("time_class") != time_class or g.get("rules") != "chess":
                continue
            side = "white" if g["white"]["username"].lower() == USERNAME else "black"
            points.append({"t": g["end_time"], "r": g[side]["rating"]})
    points.sort(key=lambda p: p["t"])
    peak = max(points, key=lambda p: p["r"]) if points else {"t": 0, "r": 0}
    return points, peak


# ------------------------------------------------------- denominators from PGN

def move_denominators() -> tuple[Counter, Counter, dict]:
    """Total own moves per think-time bucket and per phase.

    engine_review.py computes these while the engine runs but only persists the
    numerator (the blunders). Recomputing them here uses the same clock rule, so
    the rates on the page match reports/blunders.md exactly.
    """
    by_time, by_phase = Counter(), Counter()
    per_game_moves: dict[str, int] = {}

    for g in load_recent_rapid():
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
        count = 0
        for node in game.mainline():
            move = node.move
            if board.turn != side:
                board.push(move)
                continue
            by_phase[phase_of(board)] += 1
            clk = node.clock()
            think = (max(0.0, prev_clock - clk + increment)
                     if (prev_clock is not None and clk is not None) else None)
            if clk is not None:
                prev_clock = clk
            by_time["unknown" if think is None else
                    "<5s" if think < 5 else
                    "5-15s" if think < 15 else
                    "15-60s" if think < 60 else ">60s"] += 1
            count += 1
            board.push(move)
        per_game_moves[g.get("url", "")] = count

    return by_time, by_phase, per_game_moves


def pgn_by_url() -> dict[str, dict]:
    """Index every archived game by its chess.com URL, for the best-games section."""
    index = {}
    for path in sorted((DATA / "games").glob("*.json")):
        try:
            games = json.loads(path.read_text(encoding="utf-8"))["games"]
        except (json.JSONDecodeError, KeyError):
            continue
        for g in games:
            if g.get("url"):
                index[g["url"]] = g
    return index


# ------------------------------------------------------------------- best games

# From the 2026-07-27 depth-12 beauty scan of all 4,708 archived games,
# recorded in the session memory for this project.
BEST_GAMES = [
    {
        "url": "https://www.chess.com/game/daily/493556343",
        "title": "The exchange sacrifice, and mate on g3",
        "note": "Black against 1.b3. The exchange sac 13...Qc5, the 20...Nfg4 interpose, "
                "and 27...Qg3#. The scan's pick for the most beautiful win in the archive.",
    },
    {
        "url": "https://www.chess.com/game/live/82475998101",
        "title": "Cleanest game in the archive — ACL 21",
        "note": "Caro-Kann Exchange. 34...Qe2+ deflects into a promotion and mates. "
                "Lowest average centipawn loss of any win you have played.",
    },
    {"url": "https://www.chess.com/game/live/82197683007", "title": "Bullet, cleanly won", "note": "Also flagged by the scan."},
    {"url": "https://www.chess.com/game/daily/497096869", "title": "Daily, second win over the same opponent", "note": "Also flagged by the scan."},
]


def build_best_games(index: dict) -> list[dict]:
    out = []
    for entry in BEST_GAMES:
        g = index.get(entry["url"])
        if not g:
            note(f"MISSING  best game not in archive: {entry['url']}")
            continue
        side = "white" if g["white"]["username"].lower() == USERNAME else "black"
        opponent = g["black" if side == "white" else "white"]["username"]
        out.append({
            **entry,
            "pgn": g["pgn"],
            "color": side,
            "opponent": opponent,
            "time_class": g.get("time_class", ""),
            "date": datetime.fromtimestamp(g["end_time"], timezone.utc).strftime("%Y-%m-%d"),
        })
    return out


# ---------------------------------------------------------------------- studies

STUDY_LABELS = {
    "practical-rook-endings": ("Endgames", "Practical rook endings"),
    "basic-rook-endgames": ("Endgames", "Basic rook endgames"),
    "intermediate-rook-endings": ("Endgames", "Intermediate rook endings"),
    "pawn-key-squares": ("Endgames", "Pawn endgames: key squares"),
    "pawn-opposition": ("Endgames", "Pawn endgames: opposition"),
    "endgames-beginner": ("Endgames", "Endgames you must know — beginner"),
    "endgames-intermediate": ("Endgames", "Endgames you must know — intermediate"),
    "rook-endgames-must-know": ("Endgames", "Rook endgames you must know"),
    "vienna-game": ("Openings", "Vienna Game"),
    "caro-kann": ("Openings", "The Caro-Kann Defence"),
    "vs-1d4-rosen": ("Openings", "Against 1.d4 — Eric Rosen"),
}
STUDY_SOURCE = {
    "practical-rook-endings": "https://lichess.org/study/wS23j5Tm",
    "basic-rook-endgames": "https://lichess.org/study/pqUSUw8Y",
    "intermediate-rook-endings": "https://lichess.org/study/heQDnvq7",
    "pawn-key-squares": "https://lichess.org/study/xebrDvFe",
    "pawn-opposition": "https://lichess.org/study/A4ujYOer",
    "endgames-beginner": "https://lichess.org/study/wukLYIXj",
    "endgames-intermediate": "https://lichess.org/study/UsqmCsgC",
    "rook-endgames-must-know": "https://lichess.org/study/bnboDhFM",
    "vienna-game": "https://lichess.org/study/pETqbUHv",
    "caro-kann": "https://lichess.org/study/Sw1lC13A",
    "vs-1d4-rosen": "https://lichess.org/study/RyMmCrx8",
}


def load_studies() -> list[dict]:
    out = []
    folder = IMPORTED / "studies"
    if not folder.exists():
        note("MISSING  data/imported/studies — Games tab will have no studies")
        return out
    for path in sorted(folder.glob("*.pgn")):
        stem = path.stem
        group, label = STUDY_LABELS.get(stem, ("Imported", stem))
        text = path.read_text(encoding="utf-8")
        out.append({
            "name": stem,
            "group": group,
            "label": label,
            "pgn": text,
            "chapters": text.count("[Event "),
            "source_url": STUDY_SOURCE.get(stem, "https://lichess.org/study/topic"),
        })
    return out


# --------------------------------------------------------------------- openings

def build_openings(openings: dict) -> dict:
    positions = []
    for p in openings.get("positions", []):
        board = chess.Board()
        sans = []
        for uci in p.get("line", []):
            move = chess.Move.from_uci(uci)
            sans.append(board.san(move))
            board.push(move)
        line_san = ""
        for i, san in enumerate(sans):
            line_san += f"{i // 2 + 1}.{'' if i % 2 == 0 else '..'}{san} " if i % 2 == 0 else f"{san} "
        cp = p.get("cloud_cp")
        # Benchmark from reports/openings.md: +0.20 for White, -0.25 for Black.
        verdict = "unknown"
        if cp is not None:
            floor = 20 if p["side"] == "white" else -25
            verdict = "normal" if abs(cp - floor) <= 60 else ("better" if (cp - floor) * (1 if p["side"] == "white" else -1) > 0 else "worse")
        positions.append({
            "side": p["side"], "line_san": line_san.strip(), "my_move": p["my_move"],
            "n": p["n"], "my_score": p["my_score"], "eco": p.get("eco", ""),
            "fen": p["fen"], "cloud_cp": cp if cp is not None else 0, "verdict": verdict,
        })
    positions.sort(key=lambda p: (p["my_score"], -p["n"]))
    return {
        "leaks": positions,
        "explorer_available": openings.get("explorer_available", None),
    }


# -------------------------------------------------------------- endgame drills
# Every FEN below was verified against Stockfish (depth 26) on 2026-08-09: the
# "win" positions are forced mates, the "draw" positions evaluate 0.00. The drill
# is to play the position out against the embedded engine until the goal state.
# Research basis: Capablanca's endgame-first dictum, the Soviet school, and the
# consensus that a small weekly endgame dose is high-leverage (docs/research).

ENDGAME_DRILLS = [
    {"id": "eg-rook-mate", "label": "Rook mate — the box",
     "fen": "8/8/8/4k3/8/8/8/4K2R w - - 0 1", "side": "white", "goal": "win",
     "hint": "Shrink the box with the rook, walk your king up, never a rook check without purpose. "
             "This is the mate every won endgame funnels into."},
    {"id": "eg-queen-mate", "label": "Queen mate — no stalemate",
     "fen": "8/8/8/4k3/8/8/8/3QK3 w - - 0 1", "side": "white", "goal": "win",
     "hint": "Knight's-move distance with the queen shrinks the board; finish with the king. "
             "The only way to fail is stalemate — which is exactly the habit being drilled."},
    {"id": "eg-kp-win", "label": "King and pawn — king on the sixth",
     "fen": "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1", "side": "white", "goal": "win",
     "hint": "King in front of the pawn on the sixth always wins. Zugzwang does the work: "
             "step to the side the enemy king leaves."},
    {"id": "eg-kp-draw", "label": "King and pawn — hold the draw",
     "fen": "4k3/8/8/4K3/4P3/8/8/8 b - - 0 1", "side": "black", "goal": "draw",
     "hint": "Take the opposition every time the kings face off, and retreat straight back. "
             "Stalemate in front of the pawn is the drawing resource."},
    {"id": "eg-lucena", "label": "Lucena — build the bridge",
     "fen": "1K6/1P3k2/8/8/8/8/r7/2R5 w - - 0 1", "side": "white", "goal": "win",
     "hint": "Rc4: the bridge. King out, block the checks with the rook on the fourth rank, promote. "
             "The single most important rook endgame position."},
    {"id": "eg-philidor", "label": "Philidor — hold the draw",
     "fen": "4k3/R7/1r6/4K3/4P3/8/8/8 b - - 0 1", "side": "black", "goal": "draw",
     "hint": "Rook on your third rank until the pawn crosses; then drop it behind and check forever. "
             "Passive defence loses — this exact discipline is the drill."},
    {"id": "eg-q-vs-pawn", "label": "Queen vs pawn on the seventh",
     "fen": "6KQ/8/8/8/8/8/1p6/1k6 w - - 0 1", "side": "white", "goal": "win",
     "hint": "Check, approach, force the king in front of its own pawn, gain a tempo, "
             "walk your king one square closer. Repeat."},
]


# -------------------------------------------------------------- study content
# Curated 2026-08-09. Every URL below was fetched and confirmed live on that date
# by the research pass; the dead ones are kept in DEAD_LINKS so they do not get
# rediscovered and re-added.

STUDY = {
    "habit_quote": "Before releasing any move, answer: after this move, what are ALL of my "
                   "opponent&rsquo;s checks, captures, and threats &mdash; and can I meet each one? "
                   "Also run the reverse scan on their last move.",
    "habit": [
        "Minimum 10&ndash;15 seconds on any non-book move.",
        "Snap moves allowed only when recapturing or in a known book line.",
        "When clearly won (+2 or more): check every opponent check and capture <em>first</em>.",
        "When winning, prefer the boring consolidating move. Trade pieces, not pawns.",
        "Target: snap-move rate under 10%, near-zero blunders on moves played in under 5s.",
    ],
    "setting": [
        "Play 15|10, not 10|0.",
        "Losing with 5+ minutes unused counts as playing too fast, whatever the result.",
    ],
    "ritual": [
        "<code>python tools/fetch_games.py</code>",
        "<code>python tools/analyze.py</code>",
        "<code>python tools/engine_review.py</code>",
        "<code>python tools/puzzles.py profile</code> &mdash; reads what engine_review writes, so run it after",
        "<code>python tools/explorer.py</code>",
        "<code>python tools/build_page.py</code> &mdash; rebuild this page",
        "Work the 15 worst positions in the Train tab before reading any answer.",
        "Classify each blunder: no threat-scan / miscalculation / stopped calculating too soon.",
        "Write the dominant category into the README progress log. That is next month&rsquo;s puzzle theme.",
    ],
    "weekly": [
        "Daily 20&ndash;30 min puzzles, varied sets, accuracy over speed. This is maintenance &mdash; puzzles are already a strength.",
        "2&ndash;4 rapid games a week at 15|10, full effort, Real Chess check every move.",
        "After each loss, find the losing move yourself before checking the engine.",
        "Shift ~30% of study time from raw puzzles to whole-position questions: what is weak, which piece is worst, what is my opponent&rsquo;s next move?",
    ],
    "avoid": [
        "Blitz and bullet as training. They are historic volume and noise for improvement.",
        "Opening study beyond a basic repertoire.",
        "The Woodpecker Method until roughly 1400&ndash;1500.",
        "Buying another book before finishing the current one.",
    ],
    "timeline_note": "No quantitative &ldquo;X months to 1600&rdquo; timeline survived verification &mdash; "
                     "anyone selling one is guessing. These are gates you pass, not dates you hit. "
                     "Measure monthly; rating is noisy at &plusmn;50.",
    "gates": [
        {"at": "now", "what": "Blunder-check discipline",
         "why": "The current tactical level can support ~1300&ndash;1400 rapid on blunder reduction alone, with no new knowledge."},
        {"at": "1400&ndash;1500", "what": "Endgame fundamentals",
         "why": "Silman&rsquo;s Complete Endgame Course, reading only your own rating band. Consider the Woodpecker Method here, not before."},
        {"at": "~1500", "what": "Yusupov, orange volumes",
         "why": "The series is pitched harder than its labels suggest. Starting earlier wastes it."},
        {"at": "1600+", "what": "Unknown territory",
         "why": "The verified evidence thins out above here. Re-derive the plan from your own data at that point."},
    ],
    "books": [
        {"title": "Chess Fundamentals", "author": "Capablanca", "have": True,
         "note": "The classic Botvinnik called the best chess book ever written. Short, endgame-first &mdash; which is exactly the conversion gap.",
         "url": "https://www.gutenberg.org/ebooks/33870", "url_label": "free on Project Gutenberg"},
        {"title": "Logical Chess: Move by Move", "author": "Chernev", "have": False, "gate": "next",
         "note": "Every move explained, pitched at exactly this level. One game a day, board out, guessing each move before reading why."},
        {"title": "Complete Endgame Course", "author": "Silman", "have": False, "gate": "at 1400&ndash;1500",
         "note": "Read only your rating band. Reading ahead is the classic way to waste it."},
        {"title": "Build Up Your Chess (9 vols)", "author": "Yusupov", "have": False, "gate": "at ~1500",
         "note": "The best structured course to 2000+. Buy one volume at a time."},
        {"title": "Lasker&rsquo;s Manual of Chess", "author": "Emanuel Lasker", "have": False, "gate": "optional",
         "note": "Public domain and unrestricted, if you want a second classic alongside Capablanca.",
         "url": "https://archive.org/details/lasker-s-manual-of-chess", "url_label": "free on archive.org"},
    ],
    "openings_note": "Your plan says openings are not what loses these games, and the engine agrees: "
                     "every line below is objectively normal. These are score leaks, not bad moves &mdash; "
                     "positions you reach often and convert badly. The loss happens later.",
    "repertoire_note": "researched, then deprioritised by the plan",
    "repertoire": [
        {"url": "https://lichess.org/study/pETqbUHv", "label": "Vienna Game | INT",
         "note": "The most-viewed Vienna study on Lichess. Imported into the Games tab."},
        {"url": "https://lichess.org/study/ixqSygiE", "label": "Interactive: the Vienna Gambit",
         "note": "Quiz-mode chapters — better retention than reading."},
        {"url": "https://lichess.org/study/Sw1lC13A", "label": "The Caro-Kann Defence",
         "note": "Against 1.e4. Low theory, low blunder rate — suits a player fixing discipline."},
        {"url": "https://lichess.org/study/RyMmCrx8", "label": "Against 1.d4 — IM Eric Rosen",
         "note": "Best-quality free named-author option for Black against 1.d4."},
        {"url": "https://lichess.org/study/topic/Slav%20Defense/popular", "label": "Slav Defence — topic hub",
         "note": "Topic hubs outlive individual studies, which rot silently."},
        {"url": "https://lichess.org/analysis#explorer", "label": "Lichess opening explorer",
         "note": "Free and unlimited, filterable to your exact rating band."},
    ],
    "toolkit": [
        {"cmd": "python tools/fetch_games.py", "does": "Sync all games to data/games/ (incremental)"},
        {"cmd": "python tools/analyze.py", "does": "Stats report -> reports/analysis.md"},
        {"cmd": "python tools/engine_review.py", "does": "Stockfish game review: accuracy, classification, blunders"},
        {"cmd": "python tools/puzzles.py profile", "does": "What your blunders give away -> reports/puzzles.md"},
        {"cmd": "python tools/puzzles.py fetch", "does": "Build a drill deck from the CC0 Lichess puzzle DB"},
        {"cmd": "python tools/puzzles.py drill 20", "does": "Train in the terminal"},
        {"cmd": "python tools/explorer.py", "does": "Opening tree from your own games -> reports/openings.md"},
        {"cmd": "python tools/build_page.py", "does": "Rebuild this page"},
    ],
}

RESOURCES = [
    {
        "title": "Blunder-checking and thinking process",
        "blurb": "The bottleneck. Everything else on this page is downstream of these.",
        "items": [
            {"url": "https://chesscafe.com/text/real.txt", "label": "Heisman — The Secrets to Real Chess",
             "note": "The full text, still free. Defines Hope Chess vs Real Chess and the 3-ply safety check. This is the source of the diagnosis."},
            {"url": "https://www.danheisman.com/thought-process-principles.html", "label": "Heisman — thought-process principles",
             "note": "Invest time by criticality, not by move number. Aimed straight at the 30%-too-fast number."},
            {"url": "https://www.danheisman.com/thought-process-errors.html", "label": "Heisman — thought-process errors",
             "note": "Items 7 (Playing too Fast) and 11 (Hope Chess) map one-to-one onto your data."},
            {"url": "https://nextlevelchess.com/blunder-che/", "label": "Noël Studer — the blunder check",
             "note": "A concrete four-step trigger habit that works for online play. Free, no paywall."},
            {"url": "https://www.chessworld.net/chessclubs/openingguide/checklist-to-avoid-blunders.asp",
             "label": "CCT + LPDO checklist", "note": "Checks, Captures, Threats plus Loose Pieces Drop Off, with eight interactive positions."},
            {"url": "https://www.youtube.com/@danheismanchess", "label": "Heisman's channel",
             "note": "390+ free videos on safety, counting, board vision, time management."},
        ],
    },
    {
        "title": "Converting winning positions",
        "blurb": "28% of your blunders come from positions already winning. This is the second syllabus.",
        "items": [
            {"url": "https://chessmood.com/blog/win-won-games", "label": "Nine rules for winning won games",
             "note": "Free in full. Simplify, trade queens, king safety over greed, kill counterplay. The best short read for this leak."},
            {"url": "https://www.youtube.com/watch?v=EGkjoDqXcTY", "label": "Naroditsky — converting winning positions, part 1",
             "note": "Lesson format, narrated thinking."},
            {"url": "https://www.youtube.com/watch?v=jbQeUOZwhd4", "label": "Naroditsky — part 2", "note": "The continuation."},
            {"url": "https://www.youtube.com/watch?v=rK9W7ycNOpY", "label": "Finegold — converting winning positions",
             "note": "Full-length free lecture."},
            {"url": "https://lichess.org/training/defensiveMove", "label": "Lichess: defensive-move puzzles",
             "note": "Precision needed to avoid losing material — the opposite of the win-material puzzles you are already good at."},
        ],
    },
    {
        "title": "Video series at your rating band",
        "blurb": "Watching someone narrate the thinking process is the cheapest way to absorb it.",
        "items": [
            {"url": "https://www.youtube.com/playlist?list=PL8N8j2e7RpPnpqbISqi1SJ9_wrnNU3rEm",
             "label": "Building Habits — Aman Hambleton", "note": "Rule-based habits designed to eliminate blunders at 1000-1400. Start here."},
            {"url": "https://www.youtube.com/playlist?list=PLT1F2nOxLHOfQ-eoJTpyvKkQFwYewDduj",
             "label": "Beginner to Master speedrun — Naroditsky", "note": "Starts against 1100-1400 opponents. Continuous narration of a strong player's thinking."},
            {"url": "https://www.youtube.com/playlist?list=PLT1F2nOxLHOeyyw85utYJpWtSmxvA-2WR",
             "label": "The Sensei speedrun — Naroditsky", "note": "Slower and more didactic, 1.e4 based."},
            {"url": "https://www.youtube.com/playlist?list=PLl9uuRYQ-6MBwqkmwT42l1fI7Z0bYuwwO",
             "label": "Chess Fundamentals — John Bartholomew", "note": "Episode 1, Undefended Pieces, is the single most on-target video for a 3-blunder-per-game player."},
            {"url": "https://www.youtube.com/playlist?list=PLl9uuRYQ-6MCBnhtCk_bTZsD8GxeWP6BV",
             "label": "Climbing the Rating Ladder — Bartholomew", "note": "Per-band diagnosis of the typical mistakes."},
        ],
    },
    {
        "title": "Structured free curricula",
        "blurb": "Where to go when the drills here run dry.",
        "items": [
            {"url": "https://lichess.org/practice", "label": "Lichess Practice",
             "note": "32 free interactive studies in five tracks. The closest structural match to chess.com Lessons."},
            {"url": "https://listudy.org/en", "label": "Listudy",
             "note": "Free and open source. Spaced-repetition openings, endgames vs Stockfish, and blind tactics — visualisation work that cuts hanging-piece blunders."},
            {"url": "https://lichess.org/learn", "label": "Lichess Learn",
             "note": "Basics plus the coordinates trainer. Board vision reduces oversights."},
            {"url": "https://www.stappenmethode.nl/en/download.php", "label": "Chess Steps — free samples",
             "note": "Official free PDFs for all six steps, including the Thinking Ahead booklets."},
            {"url": "https://www.exeterchessclub.org.uk/content/getting-started-coaching-stuff", "label": "Exeter Chess Club coaching archive",
             "note": "Long-running free archive with downloadable PGN collections you can feed into this toolkit."},
        ],
    },
    {
        "title": "Endgames",
        "blurb": "Gated until 1400-1500 by the plan, except for the conversion technique, which is now.",
        "items": [
            {"url": "https://lichess.org/study/wukLYIXj", "label": "Endgames you must know — beginner",
             "note": "A genuine free Silman-equivalent ladder. Imported into the Games tab."},
            {"url": "https://lichess.org/study/bnboDhFM", "label": "Rook endgames you must know",
             "note": "Philidor, Lucena, the basics. Also imported."},
            {"url": "https://lichess.org/practice/rook-endgames/practical-rook-endings/wS23j5Tm",
             "label": "Lichess Practice: practical rook endings", "note": "Interactive, engine-defended. The endgame type most won games are thrown away in."},
            {"url": "https://tablebase.lichess.ovh/standard?fen=4k3/8/8/8/8/8/4P3/4K3_w_-_-_0_1",
             "label": "Lichess 7-piece tablebase API", "note": "Free, scriptable, perfect play. Solved endgames beat any drill."},
            {"url": "https://www.shredderchess.com/online/endgame-database.html", "label": "Shredder 6-piece tablebase",
             "note": "Browser, no login. Good for eyeballing a botched conversion."},
        ],
    },
    {
        "title": "Public-domain books",
        "blurb": "Legally free, complete, and downloadable.",
        "items": [
            {"url": "https://www.gutenberg.org/ebooks/33870", "label": "Capablanca — Chess Fundamentals",
             "note": "Free epub from Project Gutenberg. Endgame-first."},
            {"url": "https://archive.org/details/lasker-s-manual-of-chess", "label": "Lasker — Manual of Chess",
             "note": "Public Domain Mark, unrestricted download. Not lending-gated."},
            {"url": "https://www.gutenberg.org/ebooks/5614", "label": "Edward Lasker — Chess Strategy", "note": "Public domain."},
            {"url": "https://www.gutenberg.org/ebooks/34180", "label": "Morphy — Exploits and Triumphs",
             "note": "Free classic game collection."},
            {"url": "https://www.gutenberg.org/ebooks/subject/1677", "label": "Gutenberg chess subject index",
             "note": "Everything else that is out of copyright."},
        ],
    },
    {
        "title": "Free tools worth installing",
        "blurb": "The stack that replaces chess.com Diamond for nothing. See docs/free-tool-stack.md for the full argument.",
        "items": [
            {"url": "https://lichess.org/training", "label": "Lichess puzzles",
             "note": "Unlimited, free, ~6M positions. Replaces the 3-per-day cap outright."},
            {"url": "https://chesskit.org", "label": "Chesskit",
             "note": "AGPL. Imports by chess.com username and runs Stockfish in-browser. One-click game review, no daily cap."},
            {"url": "https://encroissant.org/", "label": "En Croissant",
             "note": "Desktop. Local database, multi-engine analysis, repertoire training with spaced repetition. Point it at tools/stockfish/."},
            {"url": "https://github.com/Pawn-Appetit/pawn-appetit", "label": "Pawn Appetit",
             "note": "The actively maintained successor to En Croissant, if that one stalls."},
            {"url": "https://lichess.org/@/maia1", "label": "Maia bots",
             "note": "Neural engines trained to play like a human of a given rating. maia1 is ~1100, maia5 ~1500. Practice that transfers."},
            {"url": "https://github.com/brianch/offline-chess-puzzles", "label": "Offline chess puzzles",
             "note": "MIT. The most-starred maintained app over the Lichess puzzle DB, if you want puzzles away from a browser."},
        ],
    },
]

DEAD_LINKS = [
    {"label": "ChessCafe Novice Nook archive", "status": "Paywalled — $25/yr. The famous free archive is gone; only /text/real.txt survives."},
    {"label": "chesscafe.com/text/heisman*.pdf", "status": "Dead — all redirect to the login page."},
    {"label": "de la Villa '100 Endgames' Lichess studies (HDb9tAGL, Aq49nFJC, cKqviBMN)",
     "status": "401/404 — removed for copyright, but still ranking in Google. No legal free excerpt exists."},
    {"label": "Lichess study 2ROjo3eM 'Vienna Gambit and Game Repertoire'", "status": "404 — despite being the top search hit."},
    {"label": "chessdriller.org", "status": "Broken — TLS certificate expired. Often recommended as the free Chessable alternative."},
    {"label": "zwischenzug.substack.com — 'How to stop losing when you're up'", "status": "Partially paywalled; the actual method is behind the subscription."},
    {"label": "syzygy-tables.info", "status": "Live but bot-blocked. Use tablebase.lichess.ovh instead."},
    {"label": "jeremysilman.com", "status": "Now a book-review blog. No free instructional archive remains."},
    {"label": "hkirat/awesome-chess", "status": "Abandoned 8.5 years. Most-starred and top-ranked, and heavily link-rotted."},
    {"label": "chessable.com / chesstempo.com", "status": "Real and partly free, but both block automated checks and funnel hard to paid tiers."},
]


# ------------------------------------------------------------------ evidence
# Consolidated 2026-08-09 from three deep-research passes (training science,
# tool survey, elite players and coaches) on top of the 2026-07 adversarially
# verified base. Full reports: docs/research-2026-08-what-works.md and
# docs/research-2026-07-chess-improvement.md. The coverage column is the honest audit of
# whether THIS system actually supports each practice.

EVIDENCE = {
    "intro": "What the evidence and the strongest coaches agree on, ranked by consensus, "
             "and whether this system actually covers it. Three deep-research passes "
             "(2026-08) on top of the adversarially verified 2026-07 base. "
             "Full reports in <code>docs/</code>.",
    "practices": [
        {"title": "Analyze your own games, especially losses",
         "who": "The single most universal doctrine: Botvinnik&rsquo;s school (produced Karpov, Kasparov, Kramnik), "
                "Fischer&rsquo;s <em>My 60 Memorable Games</em>, Heisman, Studer, Toth. ChessGoals survey: "
                "the #1 predictor of gains at this level. Annotate yourself first, engine last.",
         "status": "covered",
         "where": "engine_review + the monthly ritual; your blunders become the Train decks"},
        {"title": "Structured study beats raw playing volume",
         "who": "Charness 2005: serious study is the strongest rating predictor. Southwick 2026 "
                "(44,213 players, Psychological Science): puzzles, lessons and drills gain about 3.6x "
                "more rating per hour than playing. You still need the games — study steers, play builds.",
         "status": "covered",
         "where": "this page is the structure; log sessions below"},
        {"title": "A disciplined thought process — prophylaxis every move",
         "who": "Heisman&rsquo;s Real Chess (checks, captures, threats), Aagaard&rsquo;s third question "
                "(&ldquo;what is my opponent&rsquo;s idea?&rdquo;), Dvoretsky&rsquo;s prophylaxis. The documented "
                "barrier between club and expert play — and precisely your measured leak.",
         "status": "covered",
         "where": "the Train gate: timer plus the three-box safety check"},
        {"title": "Daily slow tactics — calculate the full line before moving",
         "who": "Polg&aacute;r canon (5,334 problems, three prodigies), every coach below 1800. "
                "Warning from the Lichess data: puzzle <em>rushing</em> inflates puzzle rating and transfers "
                "nothing — your 1850-puzzle/1061-rapid gap is that phenomenon in one number.",
         "status": "covered",
         "where": "Train decks, gated; accuracy over speed by design"},
        {"title": "Spaced repetition on your own mistakes",
         "who": "Chessable&rsquo;s MoveTrainer principle applied to the highest-value material there is: "
                "positions you actually got wrong. Nate Solon: SRS works for tactics patterns and saved "
                "mistakes; it cannot teach planning. FSRS is the modern scheduler.",
         "status": "covered",
         "where": "every Train card is FSRS-scheduled; misses come back sooner"},
        {"title": "Serious slow games, few but focused, then reviewed",
         "who": "Heisman: &ldquo;play slow games and analyze them.&rdquo; ChessDojo&rsquo;s first pillar. "
                "Per hour, games teach least (Southwick) — but nobody improved without them. "
                "2&ndash;4 per week at 15|10, full effort, is the consensus dose.",
         "status": "covered",
         "where": "the plan&rsquo;s setting; Stats measures whether you complied"},
        {"title": "Convert winning positions — technique under a habit",
         "who": "Aimchess calls it advantage capitalization and trains it from your own games. "
                "Your data: 28% of blunders come while already winning. No generic course fixes this; "
                "replaying your own squandered wins does.",
         "status": "covered",
         "where": "Winning-positions deck + play-it-out vs the engine"},
        {"title": "Endgame fundamentals before opening depth",
         "who": "Capablanca: study the endgame first. Institutionalized by the Soviet school, repeated "
                "by Dvoretsky, Toth, Ramesh. A small weekly dose now; Silman&rsquo;s course at the 1400 gate.",
         "status": "covered",
         "where": "new Endgames deck in Train: seven verified positions, played out vs the engine"},
        {"title": "Time-management telemetry",
         "who": "Heisman: use nearly all the clock; losing with half your time unused is playing too fast "
                "regardless of result. Aimchess surfaces exactly this because it moves rating at club level.",
         "status": "covered",
         "where": "Stats: snap-move rate, blunders by think time, clock left when losing"},
        {"title": "Openings kept minimal, fixed only from your own leaks",
         "who": "Studer, Toth, ChessGoals (their worst-performing archetype front-loads openings), "
                "and the refuted claim in the 2026-07 research pass. One reply to e4, one to d4, one White system.",
         "status": "covered",
         "where": "Study: leak boards from your own games; repertoire deliberately collapsed"},
        {"title": "Guess-the-move through annotated master games",
         "who": "Fischer studied a thousand Steinitz games; Carlsen devoured collections; Dvoretsky "
                "formalized it: cover the moves, commit to yours, compare. The fastest pattern-acquisition "
                "route per the chunking research (Chase &amp; Simon).",
         "status": "partial",
         "where": "studies and best games are replayable in Games; true guess-the-move scoring is the next build. "
                  "Until then: Chernev&rsquo;s <em>Logical Chess</em> at the next gate, one game a day, guessing first"},
        {"title": "Hard calculation without moving the pieces",
         "who": "Ramesh (coach of Praggnanandhaa): solving from a real board, no piece-moving, is "
                "non-negotiable; visualization limits calculation. Dvoretsky&rsquo;s exercises, Yusupov&rsquo;s tests.",
         "status": "partial",
         "where": "the gate already forbids moving until solved; dedicated deep-calculation sets are gated to 1400 "
                  "(Listudy blind tactics linked in resources meanwhile)"},
        {"title": "Feedback from stronger players",
         "who": "Botvinnik made students defend their annotations in front of peers. Gobet &amp; Campitelli: "
                "group practice correlates with skill even more strongly than solitary practice. "
                "No tool replaces this.",
         "status": "external",
         "where": "honest gap — a club, a coach, or ChessDojo&rsquo;s community when ready"},
    ],
    "failure_modes": [
        {"what": "Blitz and bullet as training",
         "why": "Speed play rehearses exactly the no-check habit being unlearned. Your 3,800-game blitz era moved nothing."},
        {"what": "Opening obsession",
         "why": "Studer: the same blunder in a new costume. The engine says your openings are already objectively fine."},
        {"what": "Engine-first analysis",
         "why": "Letting Stockfish think for you trains nothing. Annotate first, check last — ChessDojo bans the reverse."},
        {"what": "Puzzle rushing",
         "why": "Intuition-guessing timed puzzles raises puzzle rating, not chess strength. The gap in your own numbers proves it."},
        {"what": "Passive video as study",
         "why": "Watching counts as entertainment unless you pause and predict. Studer: Twitch is not training."},
        {"what": "Program-hopping and binges",
         "why": "Aagaard: a little daily beats periodic binges. ChessGoals: burnout past ~15-20 h/week; abandoned programs gain zero."},
    ],
    "myths": [
        "10,000 hours guarantees mastery — Gobet &amp; Campitelli measured an 8:1 spread (3,000 to 24,000+ hours), and some never arrive.",
        "Just play a lot — per hour, games are the least efficient activity measured; play anchors, study moves.",
        "Memorize openings first — no serious coach teaches this below master level.",
        "Everyone improves at the same rate — intelligence, age and memory shift both slope and ceiling. Measure your own curve.",
    ],
}


# ------------------------------------------------------------------------ build

def build() -> None:
    print(f"Building {OUT.name}")

    blunders = read_json(DATA / "blunders.json", [])
    review = read_json(DATA / "review.json", {})
    summary = read_json(DATA / "summary.json", {})
    openings = read_json(DATA / "openings.json", {})
    deck = read_json(DATA / "puzzle_deck.json", {})
    profile = read_json(DATA / "tactics_profile.json", {})
    sync = read_json(DATA / "sync_meta.json", {})

    series, peak = rating_series()
    by_time, by_phase, per_game_moves = move_denominators()
    index = pgn_by_url()

    games = review.get("games", [])
    recent = (summary.get("recent") or {}).get("rapid") or {}
    all_rapid = (summary.get("all") or {}).get("rapid") or {}

    moves_analyzed = sum(g.get("moves", 0) for g in games)
    hard_blunders = [b for b in blunders if b.get("classification") == "blunder"]
    winning = [b for b in blunders if b.get("eval_before", 0) >= 200]
    winning_unconverted = [
        b for b in winning
        if next((g for g in games if g["url"] == b["url"]), {}).get("result") not in (None, "win")
    ]

    accuracies = [g["accuracy"] for g in games if g.get("accuracy") is not None]
    paired = [(g["accuracy"], g["chesscom_accuracy"]) for g in games if g.get("chesscom_accuracy")]
    offset = (sum(a - c for a, c in paired) / len(paired)) if paired else 0.0

    clock_left = recent.get("loss_time_left_frac", []) or []
    median_clock = round(sorted(clock_left)[len(clock_left) // 2] * 100) if clock_left else 0

    # Blunders per month, against games played that month.
    per_month_bl: Counter = Counter()
    per_month_games: dict[str, set] = defaultdict(set)
    for b in blunders:
        per_month_bl[b["date"][:7]] += 1
    for g in games:
        per_month_games[g["date"][:7]].add(g["url"])
    by_month = [
        {"month": m, "games": len(per_month_games[m]),
         "per_game": per_month_bl[m] / max(1, len(per_month_games[m]))}
        for m in sorted(per_month_games)
    ]

    bl_by_time = Counter()
    for b in blunders:
        t = b.get("think_seconds")
        bl_by_time["unknown" if t is None else
                   "<5s" if t < 5 else "5-15s" if t < 15 else
                   "15-60s" if t < 60 else ">60s"] += 1

    label_totals = Counter()
    for g in games:
        label_totals.update(g.get("labels", {}))

    motif_counts = profile.get("motifs", {})
    rushed_counts = profile.get("motifs_when_rushed", {})
    n_blunders = profile.get("n_blunders", len(blunders)) or 1

    data = {
        "meta": {
            "built": datetime.now().strftime("%Y-%m-%d"),
            "stats_generated": sync.get("last_sync", "?")[:10],
            "engine_generated": (review.get("generated") or "?")[:10],
            "total_games": sync.get("total_games", 0),
        },
        "stats": {
            "rating_now": series[-1]["r"] if series else 0,
            "rating_peak": peak["r"],
            "rating_peak_t": peak["t"],
            "rating_peak_date": datetime.fromtimestamp(peak["t"], timezone.utc).strftime("%Y-%m-%d") if peak["t"] else "",
            "first_game_date": datetime.fromtimestamp(series[0]["t"], timezone.utc).strftime("%Y-%m") if series else "",
            "rapid_games_all": len(series),
            "total_games": sync.get("total_games", 0),
            "games_reviewed": len(games),
            "moves_analyzed": moves_analyzed,
            "blunders_total": len(blunders),
            "blunders_per_game": len(blunders) / len(games) if games else 0,
            "hard_blunders": len(hard_blunders),
            "winning_blunders": len(winning),
            "winning_blunder_share": 100 * len(winning) / max(1, len(blunders)),
            "winning_blunders_unconverted": len(winning_unconverted),
            "snap_moves": recent.get("snap_moves", 0),
            "timed_moves": recent.get("timed_moves", 0),
            "snap_share": 100 * recent.get("snap_moves", 0) / max(1, recent.get("timed_moves", 1)),
            "accuracy_mean": sum(accuracies) / len(accuracies) if accuracies else 0,
            "accuracy_offset": offset,
            "median_clock_left": median_clock,
            "losses": recent.get("l", 0),
            "clock_rich_losses": sum(1 for f in clock_left if f > 0.5),
            "wins": recent.get("w", 0),
        },
        "rating_series": series,
        "charts": {
            "think_time": [
                {"label": k, "blunders": bl_by_time.get(k, 0), "moves": by_time.get(k, 0),
                 "rate": bl_by_time.get(k, 0) / by_time[k] if by_time.get(k) else 0}
                for k in ("<5s", "5-15s", "15-60s", ">60s") if by_time.get(k)
            ],
            "phase": [
                {"label": k, "blunders": sum(1 for b in blunders if b.get("phase") == k),
                 "moves": by_phase.get(k, 0),
                 "rate": sum(1 for b in blunders if b.get("phase") == k) / by_phase[k] if by_phase.get(k) else 0}
                for k in ("opening", "middlegame", "endgame") if by_phase.get(k)
            ],
            "classification": [
                {"label": k, "n": label_totals.get(k, 0)}
                for k in ("brilliant", "great", "best", "excellent", "good", "inaccuracy", "mistake", "blunder")
                if label_totals.get(k)
            ],
            "by_month": by_month,
            "clock_left": clock_left,
            "motifs": [
                {"motif": m, "n": n, "share": n / n_blunders,
                 "rushed": rushed_counts.get(m, 0),
                 "rushed_share": rushed_counts.get(m, 0) / n if n else 0}
                for m, n in sorted(motif_counts.items(), key=lambda kv: -kv[1])
            ],
        },
        "blunders": blunders,
        "puzzles": deck.get("puzzles", []),
        "openings": build_openings(openings),
        "games": [
            {"date": g["date"], "color": g["color"], "opponent": g["opponent"],
             "accuracy": g["accuracy"], "acpl": g["acpl"], "blunders": g["blunders"],
             "moves": g["moves"], "result": g["result"], "url": g["url"]}
            for g in games
        ],
        "worst_moves": sorted(blunders, key=lambda b: -b["cp_loss"])[:15],
        "best_games": build_best_games(index),
        "studies": load_studies(),
        "study": STUDY,
        "resources": RESOURCES,
        "dead_links": DEAD_LINKS,
        "evidence": EVIDENCE,
        "endgame_drills": ENDGAME_DRILLS,
    }

    note(f"OK       {len(blunders)} blunders, {len(data['puzzles'])} puzzles, "
         f"{len(games)} reviewed games, {len(series)} rating points, "
         f"{len(data['studies'])} studies, {len(data['best_games'])} best games")

    # ---------------------------------------------------------------- assemble

    def read_asset(path: Path) -> str:
        if not path.exists():
            note(f"MISSING  {path.relative_to(ROOT)} — run the esbuild step in this file's docstring")
            return ""
        return path.read_text(encoding="utf-8")

    bundle_js = read_asset(VENDOR / "bundle.js")
    bundle_css = read_asset(VENDOR / "bundle.css")

    engine_src = ""
    sf = IMPORTED / "stockfish.js"
    if sf.exists():
        engine_src = sf.read_text(encoding="utf-8")
    else:
        note("MISSING  data/imported/stockfish.js — the conversion drill will be disabled")

    # The engine rides in a text/plain block rather than a JS string literal: at
    # 1.5MB, escaping it as a string is both slow and easy to get wrong. Only the
    # closing-tag sequence needs neutralising.
    engine_block = engine_src.replace("</script", "<\\/script")
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")

    html = f"""<!doctype html>
<html lang="en" data-theme="">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chess — 1200 to 1600</title>
<meta name="description" content="Personal chess training page built from {data['stats']['total_games']} games.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='0.9em' font-size='90'%3E%26%239822;%3C/text%3E%3C/svg%3E">
<style>{bundle_css}</style>
</head>
<body>
<header class="masthead">
  <div class="masthead-top">
    <h1>Chess</h1>
    <span class="goal">rapid <strong id="rating-now">—</strong> &rarr; goal <strong>1600</strong>, stretch 2000</span>
    <span class="built">built <span id="built-on">—</span> · offline · no tracking</span>
  </div>
  <nav id="tabs" role="tablist" aria-label="Sections"></nav>
</header>
<main id="app"></main>
<script type="application/json" id="chess-data">{payload}</script>
<script type="text/plain" id="engine-src">{engine_block}</script>
<script>
  window.__CHESS_DATA__ = JSON.parse(document.getElementById('chess-data').textContent);
  window.__CHESS_DATA__.engineSource = document.getElementById('engine-src').textContent;
</script>
<script>{bundle_js}</script>
</body>
</html>
"""

    OUT.write_text(html, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"\nWrote {OUT.relative_to(ROOT)} — {size / 1_048_576:.1f} MB")
    problems = [m for m in MANIFEST if not m.startswith("OK")]
    if problems:
        print(f"{len(problems)} input(s) missing or unreadable; those sections degrade rather than fail.")


if __name__ == "__main__":
    build()

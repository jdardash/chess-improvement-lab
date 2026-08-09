# Personalized Plan — from my actual games (2026-07)

Derived from 4,708 chess.com games (2020-2026), a Stockfish review of all 83
rapid games played since 2025, and targeted research on the puzzle-game gap.
Evidence base for the general method: `docs/research-2026-07-chess-improvement.md`.

## The diagnosis

The account tells one clear story. Tactics are not the problem:

- Puzzle rating ~1850-1900 vs rapid 1061 — an ~800-point gap, at the top edge
  of the normal 400-800 range even allowing for chess.com puzzle inflation.
- Recent rapid (2025-26): 36W/45L/2D (43%), rating drifting 1138 -> 1061.
- 30% of rapid moves are played in under 3 seconds.
- In 42% of non-timeout losses, more than half the clock was still unused;
  the median loss ends with 44% of the clock left. Historically it was worse
  (65% of losses with >50% time left).
- All 83 recent rapid games are 10|0 against ~1080-rated opposition.
- Blitz (751) and bullet (665) are historic volume (3,800+ games in 2020/2023)
  and are noise for improvement purposes; recent play is correctly rapid-only.

This is the textbook "hope chess" profile (Heisman): the tactical skill exists
but moves are committed without checking the opponent's checks, captures, and
threats in reply — a discipline failure, not a knowledge failure. The fix is
behavioral, which is good news: it is worth more rating faster than any amount
of additional study.

## What the engine found (all 83 rapid games since 2025, Stockfish)

256 blunders (>=200cp loss in undecided positions) in 2,680 moves: one every
10 moves, 3.1 per game. Full log in `data/blunders.json`; worst positions in
`reports/blunders.md`.

Where they happen:

- **Middlegame: 78% of all blunders** (12.8% of middlegame moves), vs 4.7% in
  the opening and 6.1% in the endgame. The middlegame is the syllabus.
- **28% of blunders come in positions already winning (+2 or better)** — 73
  blunders across 39 of the 83 games, and 34 of them came in games that were
  then not won. Converting won positions is the single largest recoverable
  point leak in the data.
- 12% are king moves (Kf6, Kf2, Kg2 feature in the worst-of list) — king
  safety checks fail when attention is elsewhere.

One honest correction to the intuitive story: blunder rate *rises* with think
time (4.7% on <5s moves, 16.9% on 15-60s moves). This is partly selection —
hard positions get long thinks — but it means the problem is not only
impulsivity: even when time is spent, the check for opponent replies is not
happening reliably (Heisman's "quiescence error": stopping calculation one
move too soon). The 55 sub-5-second blunders are still free rating, but the
checklist matters most exactly on the big thinks, and above all when ahead.

## The plan — one habit, one setting, one ritual

**1. The habit (the whole ballgame): Heisman's Real Chess check on every move.**
Before releasing any move, answer: after this move, what are ALL of my
opponent's checks, captures, and threats — and can I meet each one? Also run
the reverse scan on their last move (what does it check, capture, threaten?).
Minimum ~10-15 seconds on any non-book move; a snap move is only allowed when
recapturing or in a known book line. Success metric: snap-move rate (<3s)
under 10% and near-zero blunders on moves played in under 5 seconds — the
toolkit measures both.

**1b. The winning-position protocol.** The moment the position is clearly won
(up a piece, +2 or more), deliberately slow down instead of relaxing: the data
says this is when 28% of blunders happen. Each move while ahead: check every
opponent check and capture first, prefer the boring consolidating move over
the flashy one, and trade pieces (not pawns) toward a trivially won endgame.

**2. The setting: play 15|10 instead of 10|0.** The increment removes flagging
as a failure mode, rewards the blunder-check habit, and makes won endgames
convertible. Pace like a marathon (Heisman): a well-played game should end
with most of the clock consumed. Losing with 5+ minutes unused = played too
fast, regardless of result.

**3. The ritual (monthly, ~30 min):**

```text
python tools/fetch_games.py
python tools/analyze.py
python tools/engine_review.py
```

Read `reports/blunders.md`. Set up the 15 worst positions on a board and find
the right move before reading the answer. Classify each blunder with Heisman's
taxonomy — no threat-scan / miscalculation / stopped calculating too soon —
and note the dominant category in the README progress log. That category is
next month's puzzle theme.

## Weekly shape (unchanged budget, ~30-45 min/day)

- **Daily 20-30 min:** puzzles, varied sets, accuracy over speed. Puzzles are
  already a strength — this maintains; the rating gains come from items 1-2.
- **2-4 rapid games/week at 15|10,** full effort, Real Chess check every move.
  Fewer, slower games beat more, faster ones. After each loss: find the losing
  move yourself before checking the engine.
- **Shift ~30% of study time** from raw puzzles to whole-position questions
  (Aagaard): what is weak, which piece is worst, what is my opponent's next
  move? Question 3 doubles as blunder prevention.
- **Avoid:** blitz/bullet as training, opening study beyond a basic repertoire
  (the data shows openings are not what loses these games), Woodpecker until
  ~1400-1500 per the research file.

## Expectations

The realistic read (per the gap research): the current tactical level can
support ~1300-1400 rapid on blunder-reduction alone — no new knowledge
required. The 1600 goal likely needs the endgame/positional layer described
in `docs/research-2026-07-chess-improvement.md`, gated at 1400-1500. Measure monthly, not
per-session; rating is noisy at +/-50.

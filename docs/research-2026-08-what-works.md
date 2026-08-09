# What Actually Works — deep research, 2026-08-09

Three parallel research passes on top of the adversarially verified 2026-07 base
(`Chess Improvement Research.md`): (1) the training-science and coaching consensus
for 800-1600 adult improvers, (2) a feature survey of every serious training tool,
(3) what the world's best players actually did and what elite coaches teach.
This file is the consolidated record; the page's "What actually works" section in
`chess.html` is generated from the same conclusions.

## 1. The headline consensus

Across academic research, GM coaches, and data-driven programs, the same loop
appears everywhere, disagreeing only about proportions:

> Play serious slow games → deeply analyze your own games → drill tactics daily
> (slowly, full-line) → add a small endgame/strategy dose → keep openings minimal.

Quality and consistency of practice matter more than volume: the ChessGoals
survey found hours/week only the third-strongest predictor of gains, behind
starting rating and age.

## 2. What the science says

- **Charness et al. 2005** (Applied Cognitive Psychology): accumulated *serious
  solitary study* is the strongest single predictor of rating — ahead of
  tournament play and instruction. GMs averaged ~5,000 study hours in their first
  decade, ~5x intermediate players.
- **Southwick et al. 2026** (Psychological Science, n=44,213 Chess.com players,
  time-stamped): players spend >90% of chess time playing, but puzzles, lessons
  and drills produce **~3.6x more rating gain per hour** than gameplay. The first
  large-scale objective confirmation of what coaches were saying all along.
- **Chase & Simon 1973** (chunking): mastery rests on tens of thousands of stored
  patterns; training that builds a retrievable pattern library (tactics volume,
  master games, standard endgames) is mechanistically on-target.
- **Gobet & Campitelli 2007**: ~11,000 hours average to master level but with an
  8:1 spread (3,000-24,000+); some never arrive. Group practice correlated with
  skill even more strongly than solitary practice. Practice is necessary, not
  sufficient.
- **Macnamara et al. 2014** (meta-analysis): deliberate practice explains ~26-34%
  of skill variance in games — the largest *controllable* factor, far from the
  only one. Identical routines produce different curves; measure your own slope.

## 3. What the greats actually did

- **Fischer**: obsessive solitary book study (reportedly 1,000+ books, taught
  himself Russian for Soviet literature, ~1,000 Steinitz games studied); the
  brutally honest self-annotation of *My 60 Memorable Games*.
- **Botvinnik school** (Karpov, Kasparov, Kramnik): students presented four of
  their own games including at least one loss, peers attacked the analysis,
  homework in between. Ruthless self-analysis as an institution.
- **Polgár sisters**: the closest thing to a controlled experiment — 5-6 hours
  daily from age ~4, tactics-saturated (the 5,334-problem canon), enormous
  playing volume, deliberately kept fun.
- **Carlsen**: massive joyful volume — books devoured, endless blitz, tournaments
  — and almost no formal regimen; the academic literature cites him as a
  deliberate-practice counterexample (outlier memory). A caution against copying
  anyone's path literally.
- **Soviet school / Dvoretsky**: endgame-first (Capablanca's dictum), curated
  exercises over random puzzles, endgame studies for imagination, playing out
  positions to conversion, guess-the-move through annotated games, prophylaxis.

## 4. What elite coaches converge on

Every major coach independently lands on the same four:

1. Analyze your own games honestly (engine last) — Botvinnik, Heisman, Studer,
   Toth, ChessDojo. ChessGoals: the #1 predictor of gains at novice level.
2. Solve hard positions properly — real board, no piece-moving, full lines
   (Ramesh: "without progress on visualisation it is impossible to make progress
   in calculation"; Dvoretsky, Aagaard, Yusupov's test format).
3. Endgames and calculation before opening memorization (Capablanca, Toth,
   Ramesh; every "worst archetype" in the survey data front-loads openings).
4. A narrow consistent program over scattered consumption (Studer's One-Third
   Rule: a third playing, a third tactics, a third learning + analysis; Aagaard:
   a little daily beats binges).

Plus the thought-process layer: Heisman's Real Chess (all checks, captures,
threats, every move), Aagaard's three questions (weaknesses, worst piece,
opponent's idea), Dvoretsky's prophylaxis — the documented barrier between club
and expert play.

## 5. Failure modes (the ways adult improvers stall)

1. Blitz/bullet as "training" — rehearses the no-check habit.
2. Opening obsession — "the same blunder in a new costume" (Studer).
3. Not reviewing losses; engine-first analysis (ChessDojo bans it).
4. Puzzle rushing — puzzle rating inflates, nothing transfers (the
   "2100 puzzles / 1500 rapid" phenomenon; this account's 1850/1061 gap).
5. Passive video counted as study.
6. Program-hopping and volume binges — burnout past ~15-20 h/week; an abandoned
   program gains zero.

## 6. Checked and not true

- "10,000 hours guarantees mastery" — falsified by the 8:1 spread.
- "Just play a lot" — least efficient activity per hour measured.
- "Memorize openings first" — no serious coach teaches it below master.
- "X months to 1600" timelines — none survived verification (2026-07 pass).

## 7. Tool survey — what the best trainers offer

Surveyed: Lichess, Chess.com, Chessable (MoveTrainer), Aimchess, ChessDojo,
Chess Tempo, Listudy, Noctie, Lucas Chess, and open-source trainers. The
features rated most impactful, in order:

1. **Spaced-repetition tactics with failure-driven repetition** (Chessable,
   Chess Tempo, Woodpecker) — covered here by FSRS on every Train card.
2. **Mistake-based training from your own games** (Aimchess, chessli2,
   Chess.com Game Review) — this repo's core design: blunders become decks.
3. **Opening drilling against your repertoire** (Listudy, Chessable) —
   deliberately minimal here per the plan.
4. **Endgame drills played to conversion vs engine** (Lichess Practice,
   Chess Tempo) — added 2026-08: seven verified positions in Train.
5. **Weakness analytics dashboards** (Aimchess, Insights) — the Stats tab.
6. **Plan scaffolding and habit tracking** (ChessDojo) — the Study checklist
   and the session log.
7. **Guess-the-move, calculation-entry, blindfold modes** (Lucas Chess,
   Chess Tempo, Listudy) — the honest remaining gap; gated, not forgotten.

## 8. What this changed on the page

- New **Endgames deck** in Train: rook mate, queen mate, K+P win and defense,
  Lucena, Philidor, Q vs 7th-pawn — each engine-verified (depth 26), each played
  out against full-strength Stockfish until converted or held.
- New **"What actually works" section** in Study: the ranked consensus practices,
  each with an honest coverage badge (on this page / partial / outside this page).
- New **session log** in Study: 3.5-7 focused hours/week is the evidence band;
  what gets measured gets done.
- The rest of the audit came back clean: the FSRS blunder drills, the Real Chess
  gate, the conversion drill, the time telemetry, and the minimal-openings stance
  are all exactly what the evidence orders for this player's measured leak.

## Key sources

Charness et al. 2005 (Wiley); Southwick et al. 2026 (Psychological Science);
Chase & Simon 1973; Gobet & Campitelli 2007-08; Macnamara, Hambrick & Oswald 2014;
nextlevelchess.com (GM Noël Studer); danheisman.com; chessdojo.club
(Kraai/Pruess/Kavutskiy); chessgoals.com survey; zwischenzug.gg (Nate Solon);
Ramesh interviews (Next Level Chess, SayChess); Dvoretsky retrospectives;
Agdestein on Carlsen; chesshistory.com; Polgár accounts; discochess.com
Woodpecker dataset; aimchess.com; listudy.org; lucaschess.pythonanywhere.com;
lichess.org open database and practice.

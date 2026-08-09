# chess.html — design record

Written 2026-08-09, after the build. Records what was decided and why, so the
next change to `tools/webapp/src` does not have to re-derive it.

## Problem

The repo already measures the player accurately — 4,709 archived games, 83
reviewed at depth 16, 249 blunders with FEN, motif, phase and think time, 1,037
matched Lichess puzzles, plus a plan derived from all of it. None of that was
reachable while actually training. The reports are markdown; the drills were
terminal-only; the resources were scattered across two documents and a lost
session.

The diagnosis those files agree on is specific and unusual: **a discipline
failure, not a knowledge failure.** Puzzle rating ~1850 against rapid 1061. 30%
of moves played in under three seconds. 78% of blunders in the middlegame. 28%
of blunders made from positions already winning. Blunder rate that *rises* with
think time — 4.8% under 5s, 16.3% at 15-60s.

A page that merely displays this would be a fifth report. The design goal is a
page that changes behaviour.

## Decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Scope | Four tabs: Train, Stats, Study, Games | Chosen over a single-purpose page; the data supports all four and they reinforce each other. |
| Delivery | Local single file + `tools/build_page.py` | Works offline, no server, and the monthly ritual refreshes every number with one more command. An artifact snapshot would freeze the data. |
| Train behaviour | Enforced gate | The reveal is locked behind a think timer *and* the Real Chess checklist. Serving positions without the gate would drill tactics — the thing already strong. |
| Openings | Leak analysis first, repertoire collapsed underneath | Resolves the contradiction between the plan ("avoid opening study") and the lost Vienna/Sicilian/Slav research. Both are present; the tension is stated on the page. |
| Engine | Stockfish 10 asm.js, embedded | Enables the conversion drill. asm.js over WASM because it needs no cross-origin isolation, no `wasm-unsafe-eval`, and no companion file. 1.5 MB for ~2900 Elo, far above what is needed. |
| Charts | Hand-rolled SVG | ~200 lines against a charting dependency that would cost more bytes than it saves. |

## Architecture

```
data/*.json ──┐
reports/      ├──> tools/build_page.py ──> chess.html  (single file, 2.4 MB)
data/imported/│                              ├─ inlined bundle.css  (55 KB)
              │                              ├─ inlined bundle.js  (198 KB)
tools/vendor/ ┘                              ├─ <script type=application/json>  data
                                             └─ <script type=text/plain>  stockfish
tools/webapp/src/*.js ──> esbuild ──> tools/vendor/bundle.{js,css}
```

The esbuild step is separate and rarely run: the bundle is vendored, so a normal
rebuild is pure Python and needs no Node and no network.

Modules, each with one job:

- `board.js` — the only place chessground (rendering, input) meets chess.js
  (legality). Exposes `makeBoard` and `uciToSan`.
- `engine.js` — Stockfish over a Blob-URL Worker, UCI wrapped in promises.
- `charts.js` — five pure SVG chart functions, no app knowledge.
- `train.js`, `stats.js`, `study.js`, `games.js` — one tab each, each a single
  `render(root, data)` entry point.
- `app.js` — tab routing and boot. Renders tabs lazily and catches per-tab
  errors so one broken tab cannot take the page down.

## Data notes that cost time to establish

- `blunders.json` is **not** only blunders: it is every event losing ≥200cp, so
  it includes 10 rows classified `good`. It is a subset of
  `review.json.games[].below_par` (249 of 632) plus a `motifs` field.
- `review.json` stores only below-par moves, so the *denominators* for the
  think-time and phase rates are not persisted anywhere. `build_page.py`
  recomputes them by replaying the PGNs with the same clock rule
  (`think = prev_clock - clk + increment`), importing `load_recent_rapid` and
  `phase_of` from `engine_review.py` rather than copying them, so the page
  cannot drift from `reports/blunders.md`.
- Evals are clamped at ±1000cp upstream. The page says so rather than rendering
  them as unbounded.
- Two generation timestamps exist (`sync_meta` 2026-07-27, `review` 2026-08-09).
  Both are printed; they are not from the same run.
- `puzzle_deck.json` has no per-puzzle theme label — group by intersecting
  `themes` with the `per_theme` keys.
- `openings.json` has `explorer_available: false` and all `pool_*` null, because
  the Lichess explorer was down. The page renders a stated reason, not blanks.

## Verification performed

In a real Chromium, over both `http://` and `file://`:

- All four tabs render with no page errors (only a favicon 404 over http).
- The gate: reveal disabled with "Wait 15s more", enabled after the timer plus
  all three ticks, then reveals the missed move against what was actually played.
- FSRS returns real intervals (Again 1m / Hard 6m / Good 10m / Easy 7d).
- Move input via trusted mouse drag: piece selected, 8 legal destinations
  offered, move accepted.
- The engine starts from `file://` and replies to a move.
- Every statistic cross-checked against `reports/blunders.md` and
  `reports/puzzles.md`.

Note for future tests: chessground's `drag.start` begins with
`if (!(s.trustAllEvents || e.isTrusted)) return;`. Synthetic `MouseEvent` and
`PointerEvent` dispatch is ignored. Board interaction must be driven with a real
mouse (`page.mouse`) or with `trustAllEvents` enabled.

## Addendum — same day, after the deep-research pass

Three research agents (training science, tool survey, elite coaching) audited
the page against the consensus; see `docs/research-2026-08-what-works.md`.
Changes made in response:

- **Endgames deck** in Train: seven canonical positions (rook mate, queen mate,
  K+P win/defense, Lucena, Philidor, Q vs 7th-pawn), each verified against
  Stockfish at depth 26 before baking (wins are forced mates, draws are 0.00),
  each played out against the engine at skill 20 until converted or held. No
  think-timer gate there — the skill drilled is multi-move technique, not the
  single-move safety check. FSRS still schedules the positions.
- **Evidence section** in Study: the ranked consensus practices with honest
  coverage badges (on this page / partial / outside this page), failure modes,
  and refuted myths. Generated from `EVIDENCE` in `build_page.py`.
- **Session log** in Study: localStorage, minutes + activity, weekly total
  against the 3.5-7 h band.
- **Board theme fix**: pgn-viewer's stylesheet loads after chessground.brown.css
  and repainted every board gray with its transp theme. `style.css` bundles last
  and re-asserts the brown board; that is why the rule lives there.
- Inline SVG favicon (fixes the only console error, a favicon 404 over http).

## Deliberately not built

- **In-page game review of arbitrary PGN.** Chesskit already does this well and
  `tools/engine_review.py` does it better for these games.
- **Live chess.com sync from the page.** It would break the offline guarantee;
  `fetch_games.py` owns that.
- **Endgame tablebase drills.** Would need positions precomputed at build time
  against the Lichess tablebase API. Worth doing at the 1400-1500 gate, not now.
- **A published/shared version.** Everything vendored except chess.js is
  GPL-3.0, which is irrelevant for a local file and a decision if published.

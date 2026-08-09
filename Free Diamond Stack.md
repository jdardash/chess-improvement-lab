# Replicating Chess.com Diamond for $0

Researched 2026-08-08. Diamond is ~$100/yr. Everything below is free and legal
(public APIs, open-source software, CC0 data). Nothing here requires cracking,
sharing accounts, or scraping behind a login.

## First, the honest framing

Diamond does not sell you capability. It sells you **the removal of artificial
friction** on chess.com specifically. Every single analytical thing it does,
free software does as well or better — the engine is the same Stockfish, the
master database is smaller than Lichess's, and its "deep analysis" is shallower
than what your own CPU can run overnight.

What you actually lose by not paying: convenience, and the social gravity of
chess.com's ecosystem (friends, Titled Tuesday, the rating pool you already
play in). You can keep playing there for free and do all analysis elsewhere.

Second framing, specific to you: per `Personalized Plan.md`, your bottleneck is
**move-speed discipline and blunder-checking**, not tactical knowledge or
opening theory. Diamond's headline features (unlimited lessons, unlimited
puzzles, courses) target the things you are *already good at*. Paying would buy
you almost nothing. The free stack below targets the actual problem better than
Diamond does.

## What the free tier actually gates

| Feature | Free tier limit |
| --- | --- |
| Game Review | ~1 per day |
| Puzzles | 3 per day |
| Puzzle Rush / Battle / Streak | 1 attempt per day |
| Lessons | ~1 per day |
| Insights (advanced stats) | Diamond only |
| Opening Explorer | Premium only |
| Personal AI Coach | Diamond only |
| Ads | Yes |

## Feature-by-feature replacement map

### 1. Unlimited Game Review (the main one)

**Best web replacement: [Chesskit](https://github.com/GuillaumeSD/Chesskit)** —
`chesskit.org`, AGPL-3.0, ~407 stars, actively developed. Imports games directly
by chess.com or Lichess username, runs Stockfish in-browser, and produces the
same move classifications (Brilliant / Great / Good / Inaccuracy / Mistake /
Blunder) plus an accuracy score and eval graph. Self-hostable via Docker if you
want it offline and unlimited.

**Runner-up: [WintrChess](https://github.com/wintrcat/wintrchess)** —
`wintrchess.com`, GPL-3.0. This is the rebuilt successor to the very popular
[freechess](https://github.com/WintrCat/freechess) "Game Report" (now abandoned
— do not clone that one). Same idea, arguably nicer classification tuning.

**Also:** [Brilliant-Chess](https://github.com/wdeloo/Brilliant-Chess) (desktop
app, closest visual clone of the chess.com review UI) and
[OpenChess-Insights](https://github.com/LinkAnJarad/OpenChess-Insights)
(Stockfish NNUE + plain-language move explanations, runs locally).

**Best of all, for you: you already own this.** `tools/engine_review.py` is a
Game Review that runs on your own machine with no daily cap and no depth cap.
It currently finds blunders; adding move classification + accuracy percentages
is maybe 60 lines. See "Plugging into your toolkit" below.

### 2. "Deeper engine analysis" (Diamond's deep mode)

Not a real advantage. Diamond gives you a somewhat deeper cloud eval. Your local
[Stockfish](https://stockfishchess.org/download/) NNUE in `tools/stockfish/`
will go to depth 30+ on a position and can grind a full game overnight — far
past anything the web UI offers at any price tier. Diamond's edge here is
latency, not strength.

### 3. Unlimited puzzles + Puzzle Rush / Battle / Streak

[Lichess](https://lichess.org/training) — unlimited, free, forever, no tiers.
Direct one-to-one mapping:

| Chess.com | Lichess equivalent |
| --- | --- |
| Puzzles | Puzzle Training (unlimited) |
| Puzzle Rush | Puzzle Storm |
| Puzzle Battle | Puzzle Racer |
| Puzzle Streak | Puzzle Streak |

Lichess's puzzle set is ~6 million positions, larger than chess.com's, generated
by re-analyzing 600M real games with Stockfish NNUE and auto-tagged by theme.

### 4. "Personalized tactical recommendations" (Diamond)

This is where free beats paid outright. The **entire Lichess puzzle database is
downloadable under CC0**:
[`database.lichess.org/lichess_db_puzzle.csv.zst`](https://database.lichess.org/)
— ~6M rows, with `Rating`, `Themes`, `Popularity`, and `OpeningTags` columns.

That means you can build a drill deck filtered to *your* measured weaknesses
rather than chess.com's generic recommender. You already have
`data/blunders.json` — the themes of your actual blunders become the filter.
Chess.com cannot do this for you at any price.

### 5. Insights (advanced statistics)

- **[Lichess Insights](https://lichess.org/insights)** — free, and deeper than
  chess.com's version. Arbitrary dimension/metric pivots over your whole game
  history (accuracy by time-of-day, by clock remaining, by piece moved, etc.).
  Covers Lichess games only.
- **[ChessMonitor](https://www.chessmonitor.com/)** — links both your chess.com
  and Lichess accounts, gives opening explorer over your own games, progress
  tracking, opponent stats, and a FIDE Elo estimate. Free.
- **Your own `tools/analyze.py`** already produces results/openings/terminations/
  clock-usage stats over your real chess.com history. This is the Insights
  replacement that actually covers your games.

### 6. Opening Explorer + Masters database

[Lichess Opening Explorer](https://lichess.org/analysis) is free and strictly
larger: a Masters DB of OTB titled-player games plus a Lichess DB of billions of
online games, filterable by rating band and time control — so you can see what
players *at your exact level* actually play, which chess.com's explorer cannot
do. It has a [free public API](https://lichess.org/api#tag/Opening-Explorer),
no key required.

Also free: [365Chess](https://www.365chess.com/opening.php) for a classical
opening tree, and [OpeningTree](https://www.openingtree.com/) which builds a
repertoire tree from *your own* chess.com/Lichess games and lets you prep
against a named opponent's history.

### 7. Repertoire building and training (Diamond-adjacent)

**[En Croissant](https://github.com/franciscoBSalgueiro/en-croissant)** —
GPL-3.0, ~1.8k stars, Rust/Tauri desktop app for Windows. This is the single
highest-value install on this page. It gives you, in one native app:

- import + auto-sync of your chess.com and Lichess games into one local database
- multi-engine analysis (any UCI engine, so your Stockfish drops right in)
- full-game accuracy reports
- repertoire preparation **with spaced-repetition training**
- exact and partial position search across the database

That covers Game Review, Insights, Explorer, and repertoire drilling in one
offline tool with no daily limits.

Lighter web alternatives: [Repertree](https://repertree.com/) (free repertoire
builder with spaced repetition and Stockfish) and Lichess Studies (free,
shareable, unlimited, with engine).

### 8. Unlimited Lessons / courses / video library

- **[Lichess Practice](https://lichess.org/practice)** — structured, free,
  interactive lesson tracks (checkmate patterns, piece endgames, tactical
  motifs, positional themes). This is the closest structural match to
  chess.com Lessons.
- **[Chessable](https://www.chessable.com/)** — the "Short & Sweet" courses are
  free and use the same MoveTrainer spaced repetition as the paid ones.
- **YouTube** — the honest replacement for the video library. For your exact
  rating band, Daniel Naroditsky's rating-climb speedrun series is the standard
  recommendation and is free.
- You already have `Chess Fundamentals` (Capablanca) in this folder, plus the
  book ladder in `../Books & Fundamentals.md`.

### 9. Drills and Endgames (premium tab)

Lichess Practice covers the endgame drill set. For perfect play, the
[Lichess tablebase API](https://tablebase.lichess.ovh/) gives free 7-piece
Syzygy results — literally solved endgames, better than any drill.

### 10. Personal AI Coach (Diamond)

You are currently using a strictly better version of this. Claude Code plus a
local Stockfish plus your own PGN history is a coach that reads your actual
games, remembers your plan across sessions, and writes you code. Chess.com's
coach is a canned LLM over a single game.

If you want a packaged version: [Arrakis Engine](https://github.com/bleongcw/Arrakis_Engine)
(Stockfish + Claude/GPT/Gemini, tracks patterns across games),
[stockfish-coach](https://github.com/renaissancebro/stockfish-coach), or
[Chess King](https://github.com/Iamsdt/chess) (Stockfish 18 + LLM, browser).

### 11. Play against bots at your level

[Maia](https://github.com/CSSLab/maia-chess) — a neural engine trained to play
*like a human of a given rating*, not to play well. It makes the mistakes humans
make, so practice against it transfers. Play it free on Lichess as
[maia1](https://lichess.org/@/maia1) (~1100), maia5 (~1500), maia9 (~1900), or
run the weights locally. There is also [Maia-2](https://github.com/CSSLab/maia2)
covering 600–2600 in one model. Chess.com's bots do not do this well.

### 12. No ads

uBlock Origin. Or just play on Lichess, which has never had ads.

### 13. Not replicable, and not worth caring about

Custom flair, priority support, timeout protection for daily games, and the
chess.com social graph. If you need Titled Tuesday you need an account there —
but a *free* one plays in it.

## Recommended stack

**Tier 0 — 5 minutes, covers ~90% of Diamond's value**
1. Make a Lichess account. Unlimited puzzles, analysis, insights, explorer, studies, practice.
2. Install uBlock Origin.
3. Bookmark `chesskit.org` for one-click Game Review on any chess.com game.

**Tier 1 — one evening, exceeds Diamond**
4. Install [En Croissant](https://encroissant.org/), point it at your existing
   `tools/stockfish/` binary, and sync your chess.com account into it.
5. Use its spaced-repetition repertoire trainer instead of chess.com Lessons.

**Tier 2 — you're already halfway there**
6. Extend `tools/` as below. This is the part no subscription can sell you,
   because it is tuned to your own measured weaknesses.

## Plugging into your existing toolkit

Built, 2026-08-08. See the README table for the full command list.

- **`tools/engine_review.py`** — now a full Game Review: per-move classification
  (brilliant / great / best / excellent / good / inaccuracy / mistake /
  blunder), per-move and per-game accuracy on the Lichess formula, and the
  existing blunder log. Brilliant is gated behind a real static-exchange
  evaluation, so it means an actual sacrifice rather than any move that happens
  to be attacked. No daily cap, and you choose the depth.
- **`tools/puzzles.py`** — replays each of your blunders to ask what the
  opponent was handed (mate, hanging piece, fork, pin, skewer), then streams the
  304MB CC0 Lichess puzzle database and keeps only puzzles matching those
  motifs in your rating band. Drill them in the terminal, mixed with your own
  blunders as puzzles. This is the Diamond "personalised tactics" feature built
  from measured errors rather than a generic recommender.
- **`tools/explorer.py`** — builds an opening tree from your own games and finds
  lines you repeat and lose from, then compares against what your rating band
  plays.

One caveat on the last one: the Lichess opening explorer API
(`explorer.lichess.org`) has been returning 401 site-wide during this work —
[a known outage](https://github.com/lichess-org/lila/issues/19610), not
something on your end. Verified it fails from a real browser on lichess.org
itself, so it is not a client problem. `explorer.py` handles this: it reports
your own tree regardless, and falls back to the Lichess cloud-eval API (which
works) to judge whether your usual moves are objectively sound. The pool
columns will fill in on their own once the service returns; responses cache to
`data/explorer_cache.json`.

Standing caveat, unchanged: per the plan, all of this is secondary to the
move-speed discipline work. The tooling tells you what you are doing wrong; it
does not make you slow down before moving.

## Bottom line

$0 replicates Diamond and beats it on puzzle volume, database size, statistical
depth, engine depth, and personalization. It loses on convenience and on
chess.com's social features. For your specific bottleneck, Diamond would have
been ~$100/yr spent on the wrong problem.

## Sources

- [Chess.com: what each membership level gets you](https://support.chess.com/en/articles/8562418-what-does-each-level-of-premium-membership-get-me)
- [Chess.com: why am I limited to three puzzles per day](https://support.chess.com/en/articles/8652730-why-am-i-limited-to-only-three-puzzles-per-day)
- [Chesskit (GitHub)](https://github.com/GuillaumeSD/Chesskit)
- [WintrChess (GitHub)](https://github.com/wintrcat/wintrchess) / [freechess, archived](https://github.com/WintrCat/freechess)
- [Brilliant-Chess (GitHub)](https://github.com/wdeloo/Brilliant-Chess)
- [OpenChess-Insights (GitHub)](https://github.com/LinkAnJarad/OpenChess-Insights)
- [En Croissant (GitHub)](https://github.com/franciscoBSalgueiro/en-croissant) / [docs](https://encroissant.org/docs/)
- [Lichess open database](https://database.lichess.org/)
- [Maia Chess (GitHub)](https://github.com/CSSLab/maia-chess) / [Maia-2](https://github.com/CSSLab/maia2)
- [ChessMonitor](https://www.chessmonitor.com/)
- [OpeningTree](https://www.openingtree.com/) / [Repertree](https://repertree.com/)
- [Arrakis Engine](https://github.com/bleongcw/Arrakis_Engine) / [stockfish-coach](https://github.com/renaissancebro/stockfish-coach) / [Chess King](https://github.com/Iamsdt/chess)
- [Chess.com alternatives — free tools for real improvement](https://cassandrachess.com/learn/chess-com-alternatives)

# Tactics profile — built from your own blunders
Generated 2026-08-09 from 249 blunders in data/blunders.json.

Each blunder was replayed to ask what the opponent was handed. A blunder can carry several tags.

## What your blunders give away

| Motif | Blunders | Share | Of those, played in under 5s |
| --- | --- | --- | --- |
| middlegame | 193 | 78% | 36 (19%) |
| hangingPiece | 66 | 27% | 17 (26%) |
| pin | 63 | 25% | 11 (17%) |
| opening | 39 | 16% | 10 (26%) |
| fork | 24 | 10% | 6 (25%) |
| endgame | 17 | 7% | 10 (59%) |
| skewer | 13 | 5% | 2 (15%) |
| mate | 9 | 4% | 4 (44%) |

## Drill set this implies

Top motifs: hangingPiece, pin, fork, skewer.
Lichess themes to filter on: `capturingDefender,doubleCheck,fork,hangingPiece,pin,skewer,xRayAttack`

```
python tools/puzzles.py fetch
python tools/puzzles.py drill 20
```

Read the rushed column before the volume column. A motif you only miss when moving in under five seconds is a discipline problem, and more puzzles will not fix it.
"""Download all chess.com games for a player into data/games/ (one JSON per month).

Incremental: past months already on disk are skipped; the current month is
always re-fetched since it can still grow. Uses only the standard library.

Usage: python tools/fetch_games.py [username]
"""

import json
import sys
import time
import urllib.request
from datetime import date, timezone, datetime
from pathlib import Path

USERNAME = sys.argv[1] if len(sys.argv) > 1 else "joshuadardashti"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "games"
HEADERS = {"User-Agent": "chess-improvement-toolkit (jsdardashti@gmail.com)"}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    archives = get_json(
        f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
    )["archives"]

    this_month = date.today().strftime("%Y-%m")
    fetched = skipped = total_games = 0

    for url in archives:
        year, month = url.rsplit("/", 2)[-2:]
        stamp = f"{year}-{month}"
        out = OUT_DIR / f"{stamp}.json"
        if out.exists() and stamp != this_month:
            skipped += 1
            total_games += len(json.loads(out.read_text(encoding="utf-8"))["games"])
            continue
        data = get_json(url)
        out.write_text(json.dumps(data, indent=1), encoding="utf-8")
        n = len(data["games"])
        total_games += n
        fetched += 1
        print(f"{stamp}: {n} games")
        time.sleep(0.5)  # stay polite to the public API

    meta = {
        "username": USERNAME,
        "last_sync": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "months": fetched + skipped,
        "total_games": total_games,
    }
    (ROOT / "data" / "sync_meta.json").write_text(
        json.dumps(meta, indent=1), encoding="utf-8"
    )
    print(f"Done: {total_games} games across {fetched + skipped} months "
          f"({fetched} fetched, {skipped} cached).")


if __name__ == "__main__":
    main()

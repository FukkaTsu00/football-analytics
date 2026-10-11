"""Create small test fixtures from the first bronze run on disk.

Keeps 10 articles per source and cuts the text to 300 characters: enough to test
the real data shapes, without republishing whole articles in the repo.

Run from the project root:  python scripts/make_fixtures.py
"""

import json
from pathlib import Path

runs = sorted(Path("data/lake/bronze").glob("date=*/run=*"))
if not runs:
    raise SystemExit("No bronze data found: run 'python -m football_analytics scrape all' first")

out_dir = Path("tests/fixtures")
out_dir.mkdir(parents=True, exist_ok=True)

for source in ("bbc", "goal"):
    articles = json.loads((runs[0] / f"{source}.json").read_text(encoding="utf-8"))[:10]
    sample = [{**a, "content": (a.get("content") or "")[:300]} for a in articles]
    (out_dir / f"{source}.json").write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{source}: {len(sample)} articles -> {out_dir / f'{source}.json'}")

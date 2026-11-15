"""One scheduled forecast cycle (spec §5): pick the due run, wait for its inputs,
build, publish, prune. Run by .github/workflows/forecast.yml."""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from .build import build_run
from .publish import Store, prune_runs, publish_run, published_run
from .sources.openmeteo import RunIncomplete

READY_AFTER = timedelta(hours=5, minutes=15)  # inputs are usually all published by then
KEEP = timedelta(days=3)


def due_run(now: datetime) -> datetime:
    """The newest 00/06/12/18Z run whose inputs should be out by `now`."""
    t = now - READY_AFTER
    return t.replace(hour=t.hour - t.hour % 6, minute=0, second=0, microsecond=0)


def cycle(now: datetime, cache_dir: Path, out_dir: Path, store: Store, *, run: datetime | None = None,
          build: Callable | None = None, sleep: Callable[[float], None] = time.sleep,
          clock: Callable[[], float] = time.monotonic,
          wait: timedelta = timedelta(minutes=90), poll: timedelta = timedelta(minutes=10),
          stations: list[dict] | None = None) -> int:
    """0: published (or already current); 2: inputs still incomplete `wait` after the first
    attempt (wall clock, build attempts included)."""
    build = build or build_run
    run = run or due_run(now)
    current = published_run(store)
    if current is not None and current >= run:
        print(f"up to date: {current:%Y%m%d%H} is published (due {run:%Y%m%d%H})")
        return 0
    start = clock()
    while True:
        try:
            folder = build(run, cache_dir, out_dir, prune=True, **({"stations": stations} if stations else {}))
            break
        except RunIncomplete as exc:
            waited = clock() - start
            if waited >= wait.total_seconds():
                print(f"not built: {exc} (waited {int(waited // 60)} min)", file=sys.stderr)
                return 2
            print(f"waiting: {exc}", file=sys.stderr)
            sleep(min(poll.total_seconds(), wait.total_seconds() - waited))
    publish_run(store, folder, run, datetime.now(timezone.utc))
    gone = prune_runs(store, keep_from=run - KEEP)
    print(f"published {run:%Y%m%d%H}" + (f"; pruned {', '.join(gone)}" if gone else ""))
    return 0

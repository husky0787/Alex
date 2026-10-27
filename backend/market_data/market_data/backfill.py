"""Restartable universe backfill, checkpointed by verified persisted coverage."""
from datetime import date, datetime, timezone

from .calendar import history_window
from .universe import SYMBOLS, require_symbol


class HistoryBackfill:
    def __init__(self, pipeline, repository, *, clock=None):
        self.pipeline = pipeline
        self.repository = repository
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run(self, start=None, end=None, *, symbols=SYMBOLS, on_progress=None):
        now = self.clock()
        start, end = history_window(now, start, end)
        symbols = tuple(dict.fromkeys(require_symbol(symbol) for symbol in symbols))
        if not symbols:
            raise ValueError("Select at least one supported symbol")
        results = []
        for symbol in symbols:
            history = self.repository.history(symbol, start, end, as_of=now)
            run, error, action = None, None, "skipped"
            if history["missing_dates"]:
                interrupted = self.repository.interrupted_run(symbol, start, end)
                if interrupted:
                    action = "resumed"
                    try:
                        run = self.pipeline.resume(interrupted["id"])
                    except ValueError:
                        # An active owner or a future retry time remains pending.
                        # Never start a competing recovery/fresh run in this pass.
                        error = "recovery_pending"
                    history = self.repository.history(symbol, start, end, as_of=now)
                if history["missing_dates"] and not error and (not run or run["status"] == "succeeded"):
                    action = "resumed_and_fetched" if run else "fetched"
                    run = self.pipeline.run(symbol, date.fromisoformat(history["missing_dates"][0]),
                                            date.fromisoformat(history["missing_dates"][-1]))
                history = self.repository.history(symbol, start, end, as_of=now)
            complete = history["coverage"] in ("complete", "not_due")
            row = {"symbol": symbol, "action": action, "coverage": history["coverage"],
                   "expected_count": history["expected_count"], "available_count": history["available_count"],
                   "missing_dates": history["missing_dates"], "run_id": run["id"] if run else None,
                   "run_status": run["status"] if run else None,
                   "error_code": error or (run["error_code"] if run else None), "complete": complete}
            results.append(row)
            if on_progress:
                on_progress(row)
        return {"status": "succeeded" if all(row["complete"] for row in results) else "partial",
                "from_date": start.isoformat(), "to_date": end.isoformat(), "as_of": now.isoformat(),
                "source": "massive", "symbols": results}

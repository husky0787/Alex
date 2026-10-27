"""Daily REST bars, compatible with the existing Polygon account direction."""
import httpx
import math
import time


class MassiveDailyProvider:
    source = "massive"

    def __init__(self, api_key: str, client: httpx.Client, *, min_interval=0, monotonic=None, sleep=None):
        if not api_key or not api_key.strip():
            raise ValueError("Set POLYGON_API_KEY or MASSIVE_API_KEY")
        self.api_key = api_key
        self.client = client
        if not math.isfinite(min_interval) or min_interval < 0:
            raise ValueError("Request interval must be finite and nonnegative")
        self.min_interval = min_interval
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.next_request = 0.0

    def fetch(self, symbol, start, end):
        # The CLI shares this provider across symbols and retries. Other
        # processes using the same key may still produce a provider-side 429.
        delay = max(0, self.next_request - self.monotonic())
        if delay:
            self.sleep(delay)
        self.next_request = self.monotonic() + self.min_interval
        return self.client.get(
            f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30, follow_redirects=False,
        )

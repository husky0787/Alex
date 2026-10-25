"""Daily REST bars, compatible with the existing Polygon account direction."""
import httpx


class MassiveDailyProvider:
    source = "massive"

    def __init__(self, api_key: str, client: httpx.Client):
        if not api_key or not api_key.strip():
            raise ValueError("Set POLYGON_API_KEY or MASSIVE_API_KEY")
        self.api_key = api_key
        self.client = client

    def fetch(self, symbol, start, end):
        return self.client.get(
            f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": 50000},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30, follow_redirects=False,
        )

"""
News fetchers for sentiment analysis. Same interface/failover pattern as
app/marketdata's provider adapters — one dataclass, multiple real sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx


@dataclass(frozen=True)
class NewsHeadline:
    title: str
    source: str
    published_at: datetime
    url: str


class NewsFetchError(Exception):
    pass


class NewsAPIClient:
    """
    Real REST API: https://newsapi.org/docs/endpoints/everything
    Free tier: developer plan only (no commercial use), 100 requests/day, articles
    delayed ~24h — fine for a portfolio project, not for live trading sentiment at
    any real scale. Check newsapi.org/pricing before relying on specific limits.
    """

    _BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def fetch_headlines(self, query: str, page_size: int = 20) -> list[NewsHeadline]:
        resp = await self._client.get(
            self._BASE_URL,
            params={
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": page_size,
                "apiKey": self._api_key,
            },
        )
        if resp.status_code != 200:
            raise NewsFetchError(f"NewsAPI request failed: {resp.status_code} {resp.text}")

        payload = resp.json()
        return [
            NewsHeadline(
                title=a["title"],
                source=a.get("source", {}).get("name", "unknown"),
                published_at=datetime.fromisoformat(a["publishedAt"].replace("Z", "+00:00")),
                url=a["url"],
            )
            for a in payload.get("articles", [])
            if a.get("title") and a["title"] != "[Removed]"
        ]


class FinnhubNewsClient:
    """
    Real REST API: https://finnhub.io/docs/api/company-news / /news
    Uses the general market-news endpoint for forex-relevant headlines (Finnhub's
    free tier doesn't segment forex-specific news the way it does company news).
    """

    _BASE_URL = "https://finnhub.io/api/v1/news"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=15.0)

    async def fetch_headlines(self, category: str = "forex", limit: int = 20) -> list[NewsHeadline]:
        resp = await self._client.get(self._BASE_URL, params={"category": category, "token": self._api_key})
        if resp.status_code != 200:
            raise NewsFetchError(f"Finnhub news request failed: {resp.status_code} {resp.text}")

        articles = resp.json()[:limit]
        return [
            NewsHeadline(
                title=a["headline"],
                source=a.get("source", "unknown"),
                published_at=datetime.fromtimestamp(a["datetime"], tz=timezone.utc),
                url=a.get("url", ""),
            )
            for a in articles
            if a.get("headline")
        ]


async def fetch_headlines_with_failover(
    query: str, newsapi_key: str | None, finnhub_key: str | None, limit: int = 20
) -> tuple[list[NewsHeadline], str]:
    """Tries NewsAPI first (query-targeted), falls back to Finnhub's general forex feed."""
    if newsapi_key:
        try:
            client = NewsAPIClient(newsapi_key)
            headlines = await client.fetch_headlines(query, page_size=limit)
            if headlines:
                return headlines, "newsapi"
        except NewsFetchError:
            pass

    if finnhub_key:
        client = FinnhubNewsClient(finnhub_key)
        headlines = await client.fetch_headlines(limit=limit)
        return headlines, "finnhub"

    raise NewsFetchError("no news provider configured (set NEWSAPI_KEY or FINNHUB_NEWS_KEY)")

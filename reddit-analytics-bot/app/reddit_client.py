import asyncio
import json as json_lib
from urllib.parse import urlencode

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.models import SearchItem, SearchParams

COMMENTS_PER_POST = 5
BASE_URL = "https://old.reddit.com"
RETRY_STATUS_CODES = {403, 429}
RETRY_DELAYS = (1.0, 3.0)

# fetch() executed inside a real headless Chromium tab: genuine TLS/JS
# fingerprint, not just spoofed headers on a Python HTTP client.
_FETCH_JS = """async (url) => {
    try {
        const res = await fetch(url, { headers: { "Accept": "application/json" } });
        return { status: res.status, body: await res.text() };
    } catch (e) {
        return { status: 0, body: String(e) };
    }
}"""


class RedditUnavailableError(Exception):
    pass


class RedditClient:
    def __init__(
        self, playwright: Playwright, browser: Browser, context: BrowserContext, page: Page
    ) -> None:
        self._playwright = playwright
        self._browser = browser
        self._context = context
        self._page = page
        self._lock = asyncio.Lock()

    async def fetch(self, url: str) -> tuple[int, str]:
        async with self._lock:
            result = await self._page.evaluate(_FETCH_JS, url)
        return result["status"], result["body"]

    async def aclose(self) -> None:
        await self._context.close()
        await self._browser.close()
        await self._playwright.stop()


async def make_reddit_client() -> RedditClient:
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(locale="en-US")
    page = await context.new_page()
    await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
    return RedditClient(playwright, browser, context, page)


async def _get_json(reddit: RedditClient, path: str, params: dict):
    url = f"{BASE_URL}{path}?{urlencode(params)}"
    last_error: Exception | None = None
    for delay in (0.0, *RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        status, body = await reddit.fetch(url)
        if status == 0 or status in RETRY_STATUS_CODES:
            last_error = RuntimeError(f"HTTP {status}: {body[:200]}")
            continue
        if status >= 400:
            raise RedditUnavailableError(f"Reddit returned HTTP {status} for this request.")
        try:
            return json_lib.loads(body)
        except ValueError as exc:
            raise RedditUnavailableError(
                "Reddit returned an unexpected (non-JSON) response."
            ) from exc

    raise RedditUnavailableError(
        "Reddit is blocking requests right now (403/429). Try again in a couple of minutes."
    ) from last_error


async def _top_comments(reddit: RedditClient, permalink: str) -> list[dict]:
    try:
        _, comments_listing = await _get_json(
            reddit,
            f"{permalink}.json",
            {"sort": "top", "limit": COMMENTS_PER_POST},
        )
    except Exception:
        return []

    comments = [
        child["data"]
        for child in comments_listing.get("data", {}).get("children", [])
        if child.get("kind") == "t1"
    ]
    comments.sort(key=lambda c: c.get("score", 0), reverse=True)
    return comments[:COMMENTS_PER_POST]


async def search_reddit(
    reddit: RedditClient, params: SearchParams
) -> list[SearchItem]:
    subreddit_name = "+".join(params.subreddits) if params.subreddits else "all"

    listing = await _get_json(
        reddit,
        f"/r/{subreddit_name}/search.json",
        {
            "q": params.query,
            "sort": "relevance",
            "t": params.time_filter,
            "limit": params.limit,
            "restrict_sr": "on" if params.subreddits else "off",
        },
    )

    items: list[SearchItem] = []
    for child in listing.get("data", {}).get("children", []):
        post = child.get("data", {})
        if child.get("kind") != "t3":
            continue

        permalink = post.get("permalink", "")
        group = f"r/{post.get('subreddit', '')}"
        items.append(
            SearchItem(
                kind="post",
                source="reddit",
                item_id=post.get("id", ""),
                group=group,
                author=post.get("author") or "[deleted]",
                text=post.get("title", "")
                + ("\n\n" + post["selftext"] if post.get("selftext") else ""),
                score=post.get("score", 0),
                permalink=f"https://www.reddit.com{permalink}",
                created_utc=post.get("created_utc", 0.0),
            )
        )

        for comment in await _top_comments(reddit, permalink):
            body = comment.get("body")
            if not body:
                continue
            items.append(
                SearchItem(
                    kind="comment",
                    source="reddit",
                    item_id=comment.get("id", ""),
                    group=group,
                    author=comment.get("author") or "[deleted]",
                    text=body,
                    score=comment.get("score", 0),
                    permalink=f"https://www.reddit.com{comment.get('permalink', permalink)}",
                    created_utc=comment.get("created_utc", 0.0),
                )
            )

    return items

import asyncio
from dataclasses import dataclass, field

import httpx

from app.config import Config

COMMENTS_PER_POST = 5
BASE_URL = "https://old.reddit.com"
RETRY_STATUS_CODES = {403, 429}
RETRY_DELAYS = (1.0, 3.0)


class RedditUnavailableError(Exception):
    pass


@dataclass
class RedditItem:
    kind: str  # "post" or "comment"
    reddit_id: str
    subreddit: str
    author: str
    text: str
    score: int
    permalink: str
    created_utc: float


@dataclass
class SearchParams:
    query: str
    subreddits: list[str] = field(default_factory=list)
    time_filter: str = "all"  # hour, day, week, month, year, all
    limit: int = 50


def make_reddit_client(config: Config) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=BASE_URL,
        headers={
            "User-Agent": config.reddit_user_agent,
            "Accept": "application/json",
        },
        timeout=15.0,
    )


async def _get_json(reddit: httpx.AsyncClient, path: str, params: dict) -> dict:
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0, *RETRY_DELAYS)):
        if delay:
            await asyncio.sleep(delay)
        try:
            response = await reddit.get(path, params=params)
            if response.status_code in RETRY_STATUS_CODES:
                last_error = httpx.HTTPStatusError(
                    f"{response.status_code} {response.reason_phrase}",
                    request=response.request,
                    response=response,
                )
                continue
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            last_error = exc

    raise RedditUnavailableError(
        "Reddit сейчас блокирует запросы (403/429). Попробуй ещё раз через пару минут."
    ) from last_error


async def _top_comments(
    reddit: httpx.AsyncClient, permalink: str
) -> list[dict]:
    try:
        _, comments_listing = await _get_json(
            reddit,
            f"{permalink}.json",
            params={"sort": "top", "limit": COMMENTS_PER_POST},
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
    reddit: httpx.AsyncClient, params: SearchParams
) -> list[RedditItem]:
    subreddit_name = "+".join(params.subreddits) if params.subreddits else "all"

    listing = await _get_json(
        reddit,
        f"/r/{subreddit_name}/search.json",
        params={
            "q": params.query,
            "sort": "relevance",
            "t": params.time_filter,
            "limit": params.limit,
            "restrict_sr": "on" if params.subreddits else "off",
        },
    )

    items: list[RedditItem] = []
    for child in listing.get("data", {}).get("children", []):
        post = child.get("data", {})
        if child.get("kind") != "t3":
            continue

        permalink = post.get("permalink", "")
        items.append(
            RedditItem(
                kind="post",
                reddit_id=post.get("id", ""),
                subreddit=post.get("subreddit", ""),
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
                RedditItem(
                    kind="comment",
                    reddit_id=comment.get("id", ""),
                    subreddit=post.get("subreddit", ""),
                    author=comment.get("author") or "[deleted]",
                    text=body,
                    score=comment.get("score", 0),
                    permalink=f"https://www.reddit.com{comment.get('permalink', permalink)}",
                    created_utc=comment.get("created_utc", 0.0),
                )
            )

    return items

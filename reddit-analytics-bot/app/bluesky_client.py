from datetime import datetime, timezone

import httpx

from app.models import SearchItem, SearchParams, TIME_FILTER_SECONDS

SEARCH_URL = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"


def _post_url(handle: str, uri: str) -> str:
    rkey = uri.rstrip("/").split("/")[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def _parse_time(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


async def search_bluesky(
    client: httpx.AsyncClient, params: SearchParams
) -> list[SearchItem]:
    query_params = {"q": params.query, "sort": "top", "limit": min(params.limit, 100)}
    seconds = TIME_FILTER_SECONDS.get(params.time_filter)
    if seconds:
        since = datetime.now(timezone.utc).timestamp() - seconds
        query_params["since"] = datetime.fromtimestamp(
            since, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    response = await client.get(SEARCH_URL, params=query_params, timeout=15.0)
    response.raise_for_status()
    data = response.json()

    items: list[SearchItem] = []
    for post in data.get("posts", []):
        author = post.get("author") or {}
        handle = author.get("handle") or "unknown"
        record = post.get("record") or {}

        items.append(
            SearchItem(
                kind="comment" if record.get("reply") else "post",
                source="bluesky",
                item_id=post.get("cid", ""),
                group="Bluesky",
                author=handle,
                text=record.get("text", ""),
                score=post.get("likeCount") or 0,
                permalink=_post_url(handle, post.get("uri", "")),
                created_utc=_parse_time(record.get("createdAt", "")),
            )
        )

    return items

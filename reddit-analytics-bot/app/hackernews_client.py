import time

import httpx

from app.models import SearchItem, SearchParams

SEARCH_URL = "https://hn.algolia.com/api/v1/search"

TIME_FILTER_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
    "all": None,
}


def _item_url(object_id: str) -> str:
    return f"https://news.ycombinator.com/item?id={object_id}"


async def _search(
    client: httpx.AsyncClient, query: str, tags: str, limit: int, time_filter: str
) -> list[dict]:
    query_params = {"query": query, "tags": tags, "hitsPerPage": limit}
    seconds = TIME_FILTER_SECONDS.get(time_filter)
    if seconds:
        cutoff = int(time.time()) - seconds
        query_params["numericFilters"] = f"created_at_i>{cutoff}"

    response = await client.get(SEARCH_URL, params=query_params, timeout=15.0)
    response.raise_for_status()
    return response.json().get("hits", [])


async def search_hackernews(
    client: httpx.AsyncClient, params: SearchParams
) -> list[SearchItem]:
    items: list[SearchItem] = []

    for hit in await _search(client, params.query, "story", params.limit, params.time_filter):
        object_id = hit.get("objectID", "")
        text = hit.get("title") or hit.get("story_title") or ""
        if hit.get("story_text"):
            text += "\n\n" + hit["story_text"]
        items.append(
            SearchItem(
                kind="post",
                source="hackernews",
                item_id=object_id,
                group="Hacker News",
                author=hit.get("author") or "[unknown]",
                text=text,
                score=hit.get("points") or 0,
                permalink=_item_url(object_id),
                created_utc=hit.get("created_at_i") or 0.0,
            )
        )

    for hit in await _search(client, params.query, "comment", params.limit, params.time_filter):
        object_id = hit.get("objectID", "")
        body = hit.get("comment_text")
        if not body:
            continue
        items.append(
            SearchItem(
                kind="comment",
                source="hackernews",
                item_id=object_id,
                group="Hacker News",
                author=hit.get("author") or "[unknown]",
                text=body,
                score=hit.get("points") or 0,
                permalink=_item_url(object_id),
                created_utc=hit.get("created_at_i") or 0.0,
            )
        )

    return items

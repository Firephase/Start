import time

import httpx

from app.models import SearchItem, SearchParams, TIME_FILTER_SECONDS

SEARCH_URL = "https://api.stackexchange.com/2.3/search/advanced"
DEFAULT_SITE = "stackoverflow"


async def search_stackexchange(
    client: httpx.AsyncClient,
    params: SearchParams,
    api_key: str | None = None,
    site: str = DEFAULT_SITE,
) -> list[SearchItem]:
    query_params = {
        "q": params.query,
        "site": site,
        "sort": "relevance",
        "order": "desc",
        "pagesize": min(params.limit, 100),
    }
    seconds = TIME_FILTER_SECONDS.get(params.time_filter)
    if seconds:
        query_params["fromdate"] = int(time.time()) - seconds
    if api_key:
        query_params["key"] = api_key

    response = await client.get(SEARCH_URL, params=query_params, timeout=15.0)
    response.raise_for_status()
    data = response.json()

    items: list[SearchItem] = []
    for question in data.get("items", []):
        owner = question.get("owner") or {}
        items.append(
            SearchItem(
                kind="post",
                source="stackexchange",
                item_id=str(question.get("question_id", "")),
                group=site,
                author=owner.get("display_name") or "[deleted]",
                text=question.get("title", ""),
                score=question.get("score", 0),
                permalink=question.get("link", ""),
                created_utc=question.get("creation_date", 0.0),
            )
        )

    return items

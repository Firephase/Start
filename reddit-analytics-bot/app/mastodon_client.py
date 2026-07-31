import re
import time
from datetime import datetime
from html import unescape

import httpx

from app.models import SearchItem, SearchParams, TIME_FILTER_SECONDS

DEFAULT_INSTANCE = "https://mastodon.social"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return unescape(_TAG_RE.sub(" ", html)).strip()


def _parse_time(value: str) -> float:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


async def search_mastodon(
    client: httpx.AsyncClient,
    params: SearchParams,
    access_token: str,
    instance: str = DEFAULT_INSTANCE,
) -> list[SearchItem]:
    response = await client.get(
        f"{instance}/api/v2/search",
        params={"q": params.query, "type": "statuses", "limit": min(params.limit, 40)},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15.0,
    )
    response.raise_for_status()
    data = response.json()

    group = instance.removeprefix("https://").removeprefix("http://")

    cutoff = None
    seconds = TIME_FILTER_SECONDS.get(params.time_filter)
    if seconds:
        cutoff = time.time() - seconds

    items: list[SearchItem] = []
    for status in data.get("statuses", []):
        created_utc = _parse_time(status.get("created_at", ""))
        if cutoff and created_utc and created_utc < cutoff:
            continue

        account = status.get("account") or {}
        items.append(
            SearchItem(
                kind="comment" if status.get("in_reply_to_id") else "post",
                source="mastodon",
                item_id=str(status.get("id", "")),
                group=group,
                author=account.get("acct") or account.get("username") or "[unknown]",
                text=_strip_html(status.get("content", "")),
                score=(status.get("favourites_count") or 0)
                + (status.get("reblogs_count") or 0),
                permalink=status.get("url") or status.get("uri", ""),
                created_utc=created_utc,
            )
        )

    return items

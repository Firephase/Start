from dataclasses import dataclass

TIME_FILTER_SECONDS = {
    "hour": 3600,
    "day": 86400,
    "week": 604800,
    "month": 2592000,
    "year": 31536000,
    "all": None,
}


@dataclass
class SearchItem:
    kind: str  # "post" or "comment"
    source: str  # "hackernews", "stackexchange", "bluesky", "mastodon"
    item_id: str
    group: str  # display label: "Hacker News", "stackoverflow", "Bluesky", ...
    author: str
    text: str
    score: int
    permalink: str
    created_utc: float


@dataclass
class SearchParams:
    query: str
    time_filter: str = "all"  # hour, day, week, month, year, all
    limit: int = 50

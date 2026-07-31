from dataclasses import dataclass


@dataclass
class SearchItem:
    kind: str  # "post" or "comment"
    source: str  # "hackernews", "stackexchange"
    item_id: str
    group: str  # display label: "Hacker News", "stackoverflow"
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

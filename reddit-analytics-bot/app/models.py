from dataclasses import dataclass, field


@dataclass
class SearchItem:
    kind: str  # "post" or "comment"
    source: str  # "reddit", "hackernews", "stackexchange"
    item_id: str
    group: str  # display label: "r/python", "Hacker News", "stackoverflow"
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

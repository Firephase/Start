from dataclasses import dataclass, field

import asyncpraw

from app.config import Config

COMMENTS_PER_POST = 5


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


def make_reddit_client(config: Config) -> asyncpraw.Reddit:
    return asyncpraw.Reddit(
        client_id=config.reddit_client_id,
        client_secret=config.reddit_client_secret,
        user_agent=config.reddit_user_agent,
    )


async def search_reddit(
    reddit: asyncpraw.Reddit, params: SearchParams
) -> list[RedditItem]:
    subreddit_name = "+".join(params.subreddits) if params.subreddits else "all"
    subreddit = await reddit.subreddit(subreddit_name)

    items: list[RedditItem] = []
    async for submission in subreddit.search(
        params.query, sort="relevance", time_filter=params.time_filter, limit=params.limit
    ):
        items.append(
            RedditItem(
                kind="post",
                reddit_id=submission.id,
                subreddit=str(submission.subreddit),
                author=str(submission.author) if submission.author else "[deleted]",
                text=submission.title
                + ("\n\n" + submission.selftext if submission.selftext else ""),
                score=submission.score,
                permalink=f"https://www.reddit.com{submission.permalink}",
                created_utc=submission.created_utc,
            )
        )

        try:
            submission.comment_sort = "top"
            await submission.comments.replace_more(limit=0)
            top_comments = sorted(
                submission.comments.list(), key=lambda c: c.score, reverse=True
            )[:COMMENTS_PER_POST]
        except Exception:
            top_comments = []

        for comment in top_comments:
            if not getattr(comment, "body", None):
                continue
            items.append(
                RedditItem(
                    kind="comment",
                    reddit_id=comment.id,
                    subreddit=str(submission.subreddit),
                    author=str(comment.author) if comment.author else "[deleted]",
                    text=comment.body,
                    score=comment.score,
                    permalink=f"https://www.reddit.com{comment.permalink}",
                    created_utc=comment.created_utc,
                )
            )

    return items

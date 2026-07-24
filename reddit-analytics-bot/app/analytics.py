import re
from collections import Counter

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app.reddit_client import RedditItem

TOP_N = 10
TOP_KEYWORDS = 20
WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ]{3,}")

# Minimal stopword list (English + Russian). Not exhaustive by design -
# good enough to keep the most generic filler words out of keyword counts.
STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "you", "your", "are", "was",
    "were", "have", "has", "had", "not", "but", "they", "them", "their",
    "what", "when", "where", "which", "who", "how", "all", "just", "like",
    "some", "more", "most", "than", "then", "there", "here", "would",
    "could", "should", "about", "into", "out", "get", "got", "one", "can",
    "will", "its", "it's", "i'm", "im", "dont", "doesnt", "didnt",
    "это", "что", "как", "или", "если", "для", "мне", "меня", "тебя",
    "они", "она", "оно", "мой", "моя", "мои", "все", "всех", "всё",
    "так", "уже", "еще", "ещё", "был", "была", "было", "были", "есть",
    "нет", "которые", "который", "которая", "также", "чтобы", "когда",
}


def _tokenize(text: str) -> list[str]:
    return [
        w.lower()
        for w in WORD_RE.findall(text)
        if w.lower() not in STOPWORDS
    ]


def _sentiment_label(compound: float) -> str:
    if compound >= 0.05:
        return "positive"
    if compound <= -0.05:
        return "negative"
    return "neutral"


def build_analytics(query: str, items: list[RedditItem]) -> dict:
    analyzer = SentimentIntensityAnalyzer()

    top_posts = sorted(
        [i for i in items if i.kind == "post"], key=lambda i: i.score, reverse=True
    )[:TOP_N]
    top_comments = sorted(
        [i for i in items if i.kind == "comment"], key=lambda i: i.score, reverse=True
    )[:TOP_N]

    word_counter: Counter[str] = Counter()
    subreddit_counter: Counter[str] = Counter()
    subreddit_score_sum: Counter[str] = Counter()
    sentiment_counter: Counter[str] = Counter()

    for item in items:
        word_counter.update(_tokenize(item.text))
        subreddit_counter[item.subreddit] += 1
        subreddit_score_sum[item.subreddit] += item.score
        compound = analyzer.polarity_scores(item.text)["compound"]
        sentiment_counter[_sentiment_label(compound)] += 1

    subreddit_stats = [
        {
            "subreddit": name,
            "items": count,
            "avg_score": round(subreddit_score_sum[name] / count, 1),
        }
        for name, count in subreddit_counter.most_common()
    ]

    total_sentiment = sum(sentiment_counter.values()) or 1

    return {
        "query": query,
        "total_items": len(items),
        "top_posts": [_item_to_dict(i) for i in top_posts],
        "top_comments": [_item_to_dict(i) for i in top_comments],
        "keyword_frequency": word_counter.most_common(TOP_KEYWORDS),
        "subreddit_stats": subreddit_stats,
        "sentiment": {
            "positive": sentiment_counter["positive"],
            "negative": sentiment_counter["negative"],
            "neutral": sentiment_counter["neutral"],
            "positive_pct": round(100 * sentiment_counter["positive"] / total_sentiment, 1),
            "negative_pct": round(100 * sentiment_counter["negative"] / total_sentiment, 1),
            "neutral_pct": round(100 * sentiment_counter["neutral"] / total_sentiment, 1),
        },
    }


def _item_to_dict(item: RedditItem) -> dict:
    snippet = item.text.strip().replace("\n", " ")
    if len(snippet) > 300:
        snippet = snippet[:300] + "…"
    return {
        "kind": item.kind,
        "subreddit": item.subreddit,
        "author": item.author,
        "score": item.score,
        "permalink": item.permalink,
        "snippet": snippet,
    }

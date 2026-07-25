from html import escape


def format_telegram_summary(analytics: dict) -> str:
    lines = [
        f"📊 Report for query: <b>{escape(analytics['query'])}</b>",
        f"Items found: {analytics['total_items']}",
        "",
        "<b>Top posts:</b>",
    ]
    for post in analytics["top_posts"][:5]:
        lines.append(
            f"• [{post['score']}▲] r/{escape(post['subreddit'])}: "
            f"{escape(post['snippet'][:120])} — {post['permalink']}"
        )

    lines.append("")
    lines.append("<b>Top comments:</b>")
    for comment in analytics["top_comments"][:5]:
        lines.append(
            f"• [{comment['score']}▲] r/{escape(comment['subreddit'])}: "
            f"{escape(comment['snippet'][:120])} — {comment['permalink']}"
        )

    lines.append("")
    sentiment = analytics["sentiment"]
    lines.append(
        "<b>Sentiment:</b> "
        f"👍 {sentiment['positive_pct']}% / "
        f"😐 {sentiment['neutral_pct']}% / "
        f"👎 {sentiment['negative_pct']}%"
    )

    lines.append("")
    lines.append("<b>Common topics:</b> " + ", ".join(
        word for word, _ in analytics["keyword_frequency"][:10]
    ))

    lines.append("")
    lines.append("Full report is sent via /email. Commands: /filter, /run, /report")

    return "\n".join(lines)


def format_email_html(analytics: dict) -> str:
    def item_row(item: dict) -> str:
        return (
            f"<li><strong>[{item['score']}▲] r/{escape(item['subreddit'])}</strong> "
            f"by {escape(item['author'])}<br>"
            f"{escape(item['snippet'])}<br>"
            f"<a href=\"{escape(item['permalink'])}\">{escape(item['permalink'])}</a></li>"
        )

    top_posts_html = "\n".join(item_row(p) for p in analytics["top_posts"]) or "<li>—</li>"
    top_comments_html = "\n".join(
        item_row(c) for c in analytics["top_comments"]
    ) or "<li>—</li>"

    subreddit_rows = "\n".join(
        f"<tr><td>r/{escape(s['subreddit'])}</td><td>{s['items']}</td>"
        f"<td>{s['avg_score']}</td></tr>"
        for s in analytics["subreddit_stats"]
    )

    keyword_row = ", ".join(
        f"{escape(word)} ({count})" for word, count in analytics["keyword_frequency"]
    )

    sentiment = analytics["sentiment"]

    return f"""
    <html>
    <body style="font-family: sans-serif; max-width: 700px; margin: 0 auto;">
      <h2>Reddit analytics for query: {escape(analytics['query'])}</h2>
      <p>Total items analyzed: {analytics['total_items']}</p>

      <h3>Sentiment</h3>
      <p>👍 Positive: {sentiment['positive_pct']}% &nbsp;
         😐 Neutral: {sentiment['neutral_pct']}% &nbsp;
         👎 Negative: {sentiment['negative_pct']}%</p>

      <h3>Top posts by score</h3>
      <ul>{top_posts_html}</ul>

      <h3>Top comments by score</h3>
      <ul>{top_comments_html}</ul>

      <h3>Keyword frequency</h3>
      <p>{keyword_row}</p>

      <h3>Source subreddits</h3>
      <table border="1" cellpadding="6" cellspacing="0">
        <tr><th>Subreddit</th><th>Items</th><th>Avg score</th></tr>
        {subreddit_rows}
      </table>
    </body>
    </html>
    """

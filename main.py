import argparse
import asyncio
import html
import os
import smtplib
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from agents import Agent, Runner

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


@dataclass
class NewsSource:
    name: str
    url: str
    category: str


@dataclass
class NewsArticle:
    title: str
    url: str
    source: str
    category: str
    published_at: datetime | None
    summary: str


@dataclass
class AppConfig:
    model: str
    timezone: str
    run_time: str
    max_articles: int
    story_limit: int
    topics: str
    email_requirements: str
    email_to: str
    email_from: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_use_ssl: bool


RSS_SOURCES = [
    NewsSource("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml", "world"),
    NewsSource("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml", "business"),
    NewsSource("BBC Technology", "https://feeds.bbci.co.uk/news/technology/rss.xml", "technology"),
    NewsSource("BBC Sport", "https://feeds.bbci.co.uk/sport/rss.xml", "sports"),
    NewsSource("BBC Football", "https://feeds.bbci.co.uk/sport/football/rss.xml", "sports"),
    NewsSource("Bloomberg Markets", "https://feeds.bloomberg.com/markets/news.rss", "markets"),
    NewsSource("Bloomberg Economics", "https://feeds.bloomberg.com/economics/news.rss", "macro"),
    NewsSource("Bloomberg Politics", "https://feeds.bloomberg.com/politics/news.rss", "geopolitics"),
    NewsSource("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/", "crypto_policy"),
    NewsSource("The Verge", "https://www.theverge.com/rss/index.xml", "technology"),
]

def load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", maxsplit=1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value

def load_config() -> AppConfig:
    return AppConfig(
        model=os.getenv("NEWS_AGENT_MODEL", "gpt-5.4"),
        timezone=os.getenv("NEWS_TIMEZONE", "Asia/Shanghai"),
        run_time=os.getenv("NEWS_RUN_TIME", "09:00"),
        max_articles=int(os.getenv("NEWS_MAX_ARTICLES", "80")),
        story_limit=int(os.getenv("NEWS_STORY_LIMIT", "12")),
        topics=os.getenv(
            "NEWS_TOPICS",
            "全球头条, 科技与AI, 地缘政治, 宏观经济与市场, 加密货币政策, 中国与全球贸易科技关系, 体育重大事件, 商业与大公司",
        ),
        email_requirements=os.getenv(
            "NEWS_EMAIL_REQUIREMENTS",
            "用中文写，重点说明为什么重要；每条新闻保留来源和链接；忙碌读者可以在5分钟内读完。",
        ),
        email_to=os.getenv("NEWS_EMAIL_TO", ""),
        email_from=os.getenv("NEWS_EMAIL_FROM", os.getenv("SMTP_USER", "")),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "465")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_use_ssl=os.getenv("SMTP_USE_SSL", "true").lower() == "true",
    )


def fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-news-agent/0.1 (+https://openai.com)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_rss_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return None


def get_child_text(item: ET.Element, tag_name: str) -> str:
    child = item.find(tag_name)
    if child is None or child.text is None:
        return ""
    return html.unescape(child.text.strip())


def parse_rss_articles(source: NewsSource, xml_text: str) -> list[NewsArticle]:
    root = ET.fromstring(xml_text)
    articles: list[NewsArticle] = []

    for item in root.findall(".//item"):
        title = get_child_text(item, "title")
        url = get_child_text(item, "link")
        summary = get_child_text(item, "description")
        published_at = parse_rss_datetime(get_child_text(item, "pubDate"))

        if not title or not url:
            continue

        articles.append(
            NewsArticle(
                title=title,
                url=url,
                source=source.name,
                category=source.category,
                published_at=published_at,
                summary=summary,
            )
        )

    return articles

def get_timezone(name: str):
    try:
        return ZoneInfo(name)
    except Exception:
        fixed_offsets = {
            "Asia/Shanghai": timezone(timedelta(hours=8)),
            "UTC": timezone.utc,
        }
        if name in fixed_offsets:
            return fixed_offsets[name]
        print(f"[warn] Unknown timezone {name!r}; falling back to UTC.")
        return timezone.utc

def target_news_date(config: AppConfig) -> datetime.date:
    now = datetime.now(get_timezone(config.timezone))
    return (now - timedelta(days=1)).date()


def collect_articles(config: AppConfig) -> list[NewsArticle]:
    wanted_date = target_news_date(config)
    articles: list[NewsArticle] = []

    for source in RSS_SOURCES:
        try:
            xml_text = fetch_text(source.url)
            source_articles = parse_rss_articles(source, xml_text)
        except Exception as error:
            print(f"[warn] Failed to fetch {source.name}: {error}")
            continue

        for article in source_articles:
            if article.published_at is None:
                articles.append(article)
                continue

            local_date = article.published_at.astimezone(get_timezone(config.timezone)).date()
            if local_date == wanted_date:
                articles.append(article)

    return dedupe_articles(articles)[: config.max_articles]


def dedupe_articles(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen: set[str] = set()
    unique_articles: list[NewsArticle] = []

    for article in articles:
        key = article.url.split("?")[0].strip().lower() or article.title.strip().lower()
        if key in seen:
            continue

        seen.add(key)
        unique_articles.append(article)

    return unique_articles


def format_articles_for_agent(articles: list[NewsArticle], config: AppConfig) -> str:
    wanted_date = target_news_date(config)
    lines = [
        f"Target date: {wanted_date.isoformat()}",
        "Candidate articles:",
        "",
    ]

    for index, article in enumerate(articles, start=1):
        published = "unknown"
        if article.published_at is not None:
            published = article.published_at.astimezone(get_timezone(config.timezone)).isoformat()

        lines.extend(
            [
                f"{index}. {article.title}",
                f"   Source: {article.source}",
                f"   Category: {article.category}",
                f"   Published: {published}",
                f"   URL: {article.url}",
                f"   Summary: {article.summary}",
                "",
            ]
        )

    return "\n".join(lines)


def build_news_agent(config: AppConfig) -> Agent:
    instructions = f"""
You are a daily news curator for a personal email briefing.

User preferences:
- Maximum final stories: {config.story_limit}
- Priority topics: {config.topics}
- Email requirements: {config.email_requirements}

Your job:
1. Review the candidate articles from BBC, Bloomberg, CoinDesk, The Verge, and sports feeds.
2. Select up to {config.story_limit} genuinely important stories from the target date. Prefer a full briefing when the news is strong, but do not force weak stories.
3. The first 5 stories should be the most important global stories overall.
4. Use the remaining slots to cover the user's priority themes when there is real news.
5. Remove duplicates and avoid minor stories unless they are unusually important.
6. Write the briefing in clear Chinese for a busy reader.
7. Follow the user's email requirements unless they conflict with accuracy or source attribution.

Output format:
标题: 昨日新闻简报

一、全球头条
1. [事件标题]
- 来源: source name
- 重要性: one short Chinese sentence
- 摘要: two to three short Chinese sentences
- 链接: URL

二、主题重点
Continue numbering from the global headlines. Group stories under useful section names such as 地缘政治, 科技与AI, 宏观与市场, 加密货币政策, 中国与全球, 体育重大事件, 商业与大公司.
Only include a section if it contains genuinely important news.

End with:
今日关注:
- 3 to 5 short bullets about what to watch next.
"""

    return Agent(
        name="Daily News Curator",
        model=config.model,
        instructions=instructions,
    )

async def create_briefing(config: AppConfig, articles: list[NewsArticle]) -> str:
    if not articles:
        return "标题: 昨日新闻简报\n\n没有从配置的 RSS 源中找到昨日新闻。"

    agent = build_news_agent(config)
    prompt = format_articles_for_agent(articles, config)
    result = await Runner.run(agent, prompt)
    return result.final_output


def build_email_subject(config: AppConfig) -> str:
    wanted_date = target_news_date(config)
    return f"昨日新闻简报 - {wanted_date.isoformat()}"


def send_email(config: AppConfig, subject: str, body: str) -> None:
    missing = []
    if not config.email_to:
        missing.append("NEWS_EMAIL_TO")
    if not config.email_from:
        missing.append("NEWS_EMAIL_FROM or SMTP_USER")
    if not config.smtp_user:
        missing.append("SMTP_USER")
    if not config.smtp_password:
        missing.append("SMTP_PASSWORD")

    if missing:
        raise ValueError("Missing email config: " + ", ".join(missing))

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config.email_from
    message["To"] = config.email_to
    message.set_content(body)

    if config.smtp_use_ssl:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            smtp.login(config.smtp_user, config.smtp_password.replace(" ", ""))
            smtp.send_message(message)
    else:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(config.smtp_user, config.smtp_password.replace(" ", ""))
            smtp.send_message(message)


async def run_once(config: AppConfig, dry_run: bool) -> None:
    print("[info] Collecting articles...")
    articles = collect_articles(config)
    print(f"[info] Found {len(articles)} candidate articles.")

    print("[info] Creating briefing with agent...")
    briefing = await create_briefing(config, articles)

    subject = build_email_subject(config)
    print("\n" + "=" * 70)
    print(subject)
    print("=" * 70)
    print(briefing)
    print("=" * 70 + "\n")

    if dry_run:
        print("[info] Dry run only. Email was not sent.")
        return

    try:
        send_email(config, subject, briefing)
    except ValueError as error:
        print(f"[warn] Email was not sent: {error}")
        print("[hint] Add email environment variables, or run with --dry-run while testing.")
        return
    except Exception as error:
        print(f"[warn] Email sending failed: {error}")
        print("[hint] If Gmail port 465 times out, try SMTP_PORT=587 and SMTP_USE_SSL=false.")
        return

    print("[info] Email sent.")


def seconds_until_next_run(config: AppConfig) -> float:
    hour_text, minute_text = config.run_time.split(":", maxsplit=1)
    hour = int(hour_text)
    minute = int(minute_text)

    timezone = get_timezone(config.timezone)
    now = datetime.now(timezone)
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if next_run <= now:
        next_run += timedelta(days=1)

    return (next_run - now).total_seconds()


async def run_schedule(config: AppConfig, dry_run: bool) -> None:
    print(f"[info] Scheduler started. Daily run time: {config.run_time} {config.timezone}")

    while True:
        wait_seconds = seconds_until_next_run(config)
        next_minutes = round(wait_seconds / 60, 1)
        print(f"[info] Waiting {next_minutes} minutes until next run.")
        await asyncio.sleep(wait_seconds)
        await run_once(config, dry_run=dry_run)
        time.sleep(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily news agent email briefing")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the briefing but do not send email.",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Keep the process running and execute daily at NEWS_RUN_TIME.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    load_env_file()
    config = load_config()

    if args.schedule:
        await run_schedule(config, dry_run=args.dry_run)
    else:
        await run_once(config, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())








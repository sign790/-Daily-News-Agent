import asyncio
import json
import mimetypes
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import main as news_agent

PROJECT_DIR = Path(__file__).resolve().parent
WEB_DIR = PROJECT_DIR / "web"
ENV_PATH = PROJECT_DIR / ".env"

CONFIG_KEYS = [
    "OPENAI_API_KEY",
    "NEWS_AGENT_MODEL",
    "NEWS_TIMEZONE",
    "NEWS_RUN_TIME",
    "NEWS_MAX_ARTICLES",
    "NEWS_STORY_LIMIT",
    "NEWS_TOPICS",
    "NEWS_EMAIL_REQUIREMENTS",
    "NEWS_EMAIL_TO",
    "NEWS_EMAIL_FROM",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_USE_SSL",
]

SECRET_KEYS = {"OPENAI_API_KEY", "SMTP_PASSWORD"}


def read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values

    with ENV_PATH.open("r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", maxsplit=1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_file(updates: dict[str, str]) -> None:
    current = read_env_file()

    for key, value in updates.items():
        if key not in CONFIG_KEYS:
            continue
        if key in SECRET_KEYS and value == "":
            continue
        current[key] = str(value).strip()
        os.environ[key] = current[key]

    lines = [f"{key}={current[key]}" for key in CONFIG_KEYS if key in current]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def public_config() -> dict[str, object]:
    values = read_env_file()
    return {
        "NEWS_AGENT_MODEL": values.get("NEWS_AGENT_MODEL", "gpt-5.4"),
        "NEWS_TIMEZONE": values.get("NEWS_TIMEZONE", "Asia/Shanghai"),
        "NEWS_RUN_TIME": values.get("NEWS_RUN_TIME", "09:00"),
        "NEWS_MAX_ARTICLES": values.get("NEWS_MAX_ARTICLES", "80"),
        "NEWS_STORY_LIMIT": values.get("NEWS_STORY_LIMIT", "12"),
        "NEWS_TOPICS": values.get(
            "NEWS_TOPICS",
            "全球头条, 科技与AI, 地缘政治, 宏观经济与市场, 加密货币政策, 中国与全球贸易科技关系, 体育重大事件, 商业与大公司",
        ),
        "NEWS_EMAIL_REQUIREMENTS": values.get(
            "NEWS_EMAIL_REQUIREMENTS",
            "用中文写，重点说明为什么重要；每条新闻保留来源和链接；忙碌读者可以在5分钟内读完。",
        ),
        "NEWS_EMAIL_TO": values.get("NEWS_EMAIL_TO", ""),
        "NEWS_EMAIL_FROM": values.get("NEWS_EMAIL_FROM", values.get("SMTP_USER", "")),
        "SMTP_HOST": values.get("SMTP_HOST", "smtp.gmail.com"),
        "SMTP_PORT": values.get("SMTP_PORT", "587"),
        "SMTP_USER": values.get("SMTP_USER", ""),
        "SMTP_USE_SSL": values.get("SMTP_USE_SSL", "false"),
        "has_openai_key": bool(values.get("OPENAI_API_KEY")),
        "has_smtp_password": bool(values.get("SMTP_PASSWORD")),
    }


def load_runtime_config() -> news_agent.AppConfig:
    news_agent.load_env_file(str(ENV_PATH))
    for key, value in read_env_file().items():
        os.environ[key] = value
    return news_agent.load_config()


async def build_briefing() -> tuple[str, str, int]:
    config = load_runtime_config()
    articles = news_agent.collect_articles(config)
    briefing = await news_agent.create_briefing(config, articles)
    subject = news_agent.build_email_subject(config)
    return subject, briefing, len(articles)


class NewsAgentHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urlparse(path).path
        if parsed == "/":
            return str(WEB_DIR / "index.html")
        return str(WEB_DIR / parsed.lstrip("/"))

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path).path
        if parsed == "/api/config":
            self.send_json(200, {"ok": True, "config": public_config()})
            return

        file_path = Path(self.translate_path(self.path))
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "Not found")
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        parsed = urlparse(self.path).path

        try:
            payload = self.read_json()
            updates = {key: str(payload.get(key, "")) for key in CONFIG_KEYS if key in payload}

            if parsed == "/api/config":
                write_env_file(updates)
                self.send_json(200, {"ok": True, "config": public_config()})
                return

            if parsed == "/api/preview":
                write_env_file(updates)
                subject, briefing, article_count = asyncio.run(build_briefing())
                self.send_json(200, {"ok": True, "subject": subject, "briefing": briefing, "article_count": article_count, "sent": False})
                return

            if parsed == "/api/send":
                write_env_file(updates)
                subject, briefing, article_count = asyncio.run(build_briefing())
                config = load_runtime_config()
                news_agent.send_email(config, subject, briefing)
                self.send_json(200, {"ok": True, "subject": subject, "briefing": briefing, "article_count": article_count, "sent": True})
                return

            self.send_json(404, {"ok": False, "error": "Unknown endpoint"})
        except Exception as error:
            self.send_json(500, {"ok": False, "error": str(error)})


def run() -> None:
    host = os.getenv("NEWS_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("NEWS_WEB_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), NewsAgentHandler)
    print(f"Daily News Agent UI: http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    run()

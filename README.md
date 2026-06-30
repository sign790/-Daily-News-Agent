# Daily News Agent

一个用 OpenAI Agents SDK 做的个人新闻简报工具：每天抓取 RSS 新闻源，让 Agent 选出重要新闻，生成中文邮件简报，并发送到指定邮箱。

## 功能

- 抓取 BBC、Bloomberg、CoinDesk、The Verge 等 RSS 源
- 关注全球热点、科技与 AI、地缘政治、宏观市场、加密政策、中国相关国际新闻、重大体育事件
- 默认最多输出 12 条新闻
- 支持 dry-run 测试，不发邮件
- 支持 SMTP 发邮件
- 支持按固定时间循环运行


## Local-first design

This project is meant to be downloaded and run locally. It asks for an OpenAI API key and an email SMTP app password, so a public hosted version would need account systems, encrypted secret storage, abuse prevention, rate limits, billing controls, and a safer credential flow.

For most users, the safest setup is:

1. Clone the repo.
2. Copy `.env.example` to `.env`.
3. Fill in their own keys and email settings locally.
4. Run `python web_app.py` and use the local browser UI.

## 安装

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，然后填写自己的配置：

```env
OPENAI_API_KEY=your-openai-api-key
NEWS_AGENT_MODEL=gpt-5.4
NEWS_TIMEZONE=Asia/Shanghai
NEWS_RUN_TIME=09:00

NEWS_EMAIL_TO=your-receiver@example.com
NEWS_EMAIL_FROM=your-sender@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-sender@gmail.com
SMTP_PASSWORD=
SMTP_USE_SSL=false
```

不要把 `.env` 上传到 GitHub。仓库里只应该保留 `.env.example`。


## 网页界面

启动本地控制台：

```powershell
python web_app.py
```

然后打开：

```text
http://127.0.0.1:8765
```

网页里可以填写模型、收件邮箱、发件邮箱、SMTP 授权码、主题偏好、最终新闻条数和邮件要求。密钥会保存到本机 `.env`，不要把 `.env` 上传到 GitHub。

## 运行

只生成简报，不发邮件：

```powershell
python main.py --dry-run
```

生成并发送邮件：

```powershell
python main.py
```

一直运行，并在 `.env` 里的 `NEWS_RUN_TIME` 时间触发：

```powershell
python main.py --schedule
```

## 安全提醒

- 建议使用专门的小号邮箱作为发件人
- `SMTP_PASSWORD` 使用 Gmail App Password 或邮箱 SMTP 授权码，不要使用主密码
- `.env`、API key、邮箱授权码不要提交到 GitHub






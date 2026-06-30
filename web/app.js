const form = document.querySelector("#settingsForm");
const logs = document.querySelector("#logs");
const output = document.querySelector("#briefingOutput");
const subjectText = document.querySelector("#subjectText");
const articleCount = document.querySelector("#articleCount");
const secretStatus = document.querySelector("#secretStatus");
const runStatus = document.querySelector("#runStatus");
const buttons = ["#saveButton", "#previewButton", "#sendButton"].map((id) => document.querySelector(id));

function log(message) {
  const row = document.createElement("div");
  row.className = "log-entry";
  row.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  logs.prepend(row);
}

function setBusy(isBusy, label = "运行中") {
  buttons.forEach((button) => {
    button.disabled = isBusy;
  });
  runStatus.textContent = isBusy ? label : "待运行";
  runStatus.classList.toggle("muted", !isBusy);
}

function collectTopics() {
  const checked = [...document.querySelectorAll("#topicGrid input:checked")].map((item) => item.value);
  const custom = form.NEWS_TOPICS.value
    .split(/[，,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return [...new Set([...checked, ...custom])].join(", ");
}

function formPayload() {
  const data = Object.fromEntries(new FormData(form).entries());
  data.NEWS_TOPICS = collectTopics();
  data.SMTP_USE_SSL = form.SMTP_USE_SSL.checked ? "true" : "false";
  return data;
}

function fillForm(config) {
  for (const [key, value] of Object.entries(config)) {
    if (key === "has_openai_key" || key === "has_smtp_password") continue;
    if (key === "SMTP_USE_SSL") {
      form.SMTP_USE_SSL.checked = String(value).toLowerCase() === "true";
      continue;
    }
    if (form.elements[key]) {
      form.elements[key].value = value ?? "";
    }
  }

  const topics = String(config.NEWS_TOPICS || "");
  document.querySelectorAll("#topicGrid input").forEach((checkbox) => {
    checkbox.checked = topics.includes(checkbox.value);
  });

  const okKey = config.has_openai_key ? "模型密钥已保存" : "缺少模型密钥";
  const okMail = config.has_smtp_password ? "邮件授权已保存" : "缺少邮件授权";
  secretStatus.textContent = `${okKey} · ${okMail}`;
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: path === "/api/config" && !payload ? "GET" : "POST",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
  const data = await response.json();
  if (!data.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

async function loadConfig() {
  const data = await api("/api/config");
  fillForm(data.config);
  log("配置已加载");
}

async function saveConfig() {
  setBusy(true, "保存中");
  try {
    const data = await api("/api/config", formPayload());
    fillForm(data.config);
    log("设置已保存到本地 .env");
  } catch (error) {
    log(`保存失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function runPreview(send) {
  setBusy(true, send ? "发送中" : "生成中");
  output.textContent = send ? "正在生成并发送邮件..." : "正在抓取新闻并生成简报...";
  try {
    const data = await api(send ? "/api/send" : "/api/preview", formPayload());
    subjectText.textContent = data.subject;
    articleCount.textContent = data.article_count;
    output.textContent = data.briefing;
    log(send ? "邮件已发送" : "预览已生成");
  } catch (error) {
    output.textContent = `失败：${error.message}`;
    log(`${send ? "发送" : "预览"}失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

document.querySelector("#saveButton").addEventListener("click", saveConfig);
document.querySelector("#previewButton").addEventListener("click", () => runPreview(false));
document.querySelector("#sendButton").addEventListener("click", () => runPreview(true));
document.querySelector("#clearLogs").addEventListener("click", () => {
  logs.innerHTML = "";
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
    tab.classList.add("is-active");
    document.querySelector(`[data-panel="${tab.dataset.view}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
});

loadConfig().catch((error) => log(`配置加载失败：${error.message}`));

from flask import Flask, request
import requests, os

app = Flask(__name__)

MATTERMOST_WEBHOOK = os.environ["MATTERMOST_WEBHOOK"]
SENTRY_URL = os.environ.get("SENTRY_URL", "").rstrip("/")
SENTRY_ORG = os.environ.get("SENTRY_ORG", "")
PORT = int(os.environ.get("PORT", 5000))

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    action = data.get("action", "triggered")
    issue = data.get("data", {}).get("issue", {})

    title = issue.get("title", "Unknown error")
    project = issue.get("project", {}).get("slug", "unknown")
    level = issue.get("level", "error").upper()
    issue_id = issue.get("id", "")
    culprit = issue.get("culprit", "")

    if SENTRY_URL and SENTRY_ORG and issue_id:
        link = f"{SENTRY_URL}/organizations/{SENTRY_ORG}/issues/{issue_id}/"
    else:
        link = issue.get("permalink", "")

    emoji = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵", "DEBUG": "⚪"}.get(level, "🔴")

    text = f"{emoji} **[{project}] {title}**\n"
    if culprit:
        text += f"📍 `{culprit}`\n"
    text += f"Status: **{action}** | Level: **{level}**\n"
    if link:
        text += f"🔗 [View in Sentry]({link})"

    requests.post(MATTERMOST_WEBHOOK, json={"text": text})
    return "OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

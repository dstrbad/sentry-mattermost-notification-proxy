import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests
from flask import Flask, Response, request

MATTERMOST_WEBHOOK = os.environ["MATTERMOST_WEBHOOK"]
SENTRY_URL = os.environ.get("SENTRY_URL", "").rstrip("/")
SENTRY_ORG = os.environ.get("SENTRY_ORG", "")
# Optional: set SENTRY_CLIENT_SECRET to enable HMAC signature verification
SENTRY_CLIENT_SECRET = os.environ.get("SENTRY_CLIENT_SECRET", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

app = Flask(__name__)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
app.logger.handlers = [handler]
app.logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

logging.getLogger("werkzeug").setLevel(
    logging.DEBUG if LOG_LEVEL == "DEBUG" else logging.WARNING
)

COLOR_MAP = {
    "critical": "#D40000",
    "error":    "#D40000",
    "warning":  "#FFCC00",
    "info":     "#2196F3",
    "debug":    "#CCCCCC",
    "resolved": "#2EA44F",
    "default":  "#888888",
}

EMOJI_MAP = {
    "critical": "🔴",
    "error":    "🔴",
    "warning":  "🟡",
    "info":     "🔵",
    "debug":    "⚪",
    "resolved": "✅",
    "default":  "🔔",
}


def pick_color(level_or_action: str) -> str:
    return COLOR_MAP.get(level_or_action.lower(), COLOR_MAP["default"])


def pick_emoji(level_or_action: str) -> str:
    return EMOJI_MAP.get(level_or_action.lower(), EMOJI_MAP["default"])

def sentry_issue_link(issue_id: str) -> str:
    if SENTRY_URL and issue_id:
        return f"{SENTRY_URL}/organizations/{SENTRY_ORG}/issues/{issue_id}/"
    return ""


def post_to_mattermost(payload: dict) -> bool:
    try:
        resp = requests.post(MATTERMOST_WEBHOOK, json=payload, timeout=5)
        resp.raise_for_status()
        app.logger.debug("Mattermost accepted message (HTTP %s)", resp.status_code)
        return True
    except requests.RequestException as exc:
        app.logger.error("Failed to post to Mattermost: %s", exc)
        return False


def verify_signature(payload_bytes: bytes, signature: str) -> bool:
    if not SENTRY_CLIENT_SECRET:
        return True  # verification disabled
    expected = hmac.new(
        SENTRY_CLIENT_SECRET.encode(),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def handle_issue(data: dict, action: str) -> dict:
    """Resource: issue — actions: created, resolved, assigned, archived, unresolved."""
    issue = data.get("data", {}).get("issue", {})
    title = issue.get("title", "Unknown issue")
    project = issue.get("project", {}).get("slug", "unknown")
    level = issue.get("level", "error")
    issue_id = str(issue.get("id", ""))
    culprit = issue.get("culprit", "")
    link = sentry_issue_link(issue_id) or issue.get("permalink", "")

    emoji = pick_emoji(level)
    if action == "resolved":
        emoji = pick_emoji("resolved")
        color = pick_color("resolved")
    else:
        color = pick_color(level)

    attachment = {
        "fallback": f"[{project}] {title}",
        "color": color,
        "title": f"{emoji} [{project}] {title}",
        "title_link": link or None,
        "fields": [
            {"short": True, "title": "Status", "value": action},
            {"short": True, "title": "Level", "value": level.upper()},
        ],
    }
    if culprit:
        attachment["text"] = f"`{culprit}`"

    return {"attachments": [attachment]}


def handle_event_alert(data: dict, action: str) -> dict:
    event = data.get("data", {}).get("event", {})
    rule = data.get("data", {}).get("triggered_rule", "Unknown rule")
    title = event.get("title", "Unknown event")
    level = event.get("level", "error")
    culprit = event.get("culprit", "")
    issue_id = str(event.get("issue_id", ""))
    link = event.get("web_url", "") or sentry_issue_link(issue_id)

    project_id = event.get("project", "")
    project_label = str(project_id) if project_id else "unknown"

    emoji = pick_emoji(level)

    attachment = {
        "fallback": f"Alert: {rule} — {title}",
        "color": pick_color(level),
        "title": f"{emoji} Alert: {title}",
        "title_link": link or None,
        "text": f"Triggered by rule: **{rule}**",
        "fields": [
            {"short": True, "title": "Level", "value": level.upper()},
        ],
    }
    if culprit:
        attachment["fields"].append(
            {"short": True, "title": "Culprit", "value": f"`{culprit}`"}
        )

    return {"attachments": [attachment]}


def handle_metric_alert(data: dict, action: str) -> dict:
    inner = data.get("data", {})
    desc_title = inner.get("description_title", "Metric Alert")
    desc_text = inner.get("description_text", "")
    web_url = inner.get("web_url", "")
    alert_rule = inner.get("metric_alert", {}).get("alert_rule", {})
    rule_name = alert_rule.get("name", "")

    if action == "resolved":
        emoji = pick_emoji("resolved")
        color = pick_color("resolved")
    elif action == "critical":
        emoji = pick_emoji("critical")
        color = pick_color("critical")
    else:
        emoji = pick_emoji("warning")
        color = pick_color("warning")

    attachment = {
        "fallback": desc_title,
        "color": color,
        "title": f"{emoji} {desc_title}",
        "title_link": web_url or None,
        "fields": [
            {"short": True, "title": "Status", "value": action.upper()},
        ],
    }
    if rule_name:
        attachment["fields"].append(
            {"short": True, "title": "Rule", "value": rule_name}
        )
    if desc_text:
        attachment["text"] = desc_text

    return {"attachments": [attachment]}


def handle_error(data: dict, action: str) -> dict:
    error = data.get("data", {}).get("error", {})
    title = error.get("title", "Unknown error")
    level = error.get("level", "error")
    culprit = error.get("culprit", "")
    issue_id = str(error.get("issue_id", ""))
    link = error.get("web_url", "") or sentry_issue_link(issue_id)
    project_id = error.get("project", "")

    emoji = pick_emoji(level)

    attachment = {
        "fallback": f"Error: {title}",
        "color": pick_color(level),
        "title": f"{emoji} Error: {title}",
        "title_link": link or None,
        "fields": [
            {"short": True, "title": "Level", "value": level.upper()},
        ],
    }
    if culprit:
        attachment["text"] = f"`{culprit}`"

    return {"attachments": [attachment]}


def handle_comment(data: dict, action: str) -> dict:
    comment_data = data.get("data", {}).get("comment", {})
    comment_text = comment_data if isinstance(comment_data, str) else ""
    issue_id = str(data.get("data", {}).get("issue_id", ""))
    project_slug = data.get("data", {}).get("project_slug", "unknown")
    link = sentry_issue_link(issue_id)

    actor = data.get("actor", {})
    actor_name = actor.get("name", "Someone")

    attachment = {
        "fallback": f"Comment {action} on issue {issue_id}",
        "color": pick_color("info"),
        "title": f"💬 [{project_slug}] Comment {action}",
        "title_link": link or None,
        "fields": [
            {"short": True, "title": "Action", "value": action},
            {"short": True, "title": "By", "value": actor_name},
        ],
    }
    if comment_text:
        # Truncate long comments
        truncated = comment_text[:300] + ("…" if len(comment_text) > 300 else "")
        attachment["text"] = truncated

    return {"attachments": [attachment]}


def handle_installation(data: dict, action: str) -> dict:
    actor = data.get("actor", {})
    actor_name = actor.get("name", "Unknown")
    emoji = "🔧" if action == "created" else "🗑️"

    attachment = {
        "fallback": f"Integration {action} by {actor_name}",
        "color": pick_color("info"),
        "title": f"{emoji} Integration {action}",
        "fields": [
            {"short": True, "title": "Action", "value": action},
            {"short": True, "title": "By", "value": actor_name},
        ],
    }

    return {"attachments": [attachment]}


def handle_unknown(data: dict, action: str, resource: str) -> dict:
    attachment = {
        "fallback": f"Sentry webhook: {resource} {action}",
        "color": pick_color("default"),
        "title": f"🔔 Sentry: {resource} — {action}",
        "text": "Unhandled resource type. Check logs for full payload.",
        "fields": [
            {"short": True, "title": "Resource", "value": resource},
            {"short": True, "title": "Action", "value": action},
        ],
    }

    return {"attachments": [attachment]}


HANDLERS = {
    "issue":        handle_issue,
    "event_alert":  handle_event_alert,
    "metric_alert": handle_metric_alert,
    "error":        handle_error,
    "comment":      handle_comment,
    "installation": handle_installation,
}


@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    request_id = request.headers.get("Request-ID", "none")
    resource = request.headers.get("Sentry-Hook-Resource", "").lower()
    signature = request.headers.get("Sentry-Hook-Signature", "")
    raw_body = request.get_data()

    if SENTRY_CLIENT_SECRET and not verify_signature(raw_body, signature):
        app.logger.warning(
            "Signature verification failed [request_id=%s resource=%s]",
            request_id, resource,
        )
        return "invalid signature", 401

    try:
        data = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError) as exc:
        app.logger.error(
            "Failed to parse JSON body [request_id=%s]: %s", request_id, exc
        )
        return "bad request", 400

    action = data.get("action", "unknown")

    app.logger.info(
        "Received webhook [request_id=%s resource=%s action=%s]",
        request_id, resource, action,
    )
    app.logger.debug(
        "Full payload [request_id=%s]: %s",
        request_id, json.dumps(data, indent=2, default=str),
    )

    handler = HANDLERS.get(resource)
    if handler:
        try:
            payload = handler(data, action)
        except Exception:
            app.logger.exception(
                "Handler crashed [request_id=%s resource=%s action=%s]",
                request_id, resource, action,
            )
            # Still forward a degraded message so the alert isn't silently lost
            payload = handle_unknown(data, action, resource)
    else:
        app.logger.warning(
            "No handler for resource=%s action=%s [request_id=%s]. "
            "Forwarding generic message.",
            resource, action, request_id,
        )
        payload = handle_unknown(data, action, resource)

    success = post_to_mattermost(payload)
    if not success:
        app.logger.error(
            "Mattermost delivery failed [request_id=%s resource=%s action=%s]",
            request_id, resource, action,
        )
        return "delivery failed", 500

    return "ok", 200

if __name__ == "__main__":
    app.logger.info(
        "Starting Sentry→Mattermost bridge (sentry_url=%s org=%s sig_verify=%s)",
        SENTRY_URL, SENTRY_ORG, bool(SENTRY_CLIENT_SECRET),
    )
    app.run(host="0.0.0.0", port=5000)

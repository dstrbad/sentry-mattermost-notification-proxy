# Sentry Mattermost Notification Proxy

A minimal Python proxy that translates Sentry webhook payloads into formatted Mattermost notifications. Sentry's generic webhook format is not directly compatible with Mattermost's incoming webhook API.

## Requirements

- Python 3.8+
- `flask`
- `requests`

## Configuration

The proxy is configured via environment variables:

| Variable | Required | Description |
| `MATTERMOST_WEBHOOK` | Yes | Mattermost incoming webhook URL |
| `SENTRY_URL` | No | Base URL of your Sentry instance (default: ``) |
| `SENTRY_ORG` | No | Your Sentry organization slug (default: ``) |
| `SENTRY_CLIENT_SECRET` | No | Enables HMAC-SHA256 signature verification if set |
| `LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`) |

## Running

```bash
MATTERMOST_WEBHOOK=https://mattermost.example.com/hooks/xxxxx \
SENTRY_URL=https://sentry.example.com \
SENTRY_ORG=myorg \
python3 app.py
```

Set `LOG_LEVEL=DEBUG` to dump full JSON payloads for every incoming webhook — useful for diagnosing unexpected payload shapes.

## Supported Webhook Types

The proxy handles all Sentry `Sentry-Hook-Resource` types:

- **issue** — created, resolved, assigned, archived, unresolved
- **event_alert** — triggered (from alert rules)
- **metric_alert** — critical, warning, resolved
- **error** — created
- **comment** — created, updated, deleted
- **installation** — created, deleted

Unrecognized resource types are forwarded as a generic notification rather than dropped silently.

## Sentry Setup

1. In Sentry go to **Settings → Custom Integrations → New Internal Integration**
2. Under **Webhooks**, set the URL to `http://<host>:5000/webhook`
3. Subscribe to the events you want (e.g. `issue`, `event_alert`)
4. Copy the **Client Secret** and set it as `SENTRY_CLIENT_SECRET` to enable signature verification
5. Save and use the integration in your Alert Rules

## Endpoints

- `POST /webhook` — receives Sentry webhooks
- `GET /health` — liveness probe, returns `200 ok`

## Firewall

If Sentry runs in Docker, allow the Docker subnet to reach port 5000 on the host:

```bash
ufw allow from 172.18.0.0/16 to any port 5000
```

Adjust the subnet to match your Docker network (`docker network inspect <network> | grep Subnet`).

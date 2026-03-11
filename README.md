# Sentry Mattermost Notification Proxy

A minimal Python proxy that translates Sentry webhook payloads into formatted Mattermost notifications. Sentry's generic webhook format is not directly compatible with Mattermost's incoming webhook API.

## Requirements

- Python 3.8+
- `flask`
- `requests`


## Configuration

The proxy is configured via environment variables:
- `MATTERMOST_WEBHOOK`, Mattermost incoming webhook URL, eg. `https://mattermost.example.com/hooks/xxxxx`
- `SENTRY_URL`, Base URL of your Sentry instance, e.g. `https://sentry.example.com`
- `SENTRY_ORG`, Your Sentry organization slug, e.g. `myORG`

**The proxy listenst on port `5000` by default.**

## Running

Package in Docker, run as daemon, or however you prefer, don't forget to pass ENV vars to the process.

```bash
MATTERMOST_WEBHOOK=https://mattermost.example.com/hooks/xxxxx \
SENTRY_URL=https://sentry.example.com \
SENTRY_ORG=myORG \
python3 sentry_mattermost_proxy.py
```


## Sentry Setup

1. In Sentry go to **Settings → Custom Integrations → New Internal Integration**
2. Under **Webhooks**, add your proxy URL: `http://<host>:5000/webhook`
3. Subscribe to the events you want (e.g. `issue`, `event_alert`)
4. Save and use the integration in your Alert Rules


## Firewall

If Sentry runs in Docker, allow the Docker subnet to reach port 5000 on the host:

```bash
ufw allow from 172.18.0.0/16 to any port 5000
```

Adjust the subnet to match your Docker network (`docker network inspect <network> | grep Subnet`).
Adjust the port to match your configuration if not runnong on default port.


## Notification Format

```
🔴 [my-project] TypeError: Cannot read property 'x' of undefined
📍 `src/components/App.js`
Status: created | Level: ERROR
🔗 View in Sentry
```

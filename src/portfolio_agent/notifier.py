from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from urllib import parse, request

from .config import NotificationConfig


def send_notifications(config: NotificationConfig, subject: str, body: str) -> list[str]:
    if not config.enabled:
        return ["notifications disabled"]

    results: list[str] = []
    if config.dry_run:
        return [f"dry-run notification: {subject}"]

    results.append(_send_slack(config, subject, body))
    results.append(_send_telegram(config, subject, body))
    results.append(_send_email(config, subject, body))
    return results


def _send_slack(config: NotificationConfig, subject: str, body: str) -> str:
    webhook = os.getenv(config.slack_webhook_env, "").strip()
    if not webhook:
        return "slack skipped: missing webhook env"

    payload = json.dumps({"text": f"*{subject}*\n{body}"}).encode("utf-8")
    req = request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as response:
            if response.status < 300:
                return "slack sent"
            return f"slack failed: status {response.status}"
    except Exception as exc:  # noqa: BLE001
        return f"slack failed: {type(exc).__name__}"


def _send_telegram(config: NotificationConfig, subject: str, body: str) -> str:
    token = os.getenv(config.telegram_bot_token_env, "").strip()
    chat_id = os.getenv(config.telegram_chat_id_env, "").strip()
    if not token or not chat_id:
        return "telegram skipped: missing token/chat_id env"

    text = f"{subject}\n\n{body}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")

    try:
        with request.urlopen(url, data=data, timeout=10) as response:
            if response.status < 300:
                return "telegram sent"
            return f"telegram failed: status {response.status}"
    except Exception as exc:  # noqa: BLE001
        return f"telegram failed: {type(exc).__name__}"


def _send_email(config: NotificationConfig, subject: str, body: str) -> str:
    host = os.getenv(config.smtp_host_env, "").strip()
    port = os.getenv(config.smtp_port_env, "587").strip()
    user = os.getenv(config.smtp_user_env, "").strip()
    password = os.getenv(config.smtp_pass_env, "").strip()
    sender = os.getenv(config.email_from_env, "").strip()
    recipient = os.getenv(config.email_to_env, "").strip()

    if not host or not sender or not recipient:
        return "email skipped: missing SMTP/env settings"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, int(port), timeout=10) as smtp:
            smtp.starttls()
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return "email sent"
    except Exception as exc:  # noqa: BLE001
        return f"email failed: {type(exc).__name__}"

#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Quantifi Solutions Inc
# SPDX-License-Identifier: MIT
"""
Atlantis -> Microsoft Teams Relay
Accepts webhook payloads from Atlantis (the native "kind: http" payload
with PascalCase Repo/Pull/Project/Success fields) and forwards them
to a Microsoft Teams Workflows webhook as Adaptive Cards.

For convenience the relay also accepts the classic Slack incoming-webhook
shape ({text, attachments[]}) — useful for ad-hoc curl tests or other
senders. The payload type is auto-detected.

Usage:
    pip install flask requests
    TEAMS_WEBHOOK_URL=https://your-url python relay.py

Atlantis config (server-side YAML or env):
    webhooks:
      - event: apply
        kind: http
        url: http://this-server:5025/relay
"""

import os
import json
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL")

if not TEAMS_WEBHOOK_URL:
    raise RuntimeError("TEAMS_WEBHOOK_URL environment variable is not set")


def build_adaptive_card(atlantis_payload: dict) -> dict:
    """
    Convert an Atlantis/Slack-format payload into a Teams Adaptive Card.
    Atlantis sends: { "text": "...", "attachments": [...] }
    """
    body = []

    # Main text
    text = atlantis_payload.get("text", "")
    if text:
        body.append({
            "type": "TextBlock",
            "text": text,
            "wrap": True,
            "size": "Medium",
            "weight": "Bolder"
        })

    # Attachments (Atlantis uses these for plan/apply output)
    for attachment in atlantis_payload.get("attachments", []):
        # Coloured header/title
        title = attachment.get("title") or attachment.get("fallback", "")
        if title:
            color = attachment.get("color", "")
            weight = "Bolder"
            body.append({
                "type": "TextBlock",
                "text": title,
                "wrap": True,
                "weight": weight,
                "color": "Good" if color == "good" else
                         "Warning" if color == "warning" else
                         "Attention" if color == "danger" else "Default"
            })

        # Body text / pretext
        for field_key in ("pretext", "text"):
            value = attachment.get(field_key, "")
            if value:
                body.append({
                    "type": "TextBlock",
                    "text": value,
                    "wrap": True,
                    "isSubtle": True,
                    "fontType": "Monospace" if field_key == "text" else "Default"
                })

        # Fields (key/value pairs)
        fields = attachment.get("fields", [])
        if fields:
            facts = [{"title": f.get("title", ""), "value": f.get("value", "")} for f in fields]
            body.append({"type": "FactSet", "facts": facts})

    # Fallback if nothing was parsed
    if not body:
        body.append({
            "type": "TextBlock",
            "text": json.dumps(atlantis_payload),
            "wrap": True
        })

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": body
                }
            }
        ]
    }


def is_atlantis_native(payload: dict) -> bool:
    """Heuristic: Atlantis's kind:http body uses PascalCase top-level fields."""
    if not isinstance(payload, dict):
        return False
    return "Repo" in payload or "Pull" in payload or "Success" in payload


def build_card_from_atlantis(payload: dict) -> dict:
    """Convert Atlantis's native HTTP-webhook payload into a Teams Adaptive Card."""
    success = bool(payload.get("Success", False))
    repo = payload.get("Repo") or {}
    pull = payload.get("Pull") or {}
    user = payload.get("User") or {}

    repo_full = repo.get("FullName") or "/".join(
        p for p in (repo.get("Owner"), repo.get("Name")) if p
    )
    pull_num = pull.get("Num")
    pull_url = pull.get("URL", "")
    pull_author = pull.get("Author", "")
    username = user.get("Username", "")
    project = payload.get("Project", "")
    workspace = payload.get("Workspace", "")
    directory = payload.get("Directory", "")

    title = "Atlantis apply succeeded" if success else "Atlantis apply failed"
    color = "Good" if success else "Attention"

    facts = []
    if repo_full:
        facts.append({"title": "Repo", "value": repo_full})
    if pull_num is not None:
        pull_value = f"[#{pull_num}]({pull_url})" if pull_url else f"#{pull_num}"
        if pull_author:
            pull_value += f" by {pull_author}"
        facts.append({"title": "Pull request", "value": pull_value})
    if project:
        facts.append({"title": "Project", "value": project})
    if workspace:
        facts.append({"title": "Workspace", "value": workspace})
    if directory:
        facts.append({"title": "Directory", "value": directory})
    if username:
        facts.append({"title": "Triggered by", "value": username})

    body = [{
        "type": "TextBlock",
        "text": title,
        "wrap": True,
        "size": "Medium",
        "weight": "Bolder",
        "color": color,
    }]
    if facts:
        body.append({"type": "FactSet", "facts": facts})

    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.2",
                "body": body,
            },
        }],
    }


@app.route("/relay", methods=["POST"])
def relay():
    try:
        payload = request.get_json(force=True)
        logger.info("Received payload: %s", json.dumps(payload))

        card = (
            build_card_from_atlantis(payload)
            if is_atlantis_native(payload)
            else build_adaptive_card(payload)
        )
        logger.info("Sending card: %s", json.dumps(card))

        resp = requests.post(TEAMS_WEBHOOK_URL, json=card, timeout=10)
        logger.info("Teams response: %s %s", resp.status_code, resp.text)

        if resp.status_code not in (200, 202):
            return jsonify({"error": "Teams rejected the payload", "status": resp.status_code}), 502

        return jsonify({"ok": True}), 200

    except Exception as e:
        logger.exception("Relay error")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5025))
    logger.info("Starting relay on port %d", port)
    app.run(host="0.0.0.0", port=port)


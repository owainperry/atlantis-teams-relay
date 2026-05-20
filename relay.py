#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Quantifi Solutions Inc
# SPDX-License-Identifier: MIT
"""
Atlantis -> Microsoft Teams Relay
Receives Slack-format webhooks from Atlantis and forwards them
to a Microsoft Teams Workflows webhook as Adaptive Cards.

Usage:
    pip install flask requests
    TEAMS_WEBHOOK_URL=https://your-url python atlantis_teams_relay.py

Atlantis config:
    Set your webhook URL to http://this-server:5025/relay
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


@app.route("/relay", methods=["POST"])
def relay():
    try:
        payload = request.get_json(force=True)
        logger.info("Received payload: %s", json.dumps(payload))

        card = build_adaptive_card(payload)
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


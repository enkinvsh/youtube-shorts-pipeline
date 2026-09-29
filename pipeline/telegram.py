"""Send generated videos to Telegram."""

import os
from pathlib import Path

import requests

from .log import log

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003845353455")
# AI Новости topic = 32
TELEGRAM_TOPIC_ID = int(os.environ.get("TELEGRAM_TOPIC_ID", "32"))


def send_video(
    video_path: Path,
    caption: str = "",
    bot_token: str = "",
    chat_id: str = "",
    topic_id: int | None = None,
) -> bool:
    """Send an MP4 video to Telegram chat/topic.

    Returns True on success, False on failure (never raises).
    """
    token = bot_token or TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID
    topic = topic_id if topic_id is not None else TELEGRAM_TOPIC_ID

    if not token or not chat:
        log("Telegram not configured — skipping send")
        return False

    if not video_path.exists():
        log(f"Video not found: {video_path}")
        return False

    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb > 50:
        log(f"Video too large for Telegram ({size_mb:.1f}MB > 50MB limit)")
        return False

    url = f"https://api.telegram.org/bot{token}/sendVideo"
    data = {
        "chat_id": chat,
        "caption": caption[:1024] if caption else "",
        "parse_mode": "HTML",
    }
    if topic:
        data["message_thread_id"] = topic

    log(f"Sending video to Telegram ({size_mb:.1f}MB)...")

    try:
        with open(video_path, "rb") as f:
            r = requests.post(
                url,
                data=data,
                files={"video": (video_path.name, f, "video/mp4")},
                timeout=120,
            )

        if r.status_code == 200 and r.json().get("ok"):
            log("Video sent to Telegram successfully")
            return True
        else:
            detail = r.json().get("description", r.text[:200])
            log(f"Telegram send failed: {r.status_code} — {detail}")
            return False

    except Exception as e:
        log(f"Telegram send error: {e}")
        return False

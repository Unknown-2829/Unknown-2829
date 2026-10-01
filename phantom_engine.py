"""
Dynamic GitHub Stats Updater
Fetches GitHub streak data and updates README.md with conditional theming.

Streak Tiers:
  1-3   → Green theme  (fresh, growing)
  4-8   → Blue theme   (steady, consistent)
  9-29  → Red theme    (on fire, dominant)
  30+   → Black theme  (legendary, dark elite)

Streak Status:
  active  → streak > 0, use tier themes above
  broken  → streak just dropped to 0 (shows "💔 Streak Dropped" badge)
  offline → streak has been 0 for 2+ days (rotating secret/offline messages)
"""

import hmac as _hmac
import html
import os

import re
import sys
import json
import time
import shutil
import tempfile
import argparse
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo

# Ensure emoji and Unicode print correctly on all platforms (incl. Windows CI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

IST = ZoneInfo("Asia/Kolkata")

# Path to the file that persists streak state between runs
STATE_FILE = os.environ.get("STREAK_STATE_PATH", ".streak_state.json")

# Directory for cached SVG assets
ASSETS_DIR = os.environ.get("ASSETS_DIR", "assets")

# Rotating messages shown when streak has been 0 for 2+ days.
# Each entry is (emoji, label).
OFFLINE_MESSAGES = [
    ("😶\u200d🌫️", "Cooking Something Secretly"),
    ("🤫", "Shh... Working on Something Big"),
    ("💤", "Offline — Taking a Break"),
    ("🔕", "Busy with Real Life"),
    ("🌑", "Not Growing... Or Am I?"),
]


# ── Theme Definitions ──────────────────────────────────────────────────────────
THEMES = {
    "green": {
        "label": "🌱 Growing",
        "tier": "GROWING",
        "streak_bg": "0d1117",
        "ring": "00e676",
        "fire": "69f0ae",
        "curr_streak_num": "ffffff",
        "curr_streak_label": "00e676",
        "side_labels": "b9f6ca",
        "side_nums": "ffffff",
        "dates": "a5d6a7",
        "stroke": "1b5e20",
        "gradient_start": "0d1117",
        "gradient_mid": "00e676",
        "gradient_end": "69f0ae",
        "badge_color": "00e676",
        # Capsule render effect
        "capsule_type": "waving",
        "capsule_animation": "fadeIn",
        "capsule_height": "3",
        # Graph area opacity via color saturation
        "graph_area": "true",
    },
    "blue": {
        "label": "💎 Consistent",
        "tier": "CONSISTENT",
        "streak_bg": "0d1117",
        "ring": "448aff",
        "fire": "82b1ff",
        "curr_streak_num": "ffffff",
        "curr_streak_label": "448aff",
        "side_labels": "90caf9",
        "side_nums": "ffffff",
        "dates": "bbdefb",
        "stroke": "1565c0",
        "gradient_start": "0d1117",
        "gradient_mid": "448aff",
        "gradient_end": "82b1ff",
        "badge_color": "448aff",
        # Capsule render effect
        "capsule_type": "soft",
        "capsule_animation": "twinkling",
        "capsule_height": "4",
        # Graph area opacity via color saturation
        "graph_area": "true",
    },
    "red": {
        "label": "🔥 On Fire",
        "tier": "ON FIRE",
        "streak_bg": "0d1117",
        "ring": "ff1744",
        "fire": "ff5252",
        "curr_streak_num": "ffffff",
        "curr_streak_label": "ff1744",
        "side_labels": "ff8a80",
        "side_nums": "ffffff",
        "dates": "ef9a9a",
        "stroke": "b71c1c",
        "gradient_start": "0d1117",
        "gradient_mid": "ff1744",
        "gradient_end": "ff5252",
        "badge_color": "ff1744",
        # Capsule render effect
        "capsule_type": "shark",
        "capsule_animation": "scaleIn",
        "capsule_height": "5",
        # Graph area opacity via color saturation
        "graph_area": "true",
    },
    "black": {
        "label": "👑 Legendary",
        "tier": "LEGENDARY",
        "streak_bg": "000000",
        "ring": "ffffff",
        "fire": "b0b0b0",
        "curr_streak_num": "ffffff",
        "curr_streak_label": "e0e0e0",
        "side_labels": "bdbdbd",
        "side_nums": "ffffff",
        "dates": "757575",
        "stroke": "424242",
        "gradient_start": "000000",
        "gradient_mid": "212121",
        "gradient_end": "424242",
        "badge_color": "ffffff",
        # Capsule render effect
        "capsule_type": "cylinder",
        "capsule_animation": "blinking",
        "capsule_height": "6",
        # Graph area opacity via color saturation
        "graph_area": "true",
    },

    # ── Festival / Event themes ────────────────────────────────────────────────
    "sunday": {
        "label": "☁️ Recharging",           "tier": "SUNDAY",
        "streak_bg": "0a0a1a",              "ring": "7c83fd",
        "fire": "00d2c8",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "7c83fd",      "side_labels": "a8b2ff",
        "side_nums": "ffffff",              "dates": "6e7bcc",
        "stroke": "2e3170",                 "gradient_start": "0a0a1a",
        "gradient_mid": "7c83fd",           "gradient_end": "00d2c8",
        "badge_color": "7c83fd",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "new_year": {
        "label": "🎆 Happy New Year",        "tier": "NEW YEAR",
        "streak_bg": "0a0000",              "ring": "ffd700",
        "fire": "fffacd",                   "curr_streak_num": "ffd700",
        "curr_streak_label": "ffffff",      "side_labels": "fffacd",
        "side_nums": "ffd700",              "dates": "c9a800",
        "stroke": "8b6914",                 "gradient_start": "0a0000",
        "gradient_mid": "ffd700",           "gradient_end": "ff6b6b",
        "badge_color": "ffd700",            "capsule_type": "cylinder",
        "capsule_animation": "blinking",    "capsule_height": "6",
        "graph_area": "true",
    },
    "holi": {
        "label": "🎨 Happy Holi",            "tier": "HOLI",
        "streak_bg": "0d0010",              "ring": "ff006e",
        "fire": "ffbe0b",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "ff006e",      "side_labels": "fb5607",
        "side_nums": "ffffff",              "dates": "8338ec",
        "stroke": "3a86ff",                 "gradient_start": "ff006e",
        "gradient_mid": "ffbe0b",           "gradient_end": "3a86ff",
        "badge_color": "ff006e",            "capsule_type": "waving",
        "capsule_animation": "fadeIn",      "capsule_height": "5",
        "graph_area": "true",
    },
    "diwali": {
        "label": "🪔 Happy Diwali",          "tier": "DIWALI",
        "streak_bg": "0a0500",              "ring": "ff9500",
        "fire": "ffd700",                   "curr_streak_num": "ffd700",
        "curr_streak_label": "ff9500",      "side_labels": "ffb347",
        "side_nums": "ffd700",              "dates": "cc7700",
        "stroke": "8b4513",                 "gradient_start": "0a0500",
        "gradient_mid": "ff9500",           "gradient_end": "ffd700",
        "badge_color": "ff9500",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "6",
        "graph_area": "true",
    },
    "halloween": {
        "label": "🎃 Happy Halloween",       "tier": "HALLOWEEN",
        "streak_bg": "0a0500",              "ring": "ff6600",
        "fire": "ff8800",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "ff6600",      "side_labels": "cc5500",
        "side_nums": "ffffff",              "dates": "993300",
        "stroke": "5c1a00",                 "gradient_start": "0a0500",
        "gradient_mid": "ff6600",           "gradient_end": "1a0033",
        "badge_color": "ff6600",            "capsule_type": "shark",
        "capsule_animation": "blinking",    "capsule_height": "6",
        "graph_area": "true",
    },
    "christmas": {
        "label": "🎄 Merry Christmas",       "tier": "CHRISTMAS",
        "streak_bg": "000d00",              "ring": "00c851",
        "fire": "ff1744",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "00c851",      "side_labels": "b9f6ca",
        "side_nums": "ffffff",              "dates": "fffde7",
        "stroke": "1b5e20",                 "gradient_start": "000d00",
        "gradient_mid": "00c851",           "gradient_end": "ff1744",
        "badge_color": "00c851",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    "independence_day": {
        "label": "🇮🇳 Jai Hind",             "tier": "JAI HIND",
        "streak_bg": "000000",              "ring": "ff9933",
        "fire": "138808",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "ff9933",      "side_labels": "ffffff",
        "side_nums": "ff9933",              "dates": "000080",
        "stroke": "000080",                 "gradient_start": "ff9933",
        "gradient_mid": "ffffff",           "gradient_end": "138808",
        "badge_color": "ff9933",            "capsule_type": "waving",
        "capsule_animation": "fadeIn",      "capsule_height": "5",
        "graph_area": "true",
    },
    "republic_day": {
        "label": "🇮🇳 Republic Day",          "tier": "REPUBLIC",
        "streak_bg": "00003a",              "ring": "ff9933",
        "fire": "138808",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "ff9933",      "side_labels": "ffffff",
        "side_nums": "ff9933",              "dates": "4169e1",
        "stroke": "000080",                 "gradient_start": "00003a",
        "gradient_mid": "ff9933",           "gradient_end": "138808",
        "badge_color": "ff9933",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "5",
        "graph_area": "true",
    },
    "programmer_day": {
        "label": "💻 Programmer's Day",      "tier": "DAY 256",
        "streak_bg": "001100",              "ring": "00ff41",
        "fire": "00cc33",                   "curr_streak_num": "00ff41",
        "curr_streak_label": "00cc33",      "side_labels": "39ff14",
        "side_nums": "00ff41",              "dates": "008000",
        "stroke": "003300",                 "gradient_start": "001100",
        "gradient_mid": "00ff41",           "gradient_end": "003300",
        "badge_color": "00ff41",            "capsule_type": "cylinder",
        "capsule_animation": "blinking",    "capsule_height": "5",
        "graph_area": "true",
    },
    "valentine": {
        "label": "💖 Valentine's Day",       "tier": "LOVE",
        "streak_bg": "0d0005",              "ring": "ff1493",
        "fire": "ff69b4",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "ff1493",      "side_labels": "ffb6c1",
        "side_nums": "ffffff",              "dates": "db1b6e",
        "stroke": "8b0032",                 "gradient_start": "0d0005",
        "gradient_mid": "ff1493",           "gradient_end": "ff69b4",
        "badge_color": "ff1493",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "pi_day": {
        "label": "π Pi Day",                "tier": "3.14159",
        "streak_bg": "050010",              "ring": "9c27b0",
        "fire": "ce93d8",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "9c27b0",      "side_labels": "e1bee7",
        "side_nums": "ffffff",              "dates": "7b1fa2",
        "stroke": "4a148c",                 "gradient_start": "050010",
        "gradient_mid": "9c27b0",           "gradient_end": "3f51b5",
        "badge_color": "9c27b0",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "star_wars": {
        "label": "⚔️ May the Force Be With You", "tier": "MAY THE 4TH",
        "streak_bg": "000000",              "ring": "ffe81f",
        "fire": "4fc3f7",                   "curr_streak_num": "ffe81f",
        "curr_streak_label": "4fc3f7",      "side_labels": "ffe81f",
        "side_nums": "ffffff",              "dates": "b0bec5",
        "stroke": "333333",                 "gradient_start": "000000",
        "gradient_mid": "1a1a2e",           "gradient_end": "000000",
        "badge_color": "ffe81f",            "capsule_type": "cylinder",
        "capsule_animation": "blinking",    "capsule_height": "6",
        "graph_area": "true",
    },
    "teachers_day": {
        "label": "🎓 Teachers' Day",         "tier": "GRATITUDE",
        "streak_bg": "0a0500",              "ring": "f5a623",
        "fire": "f8d57e",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "f5a623",      "side_labels": "f8d57e",
        "side_nums": "ffffff",              "dates": "c47d0e",
        "stroke": "7a4d00",                 "gradient_start": "0a0500",
        "gradient_mid": "f5a623",           "gradient_end": "8b4513",
        "badge_color": "f5a623",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "gandhi": {
        "label": "☮️ Gandhi Jayanti",        "tier": "PEACE",
        "streak_bg": "00001a",              "ring": "87ceeb",
        "fire": "b0e0e6",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "87ceeb",      "side_labels": "e0f0ff",
        "side_nums": "ffffff",              "dates": "5b9bd5",
        "stroke": "1a3d5c",                 "gradient_start": "00001a",
        "gradient_mid": "87ceeb",           "gradient_end": "b0e0e6",
        "badge_color": "87ceeb",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "3",
        "graph_area": "true",
    },
    "makar_sankranti": {
        "label": "🪁 Makar Sankranti",       "tier": "SANKRANTI",
        "streak_bg": "050a00",              "ring": "f9c74f",
        "fire": "f8961e",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "f9c74f",      "side_labels": "ffd166",
        "side_nums": "ffffff",              "dates": "e07b00",
        "stroke": "7a4000",                 "gradient_start": "050a00",
        "gradient_mid": "f9c74f",           "gradient_end": "43aa8b",
        "badge_color": "f9c74f",            "capsule_type": "waving",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "eid": {
        "label": "🌙 Eid Mubarak",           "tier": "EID",
        "streak_bg": "001a0a",              "ring": "00b4d8",
        "fire": "90e0ef",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "00b4d8",      "side_labels": "caf0f8",
        "side_nums": "ffffff",              "dates": "0077b6",
        "stroke": "023e8a",                 "gradient_start": "001a0a",
        "gradient_mid": "00b4d8",           "gradient_end": "ffd700",
        "badge_color": "00b4d8",            "capsule_type": "soft",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    "shivratri": {
        "label": "🕉️ Har Har Mahadev",       "tier": "SHIVRATRI",
        "streak_bg": "000000",              "ring": "6a0dad",
        "fire": "9b59b6",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "6a0dad",      "side_labels": "d7bde2",
        "side_nums": "ffffff",              "dates": "8e44ad",
        "stroke": "4a0080",                 "gradient_start": "000000",
        "gradient_mid": "6a0dad",           "gradient_end": "1a0033",
        "badge_color": "6a0dad",            "capsule_type": "cylinder",
        "capsule_animation": "blinking",    "capsule_height": "6",
        "graph_area": "true",
    },
    "raksha_bandhan": {
        "label": "🪢 Raksha Bandhan",         "tier": "BOND",
        "streak_bg": "0a0005",              "ring": "e91e8c",
        "fire": "ffc0cb",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "e91e8c",      "side_labels": "ffb6c1",
        "side_nums": "ffffff",              "dates": "c2185b",
        "stroke": "880e4f",                 "gradient_start": "0a0005",
        "gradient_mid": "e91e8c",           "gradient_end": "ffd700",
        "badge_color": "e91e8c",            "capsule_type": "soft",
        "capsule_animation": "fadeIn",      "capsule_height": "4",
        "graph_area": "true",
    },
    "janmashtami": {
        "label": "🦚 Jai Shri Krishna",      "tier": "KRISHNA",
        "streak_bg": "000a05",              "ring": "1565c0",
        "fire": "ffd700",                   "curr_streak_num": "ffd700",
        "curr_streak_label": "1565c0",      "side_labels": "90caf9",
        "side_nums": "ffd700",              "dates": "0d47a1",
        "stroke": "01579b",                 "gradient_start": "000a05",
        "gradient_mid": "1565c0",           "gradient_end": "ffd700",
        "badge_color": "1565c0",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    "ganesh_chaturthi": {
        "label": "🐘 Ganpati Bappa Morya",   "tier": "BAPPA",
        "streak_bg": "050500",              "ring": "ff6f00",
        "fire": "ffd600",                   "curr_streak_num": "ffd600",
        "curr_streak_label": "ff6f00",      "side_labels": "ffe082",
        "side_nums": "ffd600",              "dates": "e65100",
        "stroke": "bf360c",                 "gradient_start": "050500",
        "gradient_mid": "ff6f00",           "gradient_end": "ffd600",
        "badge_color": "ff6f00",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    "navratri": {
        "label": "🪔 Navratri",              "tier": "NAVRATRI",
        "streak_bg": "0a0005",              "ring": "e040fb",
        "fire": "ff4081",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "e040fb",      "side_labels": "f48fb1",
        "side_nums": "ffffff",              "dates": "ad1457",
        "stroke": "6a1b9a",                 "gradient_start": "0a0005",
        "gradient_mid": "e040fb",           "gradient_end": "ff9100",
        "badge_color": "e040fb",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    "dussehra": {
        "label": "🏹 Dussehra",              "tier": "VICTORY",
        "streak_bg": "050000",              "ring": "ff3d00",
        "fire": "ffd740",                   "curr_streak_num": "ffd740",
        "curr_streak_label": "ff3d00",      "side_labels": "ffab40",
        "side_nums": "ffd740",              "dates": "dd2c00",
        "stroke": "870000",                 "gradient_start": "050000",
        "gradient_mid": "ff3d00",           "gradient_end": "ffd740",
        "badge_color": "ff3d00",            "capsule_type": "shark",
        "capsule_animation": "scaleIn",     "capsule_height": "5",
        "graph_area": "true",
    },
    "anniversary": {
        "label": "🎉 Account Anniversary",   "tier": "ANNIVERSARY",
        "streak_bg": "050010",              "ring": "6e3aff",
        "fire": "00d9ff",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "6e3aff",      "side_labels": "a78bfa",
        "side_nums": "ffffff",              "dates": "4c1d95",
        "stroke": "2d0082",                 "gradient_start": "050010",
        "gradient_mid": "6e3aff",           "gradient_end": "00d9ff",
        "badge_color": "6e3aff",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "5",
        "graph_area": "true",
    },
    # ── Mystery / Special (birthday + decoys) — no identifying info ────────────
    "special": {
        "label": "✨ Today feels different.", "tier": "PHANTOM",
        "streak_bg": "030010",              "ring": "bf00ff",
        "fire": "00f5ff",                   "curr_streak_num": "ffffff",
        "curr_streak_label": "bf00ff",      "side_labels": "e0aaff",
        "side_nums": "ffffff",              "dates": "9900cc",
        "stroke": "4b0080",                 "gradient_start": "030010",
        "gradient_mid": "bf00ff",           "gradient_end": "00f5ff",
        "badge_color": "bf00ff",            "capsule_type": "waving",
        "capsule_animation": "twinkling",   "capsule_height": "6",
        "graph_area": "true",
    },
}

# Tier boundaries: 1–3, 4–8, 9–29, 30+
_TIER_BOUNDARIES = [
    (1, 3, "green"),
    (4, 8, "blue"),
    (9, 29, "red"),
    (30, None, "black"),
]


def get_theme_name_for_streak(streak: int) -> str:
    """Return the theme name based on current streak value.

    Tier boundaries: 1–3 green, 4–8 blue, 9–29 red, 30+ black.
    """
    for lo, hi, name in _TIER_BOUNDARIES:
        if hi is None or streak <= hi:
            if streak >= lo:
                return name
    return "green"


def get_theme_for_streak(streak: int) -> dict:
    """Return the theme dictionary based on current streak value."""
    return THEMES[get_theme_name_for_streak(streak)]


# ── Special / Mystery day (Section 6) ─────────────────────────────────────────
# Only is_special_today() and special_seed() know about the secret.
# Nothing else may know WHY a day is special.

def _mmdd_env() -> str | None:
    """Return SECRET_MMDD from environment if it is a valid MM-DD string, else None.

    Accepts: 01-01 through 12-31 (basic range check — does not verify month/day
    combinations like Feb 30).  Logs a warning on malformed values without
    revealing the secret value.
    """
    import re as _re
    raw = os.environ.get("SECRET_MMDD", "").strip()
    if not raw:
        return None
    if not _re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", raw):
        print(
            "Warning: SECRET_MMDD is set but does not match MM-DD format — "
            "special-day theme disabled.",
            file=sys.stderr,
        )
        return None
    return raw



def is_special_today(now: datetime) -> bool:
    """
    Return True if today is the real special day OR a HMAC-derived decoy day.
    Uses only SECRET_MMDD from the environment — value never logged or stored.
    Returns False silently if the secret is not set.
    """
    secret = _mmdd_env()
    if not secret:
        return False
    today_mmdd = now.strftime("%m-%d")
    # Real day check
    if today_mmdd == secret:
        return True
    salt = os.environ.get("SECRET_SALT", "").strip()
    hmac_key = (secret + salt).encode() if salt else secret.encode()
    _ref_year = 2001  # non-leap: decoy MM-DD stays stable across leap years
    for i in range(9):
        raw = _hmac.new(hmac_key, i.to_bytes(1, "big"), "sha256").digest()
        day_of_year = (int.from_bytes(raw[:2], "big") % 365) + 1
        candidate = (date(_ref_year, 1, 1) + timedelta(days=day_of_year - 1))
        if candidate.strftime("%m-%d") == today_mmdd:
            return True
    return False





def special_seed(now: datetime) -> int:
    """Deterministic seed for special-day content selection."""
    secret = _mmdd_env() or "phantom"
    raw = _hmac.new(
        secret.encode(), now.strftime("%Y-%m-%d").encode(), "sha256"
    ).digest()
    return int.from_bytes(raw[:4], "big")


# ── Festival / Event data ──────────────────────────────────────────────────────

_EVENTS_FILE = os.path.join(
    os.path.dirname(__file__) if "__file__" in dir() else ".", "events_data.json"
)


def _load_events() -> dict:
    """Load events_data.json; return empty dict on failure."""
    try:
        with open(_EVENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def _lookup_festival(now: datetime) -> str | None:
    """
    Return the theme key for a lunisolar festival today, or None.
    Priority within festivals follows declaration order in events_data.json.
    """
    data = _load_events()
    festivals = data.get("festivals", {})
    today_mmdd = now.strftime("%m-%d")
    year_str = str(now.year)
    for key, info in festivals.items():
        dates = info.get("dates", {})
        if dates.get(year_str) == today_mmdd:
            # Map JSON key → THEMES key (they match by design)
            if key in THEMES:
                return key
    return None


def fetch_github_anniversary(username: str, token: str | None = None) -> str | None:
    """
    Return the account creation month-day as 'MM-DD', or None on failure.
    Uses the public /users endpoint — no auth required but token avoids rate limits.
    """
    try:
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        req = urllib.request.Request(
            f"https://api.github.com/users/{username}", headers=headers
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        created_at = data.get("created_at", "")          # e.g. "2021-03-15T10:22:00Z"
        if created_at:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%m-%d")
    except Exception as exc:
        print(f"  fetch_github_anniversary: {exc}", file=sys.stderr)
    return None


def _check_missing_festival_years() -> None:
    """
    On Dec 1, open a GitHub issue reminder if events_data.json lacks
    next year's festival rows. Requires GITHUB_TOKEN + GITHUB_USERNAME.
    """
    now = _now_ist()
    if now.month != 12 or now.day != 1:
        return
    next_year = str(now.year + 1)
    data = _load_events()
    festivals = data.get("festivals", {})
    missing = [k for k, v in festivals.items() if next_year not in v.get("dates", {})]
    if not missing:
        return

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    username = os.environ.get("GITHUB_USERNAME", "Unknown-2829")
    if not token:
        print(f"Warning: events_data.json missing {next_year} rows for: {missing}",
              file=sys.stderr)
        return

    title = f"[reminder] Add {next_year} festival dates to events_data.json"
    body = (
        f"The following festivals are missing {next_year} dates in `events_data.json`:\n\n"
        + "\n".join(f"- `{k}`" for k in missing)
        + "\n\nPlease verify against an authoritative panchang / Islamic calendar "
          "and update before 31 Dec."
    )
    try:
        payload = json.dumps({"title": title, "body": body, "labels": ["reminder"]}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{username}/{username}/issues",
            data=payload,
            headers={
                "Authorization": f"token {token}",
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            issue = json.loads(resp.read().decode())
            print(f"Opened reminder issue #{issue.get('number')}: {title}")
    except Exception as exc:
        print(f"Warning: could not open reminder issue: {exc}", file=sys.stderr)


# ── Fixed calendar events (MM-DD) ─────────────────────────────────────────────

_FIXED_EVENTS: list[tuple[str, str, str]] = [
    # (MM-DD, theme_key, label)  — checked in priority order
    ("12-31", "new_year",          "New Year's Eve"),
    ("01-01", "new_year",          "New Year's Day"),
    ("01-02", "new_year",          "New Year — Day 2"),
    ("01-14", "makar_sankranti",   "Makar Sankranti"),
    ("01-26", "republic_day",      "Republic Day"),
    ("02-14", "valentine",         "Valentine's Day"),
    ("03-14", "pi_day",            "Pi Day"),
    ("05-04", "star_wars",         "Star Wars Day"),
    ("08-15", "independence_day",  "Independence Day"),
    ("09-05", "teachers_day",      "Teachers' Day"),
    ("10-02", "gandhi",            "Gandhi Jayanti"),
    ("10-31", "halloween",         "Halloween"),
    ("12-24", "christmas",         "Christmas Eve"),
    ("12-25", "christmas",         "Christmas Day"),
    ("12-26", "christmas",         "Boxing Day"),
]

# ── MYSTERY lines pool (special days) ─────────────────────────────────────────
_MYSTERY_LINES = [
    "✨ Today feels different.",
    "🌌 Something's in the air.",
    "🔮 The phantom stirs.",
    "💫 An unusual alignment.",
    "🌙 The void whispers tonight.",
    "⚡ Charged with something unseen.",
    "🎭 Masks on. Lights dim. Begin.",
    "🌑 Every shadow has a source.",
    "🕯️ One flicker changes everything.",
    "∞ Some loops don't close.",
]


# ── Main theme picker ──────────────────────────────────────────────────────────

def pick_theme(
    now_ist: datetime,
    streak: int,
    state: dict,
    username: str = "Unknown-2829",
) -> tuple[str, dict, str]:
    """
    Return (theme_name, theme_dict, note) using priority order:

      1. special / decoy day  (SECRET_MMDD — section 6)
      2. fixed-date event     (New Year, Republic Day, etc.)
      3. lunisolar festival   (events_data.json)
      4. GitHub anniversary
      5. Programmer's Day     (day 256 of the year)
      6. Sunday
      7. streak tier          (existing behaviour)
    """
    today_mmdd = now_ist.strftime("%m-%d")
    day_of_year = now_ist.timetuple().tm_yday

    # ── 1. Special / mystery ─────────────────────────────────────────────────
    if is_special_today(now_ist):
        seed = special_seed(now_ist)
        line = _MYSTERY_LINES[seed % len(_MYSTERY_LINES)]
        print("theme=special")
        return "special", THEMES["special"], line

    # ── 2. Fixed-date events ─────────────────────────────────────────────────
    for mmdd, theme_key, label in _FIXED_EVENTS:
        if today_mmdd == mmdd:
            note = THEMES[theme_key]["label"]
            return theme_key, THEMES[theme_key], note

    # ── 3. Lunisolar festivals ───────────────────────────────────────────────
    festival_key = _lookup_festival(now_ist)
    if festival_key:
        note = THEMES[festival_key]["label"]
        return festival_key, THEMES[festival_key], note

    # ── 4. GitHub account anniversary ───────────────────────────────────────
    token = (
        os.environ.get("GH_STATS_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )
    anniv_mmdd = fetch_github_anniversary(username, token)
    if anniv_mmdd and today_mmdd == anniv_mmdd:
        note = THEMES["anniversary"]["label"]
        return "anniversary", THEMES["anniversary"], note

    # ── 5. Programmer's Day (day 256) ────────────────────────────────────────
    if day_of_year == 256:
        note = THEMES["programmer_day"]["label"]
        return "programmer_day", THEMES["programmer_day"], note

    # ── 6. Sunday ────────────────────────────────────────────────────────────
    if now_ist.weekday() == 6:  # Sunday
        note = "Sunday — recharging 🔋"
        return "sunday", THEMES["sunday"], note

    # ── 7. Streak tier (default) ─────────────────────────────────────────────
    theme_name = get_theme_name_for_streak(streak)
    theme = THEMES[theme_name]
    return theme_name, theme, ""




# ── SVG Asset Caching ──────────────────────────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_BACKOFF = [5, 15, 30]   # seconds between attempts
_TIMEOUT = 30            # seconds per request
_MIN_SIZE = 2 * 1024     # 2 KB
_MAX_SIZE = 500 * 1024   # 500 KB


def _validate_svg(data: bytes) -> bool:
    """Return True if data looks like a valid, script-free SVG."""
    text = data.decode("utf-8", errors="replace")
    # Strip optional XML prolog
    stripped = text.lstrip()
    if stripped.startswith("<?xml"):
        stripped = stripped[stripped.find("?>") + 2:].lstrip()
    if not stripped.startswith("<svg"):
        return False
    if not (_MIN_SIZE <= len(data) <= _MAX_SIZE):
        return False
    try:
        root = ET.fromstring(data.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return False
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    ns_prefix = "{" + ns + "}" if ns else ""
    for elem in root.iter():
        tag = elem.tag
        if tag == f"{ns_prefix}script" or tag == "script":
            return False
    return True


def cache_graph(url: str, dest: str, timeout: int = _TIMEOUT) -> bool:
    """
    Download an SVG from *url* and atomically write it to *dest*.

    Makes up to 3 attempts.  On failure waits _BACKOFF[attempt] seconds
    before the next try (5 s after attempt 0, 15 s after attempt 1).
    Validates the response (HTTP 200, valid SVG, 2 KB–500 KB, no <script>).
    If all attempts fail the existing *dest* file is left untouched.

    The *timeout* parameter controls per-request timeout in seconds
    (default: _TIMEOUT=30).  Pass a small value in tests.

    Returns True if a new file was written, False otherwise.
    """
    os.makedirs(os.path.dirname(dest) if os.path.dirname(dest) else ".", exist_ok=True)

    for attempt, backoff in enumerate(_BACKOFF):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status != 200:
                    print(
                        f"  cache_graph attempt {attempt + 1}: HTTP {resp.status}",
                        file=sys.stderr,
                    )
                    raise ValueError(f"HTTP {resp.status}")
                data = resp.read()
        except Exception as exc:
            print(
                f"  cache_graph attempt {attempt + 1} failed: {exc}",
                file=sys.stderr,
            )
            if attempt < len(_BACKOFF) - 1:
                print(f"  Retrying in {backoff} s…", file=sys.stderr)
                time.sleep(backoff)
            continue

        if not _validate_svg(data):
            print(
                f"  cache_graph attempt {attempt + 1}: invalid SVG "
                f"(size={len(data)}, starts={data[:60]!r})",
                file=sys.stderr,
            )
            if attempt < len(_BACKOFF) - 1:
                time.sleep(backoff)
            continue

        # Atomic write: temp file → validate → replace
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(dest) or ".", suffix=".tmp"
        )
        try:
            with os.fdopen(tmp_fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp_path, dest)
            print(f"  cache_graph: cached {dest} ({len(data)} bytes)")
            return True
        except Exception as exc:
            print(f"  cache_graph: write failed: {exc}", file=sys.stderr)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False


    print(
        f"Warning: All cache_graph attempts failed for {url}. "
        f"Keeping existing {dest}.",
        file=sys.stderr,
    )
    return False


# ── Streak State Persistence ───────────────────────────────────────────────────

def load_streak_state() -> dict:
    """Load the persisted streak state from disk."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"last_positive_streak": None, "streak_zero_since": None}


def save_streak_state(state: dict) -> None:
    """Persist the streak state to disk."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def _now_ist() -> datetime:
    """Return the current datetime in IST."""
    return datetime.now(IST)


def compute_streak_status(streak: int, state: dict) -> str:
    """
    Determine the display status for the current streak.

    Returns one of:
      'active'  – streak > 0, use normal tier themes
      'broken'  – streak just became 0 (was positive before, or < 2 days at 0)
      'offline' – streak has been 0 for 2+ days
    """
    if streak > 0:
        return "active"

    zero_since = state.get("streak_zero_since")
    if zero_since:
        try:
            zero_date = datetime.fromisoformat(zero_since).date()
            days_at_zero = (_now_ist().date() - zero_date).days
            if days_at_zero >= 2:
                return "offline"
        except ValueError:
            pass

    return "broken"


def update_streak_state(streak: int, state: dict) -> dict:
    """Return an updated state dict based on the current streak value."""
    today = _now_ist().date().isoformat()
    if streak > 0:
        state["last_positive_streak"] = streak
        state["streak_zero_since"] = None
    else:
        if state.get("streak_zero_since") is None:
            state["streak_zero_since"] = today
        # last_positive_streak is intentionally preserved for the "broken" message
    return state


# ── Streak Fetching ────────────────────────────────────────────────────────────

def _graphql_streak(username: str, token: str) -> int | None:
    """
    Fetch the current contribution streak via the GitHub GraphQL API.

    Uses the contribution calendar which counts all contribution types
    (commits, PRs, issues, reviews) and is accurate to the calendar day.
    Returns the streak count (0 is valid) or None on error.
    """
    today_ist = _now_ist().date()
    # Scan back 400 days — more than enough for any real streak
    from_date = (today_ist - timedelta(days=400)).isoformat()
    to_date = today_ist.isoformat()

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "login": username,
        "from": f"{from_date}T00:00:00Z",
        "to": f"{to_date}T23:59:59Z",
    }
    payload = json.dumps({"query": query, "variables": variables}).encode()
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=payload, headers=headers
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode())

    if "errors" in result:
        raise ValueError(f"GraphQL errors: {result['errors']}")

    weeks = (
        result["data"]["user"]["contributionsCollection"]
        ["contributionCalendar"]["weeks"]
    )

    # Flatten days in chronological order
    days: list[dict] = []
    for week in weeks:
        days.extend(week["contributionDays"])
    days.sort(key=lambda d: d["date"])

    # Build a set of dates with contributions
    active_dates: set[date] = {
        date.fromisoformat(d["date"])
        for d in days
        if d["contributionCount"] > 0
    }

    # Walk back from today counting consecutive days
    streak = 0
    check = today_ist
    # Allow today to not have contributions yet (it's still ongoing)
    if check not in active_dates:
        check -= timedelta(days=1)
    while check in active_dates:
        streak += 1
        check -= timedelta(days=1)

    return streak


def fetch_streak_from_svg(username: str) -> int:
    """
    Fetch the current streak by parsing the streak-stats.demolab.com SVG.
    This is the same service used to render the streak image in the README.
    """
    url = f"https://streak-stats.demolab.com?user={username}&hide_border=true"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        svg = resp.read().decode()

    # The SVG contains a unique "currstreak" animation on the current streak number
    match = re.search(
        r"animation:\s*currstreak[^>]*>\s*(\d[\d,]*)\s*</text>",
        svg,
    )
    if match:
        return int(match.group(1).replace(",", ""))

    raise ValueError("Could not find current streak number in SVG response")


def fetch_streak(username: str) -> int | None:
    """
    Fetch the current streak count for a GitHub user.

    Primary:  GitHub GraphQL contribution calendar (uses GH_STATS_TOKEN if
              set, otherwise GITHUB_TOKEN). Most accurate; counts all types.
    Fallback: Parses the streak-stats.demolab.com SVG.

    Returns the streak count (int, ≥ 0) or None if all sources fail.
    On None the caller must skip the run without changing README or state.
    """
    # Prefer GH_STATS_TOKEN (allows private contributions) over GITHUB_TOKEN
    token = (
        os.environ.get("GH_STATS_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )

    if token:
        try:
            streak = _graphql_streak(username, token)
            print(f"Streak from GraphQL API: {streak}")
            return streak
        except Exception as exc:
            print(
                f"Warning: GraphQL streak fetch failed: {exc}",
                file=sys.stderr,
            )

    # Fallback: parse streak from streak-stats.demolab.com SVG
    try:
        streak = fetch_streak_from_svg(username)
        print(f"Streak from streak-stats.demolab.com SVG (fallback): {streak}")
        return streak
    except Exception as exc:
        print(
            f"Warning: SVG streak fetch failed: {exc}",
            file=sys.stderr,
        )

    # All sources failed — return None so the caller can skip cleanly
    print(
        "Error: All streak sources failed. Skipping run to avoid false data.",
        file=sys.stderr,
    )
    return None


# ── README Generation ──────────────────────────────────────────────────────────

GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "Unknown-2829")
RAW_BASE = (
    f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_USERNAME}/main"
)


def _offline_note(now_ist: datetime | None = None) -> str:
    """Return a deterministic per-day rotating offline footer note."""
    if now_ist is None:
        now_ist = _now_ist()
    day_index = now_ist.timetuple().tm_yday
    emoji, label = OFFLINE_MESSAGES[day_index % len(OFFLINE_MESSAGES)]
    return f"{emoji} <i>{label}</i>"



# ── Stage 5: Traffic & Analytics ──────────────────────────────────────────────

_TRAFFIC_SUMMARY_FILE = os.environ.get("TRAFFIC_SUMMARY_PATH", ".traffic_summary.json")
_DATA_BRANCH          = "data"
_TRAFFIC_HISTORY_PATH = "data/traffic-history.json"
_MAX_DAILY_ROWS       = 400   # roll into monthly totals beyond this


def _load_traffic_summary() -> dict:
    """Load local traffic summary cache (on main branch). Returns {} on miss."""
    try:
        with open(_TRAFFIC_SUMMARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def _save_traffic_summary(data: dict) -> None:
    try:
        with open(_TRAFFIC_SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as exc:
        print(f"Warning: could not save traffic summary: {exc}", file=sys.stderr)


def fetch_traffic(username: str, token: str) -> dict | None:
    """
    Fetch profile-repo traffic from the GitHub API.
    Requires a token with repo scope (TRAFFIC_TOKEN or GH_STATS_TOKEN).
    Returns dict or None if token is missing / request fails.
    """
    if not token:
        return None
    repo = username   # profile repo has same name as username

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": _USER_AGENT,
    }

    def _get(path: str) -> dict | list | None:
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{username}/{repo}/{path}",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            print(f"  traffic {path}: {exc}", file=sys.stderr)
            return None

    views     = _get("traffic/views")
    clones    = _get("traffic/clones")
    referrers = _get("traffic/popular/referrers")
    paths     = _get("traffic/popular/paths")

    if views is None and clones is None:
        return None

    now_ist = _now_ist()
    today   = now_ist.strftime("%Y-%m-%d")

    # Extract today's row from the daily breakdown
    def _today(items: list | None, count_key: str, unique_key: str) -> tuple[int, int]:
        if not items:
            return 0, 0
        for row in items:
            if row.get("timestamp", "").startswith(today):
                return row.get(count_key, 0), row.get(unique_key, 0)
        # GitHub reports days in UTC midnight blocks — take latest if today not found
        if items:
            last = items[-1]
            return last.get(count_key, 0), last.get(unique_key, 0)
        return 0, 0

    v_day, uv_day = _today(
        (views or {}).get("views", []), "count", "uniques"
    )
    c_day, uc_day = _today(
        (clones or {}).get("clones", []), "count", "uniques"
    )

    top_refs = [
        {"ref": r.get("referrer"), "count": r.get("count", 0), "uniques": r.get("uniques", 0)}
        for r in (referrers or [])[:5]
    ]
    top_paths = [
        {"path": p.get("path"), "count": p.get("count", 0), "uniques": p.get("uniques", 0)}
        for p in (paths or [])[:5]
    ]

    # Rolling 14-day totals (full window returned by API)
    v14 = (views or {}).get("count", 0)
    uv14 = (views or {}).get("uniques", 0)
    c14 = (clones or {}).get("count", 0)

    return {
        "date": today,
        "views_today": v_day,
        "unique_visitors_today": uv_day,
        "clones_today": c_day,
        "unique_cloners_today": uc_day,
        "views_14d": v14,
        "unique_visitors_14d": uv14,
        "clones_14d": c14,
        "top_referrers": top_refs,
        "top_paths": top_paths,
    }


def _read_file_from_branch(
    owner: str, repo: str, path: str, branch: str, token: str
) -> tuple[str | None, str | None]:
    """
    Read a file's content and SHA from a specific branch via GitHub Contents API.
    Returns (content_str, sha) or (None, None) on 404/error.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": _USER_AGENT,
    }
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            f"?ref={branch}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            import base64
            content = base64.b64decode(data["content"]).decode("utf-8")
            return content, data["sha"]
    except Exception as exc:
        if "404" in str(exc) or "Not Found" in str(exc):
            return None, None
        print(f"  _read_file_from_branch {path}: {exc}", file=sys.stderr)
        return None, None


def _write_file_to_branch(
    owner: str, repo: str, path: str, branch: str,
    content_str: str, sha: str | None, commit_msg: str, token: str,
) -> bool:
    """
    Create or update a file on a branch via GitHub Contents API.
    Returns True on success.
    """
    import base64
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    payload: dict = {
        "message": commit_msg,
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            data=data, headers=headers, method="PUT",
        )
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as exc:
        print(f"  _write_file_to_branch {path}: {exc}", file=sys.stderr)
        return False


def _ensure_data_branch(owner: str, repo: str, token: str) -> bool:
    """
    Create the `data` branch from HEAD of main if it doesn't exist.
    Returns True if branch exists or was created successfully.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": _USER_AGENT,
    }
    # Check if branch exists
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/branches/{_DATA_BRANCH}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10):
            return True   # exists
    except Exception:
        pass   # 404 → need to create

    # Get main branch SHA
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/main",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            ref_data = json.loads(resp.read().decode())
            sha = ref_data["object"]["sha"]
    except Exception as exc:
        print(f"  _ensure_data_branch: could not get main SHA: {exc}", file=sys.stderr)
        return False

    # Create data branch
    try:
        payload = json.dumps({"ref": f"refs/heads/{_DATA_BRANCH}", "sha": sha}).encode()
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            data=payload,
            headers={**headers, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10):
            print(f"  Created branch '{_DATA_BRANCH}'")
            return True
    except Exception as exc:
        print(f"  _ensure_data_branch create failed: {exc}", file=sys.stderr)
        return False


def _roll_old_rows(rows: list[dict]) -> list[dict]:
    """
    If rows exceed _MAX_DAILY_ROWS, roll the oldest into monthly totals.
    Monthly summary rows have 'month': 'YYYY-MM' instead of 'date': 'YYYY-MM-DD'.
    """
    daily = [r for r in rows if "date" in r]
    monthly = [r for r in rows if "month" in r]

    if len(daily) <= _MAX_DAILY_ROWS:
        return rows

    # Keep the newest _MAX_DAILY_ROWS daily rows; roll the rest into months
    overflow = daily[:-_MAX_DAILY_ROWS]
    keep     = daily[-_MAX_DAILY_ROWS:]

    by_month: dict[str, dict] = {}
    for row in overflow:
        m = row["date"][:7]   # YYYY-MM
        if m not in by_month:
            by_month[m] = {"month": m, "views": 0, "unique_visitors": 0, "clones": 0}
        by_month[m]["views"]           += row.get("views_today", 0)
        by_month[m]["unique_visitors"] += row.get("unique_visitors_today", 0)
        by_month[m]["clones"]          += row.get("clones_today", 0)

    # Merge with existing monthly rows
    existing_months = {r["month"]: r for r in monthly}
    for m, totals in by_month.items():
        if m in existing_months:
            existing_months[m]["views"]           += totals["views"]
            existing_months[m]["unique_visitors"] += totals["unique_visitors"]
            existing_months[m]["clones"]          += totals["clones"]
        else:
            existing_months[m] = totals

    return sorted(existing_months.values(), key=lambda r: r["month"]) + keep


def append_traffic_to_data_branch(
    traffic: dict, username: str, token: str,
) -> bool:
    """
    Append today's traffic row to data/traffic-history.json on the `data` branch.
    Creates the branch and file if they don't exist.
    Skips silently if token is missing.
    Returns True on success.
    """
    if not token:
        return False

    repo = username
    _ensure_data_branch(username, repo, token)

    content_str, sha = _read_file_from_branch(
        username, repo, _TRAFFIC_HISTORY_PATH, _DATA_BRANCH, token
    )

    if content_str:
        try:
            rows = json.loads(content_str)
            if not isinstance(rows, list):
                rows = []
        except json.JSONDecodeError:
            rows = []
    else:
        rows = []

    # Deduplicate: replace today's row if it already exists
    today = traffic["date"]
    rows = [r for r in rows if r.get("date") != today]
    rows.append(traffic)

    # Roll if too long
    rows = _roll_old_rows(rows)

    new_content = json.dumps(rows, indent=2, ensure_ascii=False)
    ok = _write_file_to_branch(
        username, repo, _TRAFFIC_HISTORY_PATH, _DATA_BRANCH,
        new_content, sha,
        f"📊 traffic data {today}",
        token,
    )
    if ok:
        print(f"  Traffic row for {today} written to {_DATA_BRANCH} branch")
    return ok


def _compute_rolling_totals(traffic: dict) -> dict:
    """
    Build a summary suitable for the analytics block.
    We have: views_14d, unique_visitors_14d from the API.
    Approximate 7d = half of 14d (API doesn't give 7d directly).
    """
    v14  = traffic.get("views_14d", 0)
    uv14 = traffic.get("unique_visitors_14d", 0)
    # Rough 7d approximation (GitHub only returns 14d window)
    v7   = round(v14 / 2)
    uv7  = round(uv14 / 2)
    return {
        "views_7d":             v7,
        "unique_visitors_7d":   uv7,
        "views_14d":            v14,
        "unique_visitors_14d":  uv14,
        "clones_14d":           traffic.get("clones_14d", 0),
        "top_referrers":        traffic.get("top_referrers", []),
        "top_paths":            traffic.get("top_paths", []),
        "updated":              traffic.get("date", ""),
    }


_ANALYTICS_START = "<!-- ANALYTICS:START -->"
_ANALYTICS_END   = "<!-- ANALYTICS:END -->"


def build_analytics_block(summary: dict) -> str:
    """
    Generate the collapsed analytics <details> block from the traffic summary.
    Uses shields.io badges — no new design language, same style as existing badges.
    Degrades gracefully: missing data shows last-known or is hidden.
    """
    if not summary:
        return ""

    v7   = summary.get("views_7d", 0)
    uv7  = summary.get("unique_visitors_7d", 0)
    v14  = summary.get("views_14d", 0)
    uv14 = summary.get("unique_visitors_14d", 0)
    c14  = summary.get("clones_14d", 0)
    updated = summary.get("updated", "")
    refs    = summary.get("top_referrers", [])
    paths   = summary.get("top_paths", [])

    def badge(label: str, value: str, color: str = "0d1117") -> str:
        enc_label = urllib.parse.quote(label, safe="")
        enc_value = urllib.parse.quote(str(value), safe="")
        return (
            f"![{label}](https://img.shields.io/badge/{enc_label}-{enc_value}"
            f"-{color}?style=flat-square&labelColor=0d1117)"
        )

    badges = (
        f"{badge('Views · 7d', v7, '1a1a2e')} "
        f"{badge('Views · 14d', v14, '1a1a2e')} "
        f"{badge('Unique · 14d', uv14, '6e3aff')} "
        f"{badge('Clones · 14d', c14, '0d1117')}"
    )

    # Top referrers table
    ref_rows = ""
    if refs:
        ref_rows = "\n| Referrer | Views | Unique |\n|---|---|---|\n"
        for r in refs[:5]:
            ref_rows += f"| `{r.get('ref','?')}` | {r.get('count',0)} | {r.get('uniques',0)} |\n"

    # Top paths table
    path_rows = ""
    if paths:
        path_rows = "\n| Path | Views | Unique |\n|---|---|---|\n"
        for p in paths[:5]:
            path_rows += f"| `{p.get('path','?')}` | {p.get('count',0)} | {p.get('uniques',0)} |\n"

    updated_line = f"\n<sub><i>Data from GitHub Traffic API · Last updated: {updated}</i></sub>" if updated else ""

    return f"""<details>
<summary>📈 Analytics</summary>

<br>

{badges}
{ref_rows}{path_rows}{updated_line}

</details>"""


def update_analytics(
    readme_path: str,
    summary: dict,
    dry_run: bool = False,
) -> bool:
    """
    Replace the <!-- ANALYTICS:START/END --> block in README.
    Returns True if anything changed.
    """
    if not summary:
        return False
    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as exc:
        print(f"Warning: could not read README for analytics: {exc}", file=sys.stderr)
        return False

    start_idx = content.find(_ANALYTICS_START)
    end_idx   = content.find(_ANALYTICS_END)
    if start_idx == -1 or end_idx == -1:
        print("Analytics markers not found in README — skipping analytics update")
        return False

    block = build_analytics_block(summary)
    new_content = (
        content[:start_idx + len(_ANALYTICS_START)]
        + "\n"
        + block
        + "\n"
        + content[end_idx:]
    )

    if new_content == content:
        return False

    if dry_run:
        print("=== Analytics block (dry run) ===")
        print(block)
        return True

    tmp = readme_path + ".analytics.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp, readme_path)
        return True
    except IOError as exc:
        print(f"Warning: could not write analytics block: {exc}", file=sys.stderr)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


# ── Stage 4: Lines pool ────────────────────────────────────────────────────────


_LINES_FILE = os.path.join(
    os.path.dirname(__file__) if "__file__" in dir() else ".", "lines.json"
)


def _load_lines() -> dict:
    """Load lines.json; return empty dict on failure."""
    try:
        with open(_LINES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def pick_line(state: str, now_ist: datetime, theme_name: str = "") -> str:
    """
    Return a deterministic rotating line for the footer.
    Selection: hash(date, state) mod len(pool).
    Never repeats on consecutive days (the hash shifts daily).
    Falls back gracefully if lines.json is missing.
    """
    data = _load_lines()

    # Map state/theme_name → group key
    if theme_name == "special":
        group = "mystery"
    elif theme_name in ("new_year", "holi", "diwali", "halloween", "christmas",
                        "independence_day", "republic_day", "valentine", "pi_day",
                        "star_wars", "teachers_day", "gandhi", "makar_sankranti",
                        "eid", "shivratri", "raksha_bandhan", "janmashtami",
                        "ganesh_chaturthi", "navratri", "dussehra", "anniversary"):
        group = "festival"
    elif theme_name == "sunday":
        group = "sunday"
    elif state == "broken":
        group = "broken"
    elif state == "offline":
        group = "offline"
    else:
        # Check if it's "night" (after 21:00 or before 06:00 IST)
        h = now_ist.hour
        group = "night" if (h >= 21 or h < 6) else "active"

    pool = data.get(group, data.get("active", []))
    if not pool:
        return ""

    # Deterministic: hash of YYYY-MM-DD + state
    key = (now_ist.strftime("%Y-%m-%d") + group).encode()
    idx = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(pool)
    return pool[idx]


# ── Stage 4: Project status pings ─────────────────────────────────────────────

_PING_TIMEOUT = 10
_PING_RETRIES = 2
# Consecutive failures needed before marking a project as DOWN
_PING_FAIL_THRESHOLD = 2

_PROJECT_URLS = {
    "phantom_mail":   "https://mail.unknowns.app",
    "phantom_id":     "https://phantom-id.onrender.com",
    "phantom_vault":  "https://unk-extention.unknowns.app",
    "portfolio":      "https://ayushman.live",
}

# State file for project status (consecutive failure tracking)
_STATUS_FILE = os.environ.get("STATUS_STATE_PATH", ".project_status.json")


def _load_project_status() -> dict:
    try:
        with open(_STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def _save_project_status(data: dict) -> None:
    try:
        with open(_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as exc:
        print(f"Warning: could not save project status: {exc}", file=sys.stderr)


def ping_url(url: str) -> tuple[str, float]:
    """
    Ping a URL. Returns (status, elapsed_seconds).
    status: 'up', 'slow' (Render cold-start: 5-30s), 'down'
    """
    for attempt in range(_PING_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT}, method="GET")
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=_PING_TIMEOUT) as resp:
                elapsed = time.time() - t0
                _ = resp.read(256)   # consume a few bytes
                if elapsed >= 5:
                    return "slow", elapsed
                return "up", elapsed
        except Exception:
            if attempt < _PING_RETRIES - 1:
                time.sleep(2)
    return "down", -1.0


def get_project_statuses(dry_run: bool = False) -> dict[str, str]:
    """
    Ping all project URLs. Returns {key: 'up'|'slow'|'down'}.
    Requires 2 consecutive failures before flipping to 'down'.
    On dry-run: skip pings, return last-known state.
    """
    prev = _load_project_status()
    result = {}

    for key, url in _PROJECT_URLS.items():
        prev_info = prev.get(key, {})
        if dry_run:
            result[key] = prev_info.get("status", "up")
            continue
        status, elapsed = ping_url(url)
        fail_count = prev_info.get("fail_count", 0)
        if status in ("up", "slow"):
            fail_count = 0
        else:
            fail_count += 1
        # Only show 'down' after threshold consecutive failures
        shown = status if status != "down" else (
            "down" if fail_count >= _PING_FAIL_THRESHOLD else prev_info.get("status", "up")
        )
        prev[key] = {"status": shown, "fail_count": fail_count, "elapsed": round(elapsed, 2)}
        result[key] = shown
        print(f"  ping {key}: {status} ({elapsed:.1f}s) → shown={shown}")

    if not dry_run:
        _save_project_status(prev)
    return result


def _status_badge(label: str, status: str) -> str:
    """Return a shields.io badge URL for a project status."""
    colors = {"up": "00c851", "slow": "ff9500", "down": "f44336"}
    icons  = {"up": "✅", "slow": "⚡", "down": "❌"}
    color = colors.get(status, "546e7a")
    icon  = icons.get(status, "⚪")
    encoded_label = urllib.parse.quote(label, safe="")
    encoded_msg   = urllib.parse.quote(f"{icon} {status.upper()}", safe="")
    return (
        f"https://img.shields.io/badge/{encoded_label}-{encoded_msg}-{color}"
        f"?style=flat-square&labelColor=0d1117"
    )


_PROJECT_LABELS = {
    "portfolio": "Portfolio",
    "phantom_mail": "Mail",
    "phantom_id": "ID",
    "phantom_vault": "Vault",
}

_REPO_LABELS = {
    "Phanton-terminal": "Terminal",
    "Phantom-mail": "Mail",
    "llm-prompt-engineering": "Research",
}


def build_live_blocks(
    project_statuses: dict | None = None,
    repo_meta: dict | None = None,
    activity: list | None = None,
) -> str:
    """DEPRECATED internal use — now returns empty string.
    Status/repo/activity are injected into PROJECT-STATUS and RECENT-ACTIVITY markers instead."""
    return ""


def build_project_status_block(
    project_statuses: dict | None = None,
    repo_meta: dict | None = None,
) -> str:
    """DEPRECATED — live status and versions now live inside each project details block."""
    return ""


def build_recent_activity_block(activity: list | None) -> str:
    """Build a markdown list for RECENT-ACTIVITY marker (GitHub public events only).

    Each entry: `repo` — detail (when).
    Returns empty string if no activity so the section stays clean.
    """
    if not activity:
        return ""

    lines = []
    for ev in activity[:5]:
        repo = ev.get("repo", "")
        detail = ev.get("detail", "")
        when = ev.get("when", "")
        when_str = f" ({when})" if when else ""
        lines.append(f"- `{repo}` — {detail}{when_str}")
    return "\n".join(lines)


# Mapping: marker key → (service_key or None, repo_name or None)
_PER_PROJECT_MAP = {
    "phantom_mail":          ("phantom_mail",  "Phantom-mail"),
    "phantom_vault":         ("phantom_vault", None),
    "phantom_id":            ("phantom_id",    None),
    "Phanton-terminal":      (None,            "Phanton-terminal"),
    "llm-prompt-engineering":(None,            "llm-prompt-engineering"),
}

_LIVE_NOTE = (
    '<sup>&emsp;(🔴 Live · <a href="https://github.com/Unknown-2829/Unknown-2829/actions">'
    'auto-updated every ~6h</a>)</sup>'
)


def _build_per_project_block(
    key: str,
    project_statuses: dict,
    repo_meta: dict,
) -> str:
    """Build the badge HTML for a single LIVE-PROJECT marker.
    Format: badge(s) then some gap then in brackets on same line: (🔴 Live · auto-updated every ~6h)
    """
    svc_key, repo_key = _PER_PROJECT_MAP.get(key, (None, None))
    parts = []

    if svc_key and svc_key in project_statuses:
        status = project_statuses[svc_key]
        parts.append(f'<img align="absmiddle" src="{_status_badge("Service", status)}" alt="Service: {status}" />')

    if repo_key and repo_key in repo_meta:
        meta = repo_meta[repo_key]
        if meta:
            label = _REPO_LABELS.get(repo_key, repo_key)
            rel = str(meta.get("release") or "").strip()
            commits = meta.get("commits")
            msg = " · ".join(x for x in (rel, f"{commits} commits" if commits else "") if x)
            if msg:
                url = (
                    f"https://img.shields.io/badge/{urllib.parse.quote(label, safe='')}-"
                    f"{urllib.parse.quote(msg, safe='')}-6e3aff"
                    f"?style=flat-square&labelColor=0d1117"
                )
                parts.append(f'<img align="absmiddle" src="{url}" alt="{label}: {msg}" />')

    if not parts:
        return ""
    note = '(🔴 Live · <a href="https://github.com/Unknown-2829/Unknown-2829/actions">auto-updated every ~6h</a>)'
    return f'<p>\n  {" &nbsp; ".join(parts)} &nbsp; {note}\n</p>'


def inject_per_project_live(
    content: str,
    project_statuses: dict,
    repo_meta: dict,
) -> str:
    """Inject per-project live badge blocks into all LIVE-PROJECT:{key}:START/END markers."""
    for key in _PER_PROJECT_MAP:
        start = f"<!-- LIVE-PROJECT:{key}:START -->"
        end   = f"<!-- LIVE-PROJECT:{key}:END -->"
        pat   = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        if not pat.search(content):
            continue
        block = _build_per_project_block(key, project_statuses, repo_meta)
        replacement = f"{start}\n{block}\n{end}" if block else f"{start}\n{end}"
        content = pat.sub(replacement, content)
    return content





# ── Stage 4: Repo meta (latest release + commit count) ────────────────────────

_REPO_META_FILE = os.environ.get("REPO_META_PATH", ".repo_meta.json")


def _load_repo_meta() -> dict:
    try:
        with open(_REPO_META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


def _save_repo_meta(data: dict) -> None:
    try:
        with open(_REPO_META_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as exc:
        print(f"Warning: could not save repo meta: {exc}", file=sys.stderr)


def fetch_repo_meta(owner: str, repo: str, token: str | None = None) -> dict:
    """
    Fetch latest release tag + commit count for a repo.
    Returns {'release': 'v3.6.1', 'commits': 68, 'pushed_at': '...'}.
    Returns {} on failure (caller uses last-known cache).
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    result: dict = {}
    try:
        # Latest release
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            result["release"] = data.get("tag_name", "")
            result["pushed_at"] = data.get("published_at", "")
    except Exception as exc:
        print(f"  fetch_repo_meta release {repo}: {exc}", file=sys.stderr)

    try:
        # Commit count: request page 1 with per_page=100 to count.
        # GitHub includes a Link rel="last" header for paginated results;
        # the last page number equals the total commit count (with per_page=1).
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=1",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            link = resp.headers.get("Link", "")
            import re as _re
            m = _re.search(r'page=(\d+)>; rel="last"', link)
            if m:
                # Paginated: last page number = total commits (per_page=1)
                result["commits"] = int(m.group(1))
            else:
                # Single page: count items in the response body
                items = json.loads(resp.read().decode())
                result["commits"] = len(items) if isinstance(items, list) else 1
    except Exception as exc:
        print(f"  fetch_repo_meta commits {repo}: {exc}", file=sys.stderr)


    return result


def get_all_repo_meta(token: str | None = None, dry_run: bool = False) -> dict:
    """
    Returns cached + optionally refreshed meta for tracked repos.
    Cache key: repo name. Only re-fetches if pushed_at changed or cache empty.
    """
    tracked = {
        "Phanton-terminal": "Unknown-2829",
        "Phantom-mail":     "Unknown-2829",
        "llm-prompt-engineering": "Unknown-2829",
    }
    cache = _load_repo_meta()

    if dry_run:
        return cache

    for repo, owner in tracked.items():
        fresh = fetch_repo_meta(owner, repo, token)
        if fresh:
            cache[repo] = fresh
            print(f"  repo meta {repo}: release={fresh.get('release')} commits={fresh.get('commits')}")

    _save_repo_meta(cache)
    return cache


# ── Stage 4: Recent activity ───────────────────────────────────────────────────

def fetch_recent_activity(username: str, token: str | None = None, n: int = 5) -> list[dict]:
    """
    Returns last n non-bot public events from owned repos.
    Each item: {'type': str, 'repo': str, 'when': str (relative), 'detail': str}
    Returns [] on failure.
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        req = urllib.request.Request(
            f"https://api.github.com/users/{username}/events/public?per_page=50",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            events = json.loads(resp.read().decode())
    except Exception as exc:
        print(f"  fetch_recent_activity: {exc}", file=sys.stderr)
        return []

    now = datetime.now(timezone.utc)
    results = []
    for ev in events:
        if len(results) >= n:
            break
        actor = ev.get("actor", {}).get("login", "")
        if actor.endswith("[bot]"):
            continue
        # Only own repos
        repo_full = ev.get("repo", {}).get("name", "")
        if not repo_full.startswith(f"{username}/"):
            continue
        repo = repo_full.split("/", 1)[1]
        etype = ev.get("type", "")
        payload = ev.get("payload", {})

        detail = ""
        if etype == "PushEvent":
            commits = payload.get("commits", [])
            msg = commits[-1].get("message", "").split("\n")[0][:50] if commits else ""
            detail = f"pushed: {msg}" if msg else "pushed"
        elif etype == "CreateEvent":
            detail = f"created {payload.get('ref_type', '')} {payload.get('ref', '')}"
        elif etype == "ReleaseEvent":
            detail = f"released {payload.get('release', {}).get('tag_name', '')}"
        elif etype == "IssuesEvent":
            detail = f"{payload.get('action', '')} issue #{payload.get('issue', {}).get('number', '')}"
        elif etype == "PullRequestEvent":
            detail = f"{payload.get('action', '')} PR #{payload.get('pull_request', {}).get('number', '')}"
        else:
            detail = etype.replace("Event", "").lower()

        created = ev.get("created_at", "")
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            delta = now - dt
            days = delta.days
            hours = delta.seconds // 3600
            if days == 0:
                when = f"{hours}h ago" if hours > 0 else "just now"
            elif days == 1:
                when = "1d ago"
            else:
                when = f"{days}d ago"
        except Exception:
            when = ""

        results.append({"type": etype, "repo": repo, "when": when, "detail": detail})

    return results


# ── Stage 4: Failure tracking + issue ─────────────────────────────────────────

_RUN_STATE_FILE = os.environ.get("RUN_STATE_PATH", ".run_state.json")


def _load_run_state() -> dict:
    try:
        with open(_RUN_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {"consecutive_failures": 0, "failure_issue_number": None}


def _save_run_state(data: dict) -> None:
    try:
        with open(_RUN_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except IOError as exc:
        print(f"Warning: could not save run state: {exc}", file=sys.stderr)


def record_run_success(run_state: dict) -> dict:
    run_state["consecutive_failures"] = 0
    return run_state


def record_run_failure(run_state: dict) -> dict:
    run_state["consecutive_failures"] = run_state.get("consecutive_failures", 0) + 1
    return run_state


def open_or_update_failure_issue(run_state: dict, token: str, username: str, reason: str) -> None:
    """Open or update a 'Profile updater failing' issue after 3 consecutive failures.

    If an existing issue number is stored, PATCH its body (no comment spam).
    If the stored number is stale (404), clears it and opens a fresh issue.
    Does nothing if fewer than 3 consecutive failures or no token.
    """
    failures = run_state.get("consecutive_failures", 0)
    if failures < 3 or not token:
        return
    existing = run_state.get("failure_issue_number")
    title = "⚠️ Profile updater failing"
    body = (
        f"The profile updater has failed **{failures} consecutive times**.\n\n"
        f"Last failure reason: `{reason}`\n\n"
        f"Please check the [Actions tab](https://github.com/{username}/{username}/actions) "
        f"for details.\n\n"
        f"_This issue is auto-managed by the profile updater. "
        f"It will be closed when the next run succeeds._"
    )
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "User-Agent": _USER_AGENT,
    }
    try:
        if existing:
            # PATCH issue body — no comment spam
            payload = json.dumps({"body": body}).encode()
            req = urllib.request.Request(
                f"https://api.github.com/repos/{username}/{username}/issues/{existing}",
                data=payload, headers=headers, method="PATCH",
            )
            try:
                with urllib.request.urlopen(req, timeout=10):
                    print(f"Updated failure issue #{existing}")
                    return
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # Stale issue number — clear it and fall through to create
                    print(
                        f"Warning: failure issue #{existing} not found (stale) — opening new",
                        file=sys.stderr,
                    )
                    run_state["failure_issue_number"] = None
                    existing = None
                else:
                    raise

        if not existing:
            payload = json.dumps({"title": title, "body": body, "labels": ["bug"]}).encode()
            req = urllib.request.Request(
                f"https://api.github.com/repos/{username}/{username}/issues",
                data=payload, headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                issue = json.loads(resp.read().decode())
                run_state["failure_issue_number"] = issue.get("number")
                print(f"Opened failure issue #{run_state['failure_issue_number']}")
    except Exception as exc:
        print(f"Warning: could not manage failure issue: {exc}", file=sys.stderr)



def close_failure_issue(run_state: dict, token: str, username: str) -> None:
    """Close the failure issue when a run succeeds."""
    existing = run_state.get("failure_issue_number")
    if not existing or not token:
        return
    try:
        payload = json.dumps({"state": "closed"}).encode()
        headers = {
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
            "User-Agent": _USER_AGENT,
        }
        req = urllib.request.Request(
            f"https://api.github.com/repos/{username}/{username}/issues/{existing}",
            data=payload, headers=headers, method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=10):
            run_state["failure_issue_number"] = None
            print(f"Closed failure issue #{existing}")
    except Exception as exc:
        print(f"Warning: could not close failure issue: {exc}", file=sys.stderr)


# ── Stage 4: GitHub Actions job summary ───────────────────────────────────────

def write_job_summary(items: list[tuple[str, str]], now_ist: datetime) -> None:
    """
    Write a Markdown job summary to GITHUB_STEP_SUMMARY.
    items: list of (label, value_or_status_string)
    """
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_file:
        return
    ts = now_ist.strftime("%d %b %Y, %H:%M IST")
    lines = [f"## 📊 Profile Updater — {ts}\n\n", "| Item | Result |\n", "|---|---|\n"]
    for label, value in items:
        lines.append(f"| {label} | {value} |\n")
    try:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.writelines(lines)
    except IOError as exc:
        print(f"Warning: could not write job summary: {exc}", file=sys.stderr)




def generate_stats_section(
    username: str,
    streak: int,
    status: str = "active",
    state: dict | None = None,
    now_ist: datetime | None = None,
    project_statuses: dict | None = None,
    repo_meta: dict | None = None,
    activity: list | None = None,
    theme_name: str | None = None,
    live: dict | None = None,
) -> str:
    """Generate the dynamic stats section markdown."""
    if state is None:
        state = {}
    if now_ist is None:
        now_ist = _now_ist()
    if live:
        project_statuses = live.get("statuses", project_statuses)
        repo_meta = live.get("meta", repo_meta)
        activity = live.get("activity", activity)

    # ── Determine badge / sub-text based on status ──────────────────────────
    if theme_name and theme_name in THEMES:
        picked_name = theme_name
        theme = THEMES[theme_name]
        event_note = f"Forced Theme: {theme['label']}"
        badge_color = theme["badge_color"]
        badge_label = urllib.parse.quote(f"{theme['label']}", safe="_-")
        status_note = f"🎨 <i>{theme['label']} | Powered by GitHub Actions</i>"
    elif status == "broken":
        last = state.get("last_positive_streak")
        badge_color = "ff6d00"
        badge_label = urllib.parse.quote("💔 Streak Dropped", safe="")
        if last:
            status_note = (
                f"⚡ <i>{last}-day streak was broken — "
                f"get back in the game!</i>"
            )
        else:
            status_note = "⚡ <i>Streak dropped — get back in the game!</i>"
        # Use the theme from the last known positive streak for visual continuity
        theme = get_theme_for_streak(last if last else 1)
        picked_name = get_theme_name_for_streak(last if last else 1)

    elif status == "offline":
        day_index = now_ist.timetuple().tm_yday
        emoji, label = OFFLINE_MESSAGES[day_index % len(OFFLINE_MESSAGES)]
        badge_color = "546e7a"
        badge_label = urllib.parse.quote(f"{emoji} {label}", safe="")
        status_note = _offline_note(now_ist)
        # Use a neutral dark theme for offline state
        theme = THEMES["black"]
        picked_name = "black"

    else:  # active — use pick_theme for full festival/event/Sunday/special support
        picked_name, theme, event_note = pick_theme(now_ist, streak, state, username)
        badge_color = theme["badge_color"]
        tier_display = theme["tier"].replace(" ", "%20")
        badge_label = urllib.parse.quote(f"{theme['label']}", safe="_-")
        if event_note:
            # Festival / Sunday / special: show the event label as the note
            status_note = f"🎨 <i>{event_note} | Powered by GitHub Actions</i>"
        else:
            # Normal streak tier
            status_note = (
                "🎨 <i>Stats theme updates dynamically based on current streak"
                " | Powered by GitHub Actions</i>"
            )

    # ── Build streak-stats URL ───────────────────────────────────────────────
    streak_url = (
        f"https://streak-stats.demolab.com?user={username}"
        f"&hide_border=true"
        f"&background={theme['streak_bg']}"
        f"&ring={theme['ring']}"
        f"&fire={theme['fire']}"
        f"&currStreakNum={theme['curr_streak_num']}"
        f"&currStreakLabel={theme['curr_streak_label']}"
        f"&sideNums={theme['side_nums']}"
        f"&sideLabels={theme['side_labels']}"
        f"&dates={theme['dates']}"
        f"&stroke={theme['stroke']}"
        f"&date_format=j%20M%20Y"
    )

    # ── Capsule render dividers ──────────────────────────────────────────────
    capsule_divider_url = (
        f"https://capsule-render.vercel.app/api?type={theme['capsule_type']}"
        f"&color=0:{theme['gradient_start']},50:{theme['gradient_mid']},100:{theme['gradient_end']}"
        f"&height={theme['capsule_height']}"
        f"&section=header"
        f"&animation={theme['capsule_animation']}"
    )

    # ── Activity graph URL (for caching) ─────────────────────────────────────
    graph_url_live = (
        f"https://github-readme-activity-graph.vercel.app/graph?username={username}"
        f"&bg_color={theme['streak_bg']}"
        f"&color={theme['side_labels']}"
        f"&line={theme['ring']}"
        f"&point={theme['fire']}"
        f"&area_color={theme['ring']}"
        f"&area={theme['graph_area']}"
        f"&hide_border=true"
    )
    graph_cached = os.path.join(ASSETS_DIR, "activity-graph.svg")
    if os.path.exists(graph_cached):
        graph_img_url = f"{RAW_BASE}/assets/activity-graph.svg"
    else:
        # No cached file yet and fetch may have failed — fall back to live URL
        graph_img_url = graph_url_live

    # ── Streak card URL (for caching) ────────────────────────────────────────
    streak_cached = os.path.join(ASSETS_DIR, "streak-card.svg")
    if os.path.exists(streak_cached):
        streak_img_url = f"{RAW_BASE}/assets/streak-card.svg"
    else:
        streak_img_url = streak_url

    # ── Assemble the section ─────────────────────────────────────────────────
    if sys.platform == "win32":
        last_updated = now_ist.strftime("%#d %b %Y, %H:%M IST")
    else:
        last_updated = now_ist.strftime("%-d %b %Y, %H:%M IST").lstrip("0")

    # Cinematic footer line from lines.json
    theme_name_for_line = locals().get("picked_name", "")
    footer_line = pick_line(status, now_ist, theme_name_for_line)

    live_html = build_live_blocks(project_statuses, repo_meta, activity)
    live_block_str = f"\n{live_html}\n" if live_html else ""

    tagline_block = ""
    if footer_line:
        clean_quote = urllib.parse.quote(f"“ {footer_line} ”", safe="")
        tagline_block = f"""
<p align="center">
  <img src="https://img.shields.io/badge/%23%20TAGLINE-{clean_quote}-ffffff?style=for-the-badge&labelColor=161b22" alt="Tagline: {footer_line}" />
</p>
"""

    section = f"""
<p align="center">
  <img src="https://img.shields.io/badge/%E2%9A%A1%20CURRENT%20STATUS-{badge_label}-{badge_color}?style=for-the-badge&labelColor=161b22" alt="Current Status" />
</p>
{tagline_block}
<!-- Themed gradient divider with tier-specific effect -->
<p align="center">
  <img src="{capsule_divider_url}" width="70%" alt="" />
</p>

<!-- Streak Stats - Dynamically Themed -->
<p align="center">
  <img width="70%" src="{streak_img_url}" alt="GitHub streak stats" />
</p>

<!-- Activity Graph - Themed -->
<p align="center">
  <img width="95%" src="{graph_img_url}" alt="GitHub activity graph" />
</p>
{live_block_str}
<!-- Themed gradient divider with tier-specific effect -->
<p align="center">
  <img src="{capsule_divider_url}" width="70%" alt="" />
</p>

<p align="center">
  <sub>{status_note}</sub>
</p>

<p align="center">
  <sub><code>Last refresh: {last_updated}</code></sub>
</p>"""
    return section.strip()


_STATUS_LOOK = {
    "active":  ("ACTIVE", "00ff00", "🟢 OPEN TO OPPORTUNITIES"),
    "broken":  ("BUSY", "ff6d00", "🟠 BUSY · OPEN TO OPPORTUNITIES"),
    "offline": ("AWAY", "546e7a", "🌑 QUIET MODE · OPEN TO OPPORTUNITIES"),
}


def _replace_marked(content: str, name: str, inner: str) -> str:
    pat = re.compile(
        r"(<!-- " + re.escape(name) + r":START -->).*?(<!-- " + re.escape(name) + r":END -->)",
        re.DOTALL)
    return pat.sub(lambda m: f"{m.group(1)}{inner}{m.group(2)}", content)


def apply_status_badges(content: str, status: str) -> str:
    """One computed status drives both the top badge and the Contact badge."""
    top, color, contact = _STATUS_LOOK.get(status, _STATUS_LOOK["active"])
    def badge(text, alt):
        return (f'<img src="https://img.shields.io/badge/Status-'
                f'{urllib.parse.quote(text, safe="")}-{color}?style=for-the-badge" alt="{alt}" />')
    content = _replace_marked(content, "STATUS-TOP", badge(top, f"Status: {top}"))
    content = _replace_marked(content, "STATUS-CONTACT", badge(contact, f"Status: {contact}"))
    return content


def generate_commit_message(
    status: str,
    streak: int | None,
    prev_streak: int | None = None,
    theme_name: str = "",
    theme: dict | None = None,
    event_note: str | None = None,
    is_special: bool = False,
    project_statuses: dict | None = None,
    repo_meta: dict | None = None,
    quote_line: str = "",
    now_ist: datetime | None = None,
) -> str:
    """Generate a dynamic, detailed git commit message with subject & multi-line description."""
    theme = theme or {}
    label = theme.get("label", theme_name)
    streak_val = streak if streak is not None else 0
    streak_changed = (prev_streak is not None and streak_val != prev_streak and streak_val > 0)

    # ── Streak milestone detection ────────────────────────────────────────────
    milestones = {7: "🎯 1-week", 14: "🔥 2-week", 30: "💎 1-month",
                  50: "🚀 50-day", 100: "👑 100-day", 365: "⚡ 1-year"}
    milestone_str = milestones.get(streak_val, "")

    # ── Subject line ──────────────────────────────────────────────────────────
    if status == "broken":
        subject = f"💔 profile: streak dropped → busy mode | {label} theme"
    elif status == "offline":
        subject = f"🌙 profile: quiet mode active | offline theme"
    elif is_special:
        streak_str = f" · {streak_val}d" if streak_val > 0 else ""
        subject = f"✨ profile: special day theme active{streak_str} | {label}"
    elif event_note:
        streak_str = f" · {streak_val}d" if streak_val > 0 else ""
        subject = f"🎨 profile: {label} theme applied{streak_str}"
    elif milestone_str:
        subject = f"⚡ profile: {milestone_str} streak milestone! | {label} theme"
    elif streak_changed and prev_streak is not None:
        delta = streak_val - prev_streak
        arrow = f"+{delta}" if delta > 0 else str(delta)
        subject = f"⚡ profile: streak {prev_streak}d → {streak_val}d ({arrow}) | {label}"
    elif streak_val > 0:
        subject = f"⚡ profile: {streak_val}d streak synced | {label} theme"
    else:
        subject = "⚡ profile: data, health & status refreshed in README"

    # ── Detailed operational breakdown ────────────────────────────────────────
    desc = [subject, ""]

    # Theme
    desc.append(f"🎨 Theme      : {label} ({theme_name})")

    # Event / special day
    if event_note:
        desc.append(f"📅 Event      : {event_note}")
    if is_special:
        desc.append(f"🌟 Special day: theme override applied")

    # Streak
    if milestone_str:
        desc.append(f"🔥 Streak     : {streak_val} days — {milestone_str} milestone reached!")
    elif streak_changed and prev_streak is not None:
        delta = streak_val - prev_streak
        arrow = f"+{delta}" if delta > 0 else str(delta)
        desc.append(f"🔥 Streak     : {streak_val} days (was {prev_streak}d, Δ{arrow})")
    else:
        desc.append(f"🔥 Streak     : {streak_val} days (status: {status})")

    # Project health — flag anything not 'up'
    if project_statuses:
        health_parts = []
        issues = []
        for k, v in project_statuses.items():
            lbl = _PROJECT_LABELS.get(k, k)
            icon = {"up": "✅", "slow": "⚡", "down": "❌"}.get(v, "❓")
            health_parts.append(f"{icon} {lbl}")
            if v != "up":
                issues.append(f"{lbl}:{v}")
        health_str = "  ".join(health_parts)
        if issues:
            desc.append(f"🩺 Services   : {health_str}  ⚠️ degraded: {', '.join(issues)}")
        else:
            desc.append(f"🩺 Services   : {health_str}  (all operational)")

    # Repo versions
    if repo_meta:
        r_parts = []
        for repo, meta in repo_meta.items():
            if not meta:
                continue
            r_label = _REPO_LABELS.get(repo, repo)
            rel = meta.get("release", "")
            commits = meta.get("commits")
            detail = " · ".join(x for x in (rel, f"{commits}c" if commits else "") if x)
            if detail:
                r_parts.append(f"{r_label}({detail})")
        if r_parts:
            desc.append(f"📦 Repos      : {' · '.join(r_parts)}")

    # Tagline
    if quote_line:
        desc.append(f'💬 Tagline    : "{quote_line}"')

    # Timestamp
    if now_ist:
        time_str = now_ist.strftime("%d %b %Y, %H:%M IST")
        desc.append(f"🕐 Refreshed  : {time_str}")

    return "\n".join(desc)





def update_readme(
    readme_path: str,
    username: str,
    streak: int,
    status: str = "active",
    state: dict | None = None,
    now_ist: datetime | None = None,
    dry_run: bool = False,
    force: bool = False,
    project_statuses: dict | None = None,
    repo_meta: dict | None = None,
    activity: list | None = None,
    theme_name: str | None = None,
) -> bool:
    """
    Update the README.md file with the dynamic stats section and status badges.
    Looks for markers: <!-- DYNAMIC-STATS:START --> and <!-- DYNAMIC-STATS:END -->
    """
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_section = generate_stats_section(
        username,
        streak,
        status,
        state,
        now_ist,
        project_statuses=project_statuses,
        repo_meta=repo_meta,
        activity=activity,
        theme_name=theme_name,
    )

    start_marker = "<!-- DYNAMIC-STATS:START -->"
    end_marker = "<!-- DYNAMIC-STATS:END -->"

    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )

    if pattern.search(content):
        new_content = pattern.sub(
            f"{start_marker}\n{new_section}\n{end_marker}",
            content,
        )
    else:
        print("Error: Could not find DYNAMIC-STATS markers in README.md",
              file=sys.stderr)
        return False

    new_content = apply_status_badges(new_content, status)

    # ── Inject RECENT-ACTIVITY block ──────────────────────────────────────────
    ra_block = build_recent_activity_block(activity)
    ra_start = "<!-- RECENT-ACTIVITY:START -->"
    ra_end   = "<!-- RECENT-ACTIVITY:END -->"
    ra_pat   = re.compile(re.escape(ra_start) + r".*?" + re.escape(ra_end), re.DOTALL)
    if ra_pat.search(new_content):
        new_content = ra_pat.sub(
            f"{ra_start}\n{ra_block}\n{ra_end}" if ra_block else f"{ra_start}\n{ra_end}",
            new_content,
        )
    else:
        print("Info: RECENT-ACTIVITY markers not found — skipping", file=sys.stderr)

    # ── Inject per-project live badges ────────────────────────────────────────
    new_content = inject_per_project_live(new_content, project_statuses or {}, repo_meta or {})

    if new_content != content:
        if dry_run:
            print("── DRY RUN: generated README block ──────────────────")
            print(new_section)
            print("─────────────────────────────────────────────────────")
            print(f"[dry-run] Would update README — status: '{status}', "
                  f"theme: '{get_theme_name_for_streak(streak)}' "
                  f"(streak: {streak})")
        else:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"README updated — status: '{status}', "
                  f"theme: '{get_theme_name_for_streak(streak)}' "
                  f"(streak: {streak})")
        return True
    else:
        if force and not dry_run:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"README force-written (no content change) — streak: {streak}")
            return True
        print(f"No changes needed (streak: {streak}, "
              f"status: {status}, "
              f"theme: {get_theme_name_for_streak(streak)})")
        return False




# ── CLI Entry Point ────────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Phantom Engine — dynamic GitHub profile README updater.\n"
            "Fetches streak, picks a theme, caches SVGs, updates DYNAMIC-STATS block."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated blocks without writing any files.",
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD[THH:MM]",
        help="Simulate a specific IST date/time for theme preview.",
    )
    parser.add_argument(
        "--streak",
        type=int,
        metavar="N",
        help="Override streak value (skips network streak fetch).",
    )
    parser.add_argument(
        "--theme",
        metavar="THEME_NAME",
        help="Force a specific theme by name (e.g. diwali, blue, special). "
             "Use --list-themes to see all available names.",
    )
    parser.add_argument(
        "--list-themes",
        action="store_true",
        help="Print all available theme names and exit.",
    )
    parser.add_argument(
        "--skip-pings",
        action="store_true",
        help="Skip project status URL pings (faster local runs).",
    )
    parser.add_argument(
        "--skip-traffic",
        action="store_true",
        help="Skip GitHub Traffic API fetch.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Write README even if the generated block is identical to current content.",
    )
    return parser.parse_args(argv)



def main(argv=None):
    args = parse_args(argv)

    # ── --list-themes: print all theme names and exit ─────────────────────────
    if args.list_themes:
        print("Available themes:")
        for name, t in sorted(THEMES.items()):
            print(f"  {name:<22} — {t['label']}")
        return

    username = os.environ.get("GITHUB_USERNAME", "Unknown-2829")
    readme_path = os.environ.get("README_PATH", "README.md")

    # ── Validate --theme override early ──────────────────────────────────────
    if args.theme and args.theme not in THEMES:
        print(
            f"Error: unknown theme '{args.theme}'. "
            f"Run with --list-themes to see valid names.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── Resolve simulated date ───────────────────────────────────────────────
    if args.date:
        try:
            if "T" in args.date:
                sim_dt = datetime.fromisoformat(args.date)
                if sim_dt.tzinfo is None:
                    sim_dt = sim_dt.replace(tzinfo=IST)
            else:
                sim_dt = datetime.fromisoformat(args.date).replace(
                    hour=12, minute=0, tzinfo=IST
                )
            now_ist = sim_dt
            print("Date simulation active (value not logged)")

        except ValueError as exc:
            print(f"Error: invalid --date value: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        now_ist = _now_ist()

    # ── Resolve streak ───────────────────────────────────────────────────────
    # Priority: --streak > STREAK_OVERRIDE env > network fetch
    streak_override_env = os.environ.get("STREAK_OVERRIDE", "").strip()

    if args.streak is not None:
        streak = args.streak
        print(f"Using --streak override: {streak}")
    elif streak_override_env:
        try:
            streak = int(streak_override_env)
        except ValueError:
            print(
                f"Error: STREAK_OVERRIDE must be an integer, "
                f"got {streak_override_env!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Using STREAK_OVERRIDE: {streak}")
    else:
        streak = fetch_streak(username)
        if streak is None:
            print(
                "All streak sources failed — README and state left unchanged.",
                file=sys.stderr,
            )
            # ── Failure tracking (must happen before exit) ────────────────────
            run_state = _load_run_state()
            token = (
                os.environ.get("GH_STATS_TOKEN", "").strip()
                or os.environ.get("GITHUB_TOKEN", "").strip()
            )
            run_state = record_run_failure(run_state)
            if not args.dry_run:
                open_or_update_failure_issue(
                    run_state, token, username, "streak fetch failed"
                )
                _save_run_state(run_state)
            sys.exit(1)   # real failure — let the Action job go red
        print(f"Fetched streak for {username}: {streak}")


    # ── Load state, compute status ───────────────────────────────────────────
    state = load_streak_state()
    prev_streak = state.get("last_positive_streak")
    status = compute_streak_status(streak, state)


    # ── Theme selection ───────────────────────────────────────────────────────
    if args.theme:
        picked_name = args.theme
        picked_theme = THEMES[args.theme]
        picked_note = f"Theme forced via --theme {args.theme}"
        print(f"Forced theme: {picked_name} ({picked_theme['label']})")
    else:
        # pick_theme runs at every streak level — festivals/events/Sunday
        # apply even when streak is 0; tier fallback handles offline/broken
        picked_name, picked_theme, picked_note = pick_theme(now_ist, streak, state, username)
        print(f"Selected theme: {picked_name} ({picked_theme['label']})")
        if picked_note:
            print(f"Event note: {picked_note}")

    # ── Cache SVG assets (skip in dry-run or when overriding streak) ─────────
    if not args.dry_run and args.streak is None and not streak_override_env:
        theme = picked_theme

        graph_url = (
            f"https://github-readme-activity-graph.vercel.app/graph?username={username}"
            f"&bg_color={theme['streak_bg']}"
            f"&color={theme['side_labels']}"
            f"&line={theme['ring']}"
            f"&point={theme['fire']}"
            f"&area_color={theme['ring']}"
            f"&area={theme['graph_area']}"
            f"&hide_border=true"
        )
        streak_url = (
            f"https://streak-stats.demolab.com?user={username}"
            f"&hide_border=true"
            f"&background={theme['streak_bg']}"
            f"&ring={theme['ring']}"
            f"&fire={theme['fire']}"
            f"&currStreakNum={theme['curr_streak_num']}"
            f"&currStreakLabel={theme['curr_streak_label']}"
            f"&sideNums={theme['side_nums']}"
            f"&sideLabels={theme['side_labels']}"
            f"&dates={theme['dates']}"
            f"&stroke={theme['stroke']}"
            f"&date_format=j%20M%20Y"
        )
        os.makedirs(ASSETS_DIR, exist_ok=True)
        print("Caching activity graph…")
        cache_graph(graph_url, os.path.join(ASSETS_DIR, "activity-graph.svg"))
        print("Caching streak card…")
        cache_graph(streak_url, os.path.join(ASSETS_DIR, "streak-card.svg"))

    # ── Stage 4: Run state (failure tracking) ────────────────────────────────
    run_state = _load_run_state()
    token = (
        os.environ.get("GH_STATS_TOKEN", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )

    # ── Stage 4: Project status pings ────────────────────────────────────────
    if args.skip_pings:
        print("Skipping project status pings (--skip-pings)")
        project_statuses = {}
    else:
        print("Checking project statuses…")
        project_statuses = get_project_statuses(dry_run=args.dry_run)

    # ── Stage 4: Repo meta ───────────────────────────────────────────────────
    print("Fetching repo meta…")
    repo_meta = get_all_repo_meta(token=token, dry_run=args.dry_run)

    # ── Stage 4: Recent activity ─────────────────────────────────────────────
    print("Fetching recent activity…")
    if args.dry_run:
        activity = []
    else:
        activity = fetch_recent_activity(username, token, n=5)
    if activity:
        print("Recent activity:")
        for ev in activity:
            print(f"  [{ev['when']}] {ev['repo']}: {ev['detail']}")

    # ── Update state (skip in dry-run) ───────────────────────────────────────
    if not args.dry_run:
        state = update_streak_state(streak, state)
        save_streak_state(state)

    print(
        f"Streak status: {status} "
        f"(last_positive_streak={state.get('last_positive_streak')}, "
        f"streak_zero_since={state.get('streak_zero_since')})"
    )

    # ── Dec 1 reminder: check if next year's festival dates are present ──────
    if not args.dry_run:
        _check_missing_festival_years()

    updated = update_readme(
        readme_path, username, streak, status, state,
        now_ist=now_ist, dry_run=args.dry_run,
        force=args.force,
        project_statuses=project_statuses,
        repo_meta=repo_meta,
        activity=activity,
        theme_name=picked_name,
    )



    if updated:
        if args.dry_run:
            print("✅ Dry run complete — no files modified")
        else:
            print("✅ README.md updated successfully")
            # Stage 4: success — reset failure counter, close any open issue
            run_state = record_run_success(run_state)
            close_failure_issue(run_state, token, username)
    else:
        print("ℹ️  No update needed or markers not found")

    # ── Stage 4: Persist run state ───────────────────────────────────────────
    if not args.dry_run:
        _save_run_state(run_state)


    # ── Stage 4: Job summary ─────────────────────────────────────────────────
    summary_items = [
        ("Streak", f"{streak} days ({status})" if streak is not None else "fetch failed"),
        ("Theme", picked_name if streak and streak > 0 else status),
        ("Graph cache", "✅ fresh" if os.path.exists(os.path.join(ASSETS_DIR, "activity-graph.svg")) else "⚠️ missing"),
        ("Streak card cache", "✅ fresh" if os.path.exists(os.path.join(ASSETS_DIR, "streak-card.svg")) else "⚠️ missing"),
    ]
    for k, v in project_statuses.items():
        icon = {"up": "✅", "slow": "⚡", "down": "❌"}.get(v, "❓")
        summary_items.append((f"Project: {k.replace('_', ' ')}", f"{icon} {v}"))
    for repo, meta in repo_meta.items():
        if meta:
            rel = meta.get("release", "—")
            commits = meta.get("commits", "—")
            summary_items.append((f"Repo: {repo}", f"{rel} · {commits} commits"))

    # ── Stage 5: Traffic & Analytics ─────────────────────────────────────────
    traffic_token = (
        os.environ.get("TRAFFIC_TOKEN", "").strip()
        or os.environ.get("GH_STATS_TOKEN", "").strip()
    )


    if args.skip_traffic:
        print("Skipping traffic fetch (--skip-traffic)")
        traffic = None
    else:
        print("Fetching traffic data…")
        traffic = None if args.dry_run else fetch_traffic(username, traffic_token)


    if traffic:
        print(
            f"  Views today: {traffic['views_today']} "
            f"(unique: {traffic['unique_visitors_today']})"
        )
        # Save summary to main branch for analytics block
        summary = _compute_rolling_totals(traffic)
        if not args.dry_run:
            _save_traffic_summary(summary)
            # Push full row to data branch (silently skip if no token)
            append_traffic_to_data_branch(traffic, username, traffic_token)
        summary_items.append((
            "Traffic (14d)",
            f"{traffic['views_14d']} views · {traffic['unique_visitors_14d']} unique"
        ))
    else:
        # Use last-known summary if fetch failed / no token
        summary = _load_traffic_summary()
        if not traffic_token:
            print("  Traffic skipped — TRAFFIC_TOKEN not set")
        else:
            print("  Traffic fetch failed — using cached summary")

    # Update analytics block in README from summary (last-known or fresh)
    if summary:
        analytics_updated = update_analytics(readme_path, summary, dry_run=args.dry_run)
        if analytics_updated and not args.dry_run:
            print("✅ Analytics block updated in README")

    # Write dynamic commit message for CI runner
    if not args.dry_run:
        quote_line = pick_line(status, now_ist, picked_name)
        msg = generate_commit_message(
            status=status,
            streak=streak,
            prev_streak=prev_streak,
            theme_name=picked_name,
            theme=picked_theme,
            event_note=picked_note if "picked_note" in locals() else None,
            is_special=is_special_today(now_ist),
            project_statuses=project_statuses,
            repo_meta=repo_meta,
            quote_line=quote_line,
            now_ist=now_ist,
        )
        try:
            with open(".commit_msg", "w", encoding="utf-8") as f:
                f.write(msg)
        except IOError:
            pass



    write_job_summary(summary_items, now_ist)




if __name__ == "__main__":
    main()

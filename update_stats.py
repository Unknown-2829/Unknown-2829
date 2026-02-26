"""
Dynamic GitHub Stats Updater
Fetches GitHub streak data and updates README.md with conditional theming.

Streak Tiers:
  1-3   → Green theme  (fresh, growing)
  4-8   → Blue theme   (steady, consistent)
  9-30  → Red theme    (on fire, dominant)
  30+   → Black theme  (legendary, dark elite)

Streak Status:
  active  → streak > 0, use tier themes above
  broken  → streak just dropped to 0 (shows "💔 Streak Dropped" badge)
  offline → streak has been 0 for 2+ days (rotating secret/offline messages)

Each tier has unique visual styles and colors.
"""

import os
import re
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# Path to the file that persists streak state between runs
STATE_FILE = os.environ.get("STREAK_STATE_PATH", ".streak_state.json")

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
}


def get_theme_name_for_streak(streak: int) -> str:
    """Return the theme name based on current streak value."""
    if streak <= 3:
        return "green"
    elif streak <= 8:
        return "blue"
    elif streak <= 30:
        return "red"
    else:
        return "black"


def get_theme_for_streak(streak: int) -> dict:
    """Return the theme dictionary based on current streak value."""
    return THEMES[get_theme_name_for_streak(streak)]


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
            days_at_zero = (datetime.now(timezone.utc).date() - zero_date).days
            if days_at_zero >= 2:
                return "offline"
        except ValueError:
            pass

    return "broken"


def update_streak_state(streak: int, state: dict) -> dict:
    """Return an updated state dict based on the current streak value."""
    today = datetime.now(timezone.utc).date().isoformat()
    if streak > 0:
        state["last_positive_streak"] = streak
        state["streak_zero_since"] = None
    else:
        if state.get("streak_zero_since") is None:
            state["streak_zero_since"] = today
        # last_positive_streak is intentionally preserved for the "broken" message
    return state


def fetch_streak_from_svg(username: str) -> int:
    """
    Fetch the current streak by parsing the streak-stats.demolab.com SVG.
    This is the same service used to render the streak image in the README,
    so it provides the most accurate streak data (uses GitHub's contribution
    calendar via GraphQL, which includes all contribution types).
    """
    url = f"https://streak-stats.demolab.com?user={username}&hide_border=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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


def fetch_streak(username: str) -> int:
    """
    Fetch the current streak count for a GitHub user.
    Primary: parses the streak-stats.demolab.com SVG (accurate, uses
    GitHub's contribution calendar which includes all contribution types).
    Fallback: counts consecutive days from the GitHub Events API.
    """
    # Primary method: parse streak from streak-stats.demolab.com SVG
    try:
        streak = fetch_streak_from_svg(username)
        print(f"Streak from streak-stats.demolab.com: {streak}")
        return streak
    except Exception as e:
        print(f"Warning: Could not fetch streak from SVG: {e}",
              file=sys.stderr)

    # Fallback: GitHub Events API (less reliable — only public events)
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"

        url = f"https://api.github.com/users/{username}/events/public"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            events = json.loads(resp.read().decode())

        if not events:
            return 0

        today = datetime.now(timezone.utc).date()
        dates_with_activity = set()
        for event in events:
            if event.get("type") in ("PushEvent", "CreateEvent",
                                     "PullRequestEvent", "IssuesEvent",
                                     "CommitCommentEvent"):
                event_date = datetime.strptime(
                    event["created_at"], "%Y-%m-%dT%H:%M:%SZ"
                ).date()
                dates_with_activity.add(event_date)

        if not dates_with_activity:
            return 0

        streak = 0
        check_date = today
        while check_date in dates_with_activity:
            streak += 1
            check_date -= timedelta(days=1)

        if streak == 0:
            check_date = today - timedelta(days=1)
            while check_date in dates_with_activity:
                streak += 1
                check_date -= timedelta(days=1)

        print(f"Streak from Events API fallback: {streak}")
        return streak

    except Exception as e:
        print(f"Warning: Could not fetch streak data: {e}", file=sys.stderr)
        return 0


def generate_stats_section(username: str, streak: int,
                           status: str = "active",
                           state: dict | None = None) -> str:
    """Generate the dynamic stats section markdown."""
    if state is None:
        state = {}

    # ── Determine badge / sub-text based on status ──────────────────────────
    if status == "broken":
        last = state.get("last_positive_streak")
        badge_color = "ff6d00"
        badge_label = urllib.parse.quote("💔 Streak Dropped", safe="")
        if last:
            status_note = (
                f"⚡ *{last}-day streak was broken — "
                f"get back in the game!*"
            )
        else:
            status_note = "⚡ *Streak dropped — get back in the game!*"
        # Use the theme from the last known positive streak for visual continuity
        theme = get_theme_for_streak(last if last else 1)

    elif status == "offline":
        # Pick a message based on the current day-of-year for variety
        day_index = datetime.now(timezone.utc).timetuple().tm_yday
        emoji, label = OFFLINE_MESSAGES[day_index % len(OFFLINE_MESSAGES)]
        badge_color = "546e7a"
        badge_label = urllib.parse.quote(f"{emoji} {label}", safe="")
        status_note = (
            "😶\u200d🌫️ *maybe cooking something secretly...* 🤫"
        )
        # Use a neutral dark theme for offline state
        theme = THEMES["black"]

    else:  # active
        theme = get_theme_for_streak(streak)
        badge_color = theme["badge_color"]
        badge_label = f"🏆_Streak_Tier-{theme['tier'].replace(' ', '%20')}"
        status_note = (
            "🎨 Stats theme updates dynamically based on current streak"
            " | Powered by GitHub Actions"
        )

    # Build streak stats URL with themed parameters
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

    # Capsule render dividers with tier-specific effects
    capsule_divider_url = (
        f"https://capsule-render.vercel.app/api?type={theme['capsule_type']}"
        f"&color=0:{theme['gradient_start']},50:{theme['gradient_mid']},100:{theme['gradient_end']}"
        f"&height={theme['capsule_height']}"
        f"&section=header"
        f"&animation={theme['capsule_animation']}"
    )

    # Activity graph with matching theme
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

    # Build the section
    section = f"""
<p align="center">
  <img src="https://img.shields.io/badge/{badge_label}-{badge_color}?style=for-the-badge&labelColor=0d1117" />
</p>

<!-- Themed gradient divider with tier-specific effect -->
<p align="center">
  <img src="{capsule_divider_url}" width="70%" />
</p>

<!-- Streak Stats - Dynamically Themed -->
<p align="center">
  <img width="70%" src="{streak_url}" />
</p>

<!-- Activity Graph - Themed -->
<p align="center">
  <img width="95%" src="{graph_url}" />
</p>

<!-- Themed gradient divider with tier-specific effect -->
<p align="center">
  <img src="{capsule_divider_url}" width="70%" />
</p>

<p align="center">
  <sub>{status_note}</sub>
</p>
"""
    return section.strip()


def update_readme(readme_path: str, username: str, streak: int,
                  status: str = "active", state: dict | None = None) -> bool:
    """
    Update the README.md file with the dynamic stats section.
    Looks for markers: <!-- DYNAMIC-STATS:START --> and <!-- DYNAMIC-STATS:END -->
    """
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_section = generate_stats_section(username, streak, status, state)

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

    if new_content != content:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"README updated — status: '{status}', "
              f"theme: '{get_theme_name_for_streak(streak)}' "
              f"(streak: {streak})")
        return True
    else:
        print(f"No changes needed (streak: {streak}, "
              f"status: {status}, "
              f"theme: {get_theme_name_for_streak(streak)})")
        return False


def main():
    username = os.environ.get("GITHUB_USERNAME", "Unknown-2829")
    readme_path = os.environ.get("README_PATH", "README.md")

    # Allow override via environment variable for testing
    streak_override = os.environ.get("STREAK_OVERRIDE", "").strip()
    if streak_override:
        try:
            streak = int(streak_override)
        except ValueError:
            print(
                f"Error: STREAK_OVERRIDE must be an integer, got "
                f"{streak_override!r}",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"Using streak override: {streak}")
    else:
        streak = fetch_streak(username)
        print(f"Fetched streak for {username}: {streak}")

    # Load persisted streak state, compute status, then update and save state
    state = load_streak_state()
    status = compute_streak_status(streak, state)
    state = update_streak_state(streak, state)
    save_streak_state(state)
    print(f"Streak status: {status} "
          f"(last_positive_streak={state.get('last_positive_streak')}, "
          f"streak_zero_since={state.get('streak_zero_since')})")

    if streak > 0:
        theme_name = get_theme_name_for_streak(streak)
        theme = get_theme_for_streak(streak)
        print(f"Selected theme: {theme_name} ({theme['label']})")
        print(f"Tier: {theme['tier']}")

    updated = update_readme(readme_path, username, streak, status, state)

    if updated:
        print("✅ README.md updated successfully")
    else:
        print("ℹ️  No update needed or markers not found")


if __name__ == "__main__":
    main()

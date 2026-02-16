"""
Dynamic GitHub Stats Updater
Fetches GitHub streak data and updates README.md with conditional theming.

Streak Tiers:
  1-3   → Green theme  (fresh, growing — soft dull glow)
  4-8   → Blue theme   (steady, consistent — fade effect)
  9-30  → Red theme    (on fire, dominant — dark intensity)
  30+   → Black theme  (legendary, dark elite — special effects)

Each tier has unique visual effects: glow, fade, animation styles.
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


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
        "effect_desc": "soft dull glow",
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
        "effect_desc": "smooth fade transition",
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
        "effect_desc": "dark intensity pulse",
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
        "effect_desc": "elite shadow aura",
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


def fetch_streak(username: str) -> int:
    """
    Fetch the current streak count for a GitHub user.
    Uses the streak-stats API to get streak data.
    Falls back to GitHub API contributions if needed.
    """
    # Try fetching from GitHub API (contribution data)
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"

        url = f"https://api.github.com/users/{username}/events/public"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            events = json.loads(resp.read().decode())

        # Count consecutive days with push events
        if not events:
            return 0

        today = datetime.now(timezone.utc).date()
        dates_with_activity = set()
        for event in events:
            if event.get("type") in ("PushEvent", "CreateEvent", "PullRequestEvent",
                                     "IssuesEvent", "CommitCommentEvent"):
                event_date = datetime.strptime(
                    event["created_at"], "%Y-%m-%dT%H:%M:%SZ"
                ).date()
                dates_with_activity.add(event_date)

        if not dates_with_activity:
            return 0

        # Count consecutive days from today backwards
        from datetime import timedelta
        streak = 0
        check_date = today
        while check_date in dates_with_activity:
            streak += 1
            check_date -= timedelta(days=1)

        # If today has no activity, check from yesterday
        if streak == 0:
            check_date = today - timedelta(days=1)
            while check_date in dates_with_activity:
                streak += 1
                check_date -= timedelta(days=1)

        return streak

    except Exception as e:
        print(f"Warning: Could not fetch streak data: {e}", file=sys.stderr)
        return 0


def generate_stats_section(username: str, streak: int) -> str:
    """Generate the dynamic stats section markdown."""
    theme = get_theme_for_streak(streak)
    theme_name = get_theme_name_for_streak(streak)

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

    # Effect badge showing current visual effect
    effect_badge = (
        f"https://img.shields.io/badge/✨_Effect-"
        f"{theme['effect_desc'].replace(' ', '%20')}-"
        f"{theme['gradient_mid']}?style=flat-square&labelColor={theme['gradient_start']}"
    )

    # Build the section
    section = f"""
<p align="center">
  <img src="https://img.shields.io/badge/🏆_Streak_Tier-{theme['tier'].replace(' ', '%20')}-{theme['badge_color']}?style=for-the-badge&labelColor=0d1117" />
  <img src="{effect_badge}" />
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
  <sub>🎨 Stats theme updates dynamically based on current streak • {theme['label']} — {theme['effect_desc']} | Powered by GitHub Actions</sub>
</p>
"""
    return section.strip()


def update_readme(readme_path: str, username: str, streak: int) -> bool:
    """
    Update the README.md file with the dynamic stats section.
    Looks for markers: <!-- DYNAMIC-STATS:START --> and <!-- DYNAMIC-STATS:END -->
    """
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_section = generate_stats_section(username, streak)

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
        print(f"README updated with '{get_theme_name_for_streak(streak)}' "
              f"theme (streak: {streak})")
        return True
    else:
        print(f"No changes needed (streak: {streak}, "
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

    theme_name = get_theme_name_for_streak(streak)
    theme = get_theme_for_streak(streak)
    print(f"Selected theme: {theme_name} ({theme['label']})")
    print(f"Tier: {theme['tier']}")

    updated = update_readme(readme_path, username, streak)

    if updated:
        print("✅ README.md updated successfully")
    else:
        print("ℹ️  No update needed or markers not found")


if __name__ == "__main__":
    main()

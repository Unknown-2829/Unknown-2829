import sys
import re
import os
import json

with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Phase B #8: Partial traffic
old_traffic_fetch = """        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/traffic/views",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            views_data = json.loads(resp.read().decode("utf-8"))
        result["views_14d"] = views_data.get("count", 0)
        result["unique_visitors_14d"] = views_data.get("uniques", 0)

        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{repo}/traffic/clones",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            clones_data = json.loads(resp.read().decode("utf-8"))
        result["clones_14d"] = clones_data.get("count", 0)"""
new_traffic_fetch = """        views_data = None
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{owner}/{repo}/traffic/views",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                views_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"  Traffic views: {exc}", file=sys.stderr)
        
        result["views_available"] = views_data is not None
        result["views_14d"] = views_data.get("count", 0) if views_data else 0
        result["unique_visitors_14d"] = views_data.get("uniques", 0) if views_data else 0

        clones_data = None
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{owner}/{repo}/traffic/clones",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                clones_data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            print(f"  Traffic clones: {exc}", file=sys.stderr)

        result["clones_available"] = clones_data is not None
        result["clones_14d"] = clones_data.get("count", 0) if clones_data else 0"""
content = content.replace(old_traffic_fetch, new_traffic_fetch)

# phase B #8 save traffic summary
old_traffic_save = """        new_summary = _compute_rolling_totals(traffic_raw)
        _save_traffic_summary(new_summary)"""
new_traffic_save = """        existing = _load_traffic_summary()
        new_summary = _compute_rolling_totals(traffic_raw)
        if not traffic_raw.get("views_available", True):
            for key in ("views_14d", "unique_visitors_14d"):
                if key in existing:
                    new_summary[key] = existing[key]
        if not traffic_raw.get("clones_available", True):
            if "clones_14d" in existing:
                new_summary["clones_14d"] = existing["clones_14d"]
        _save_traffic_summary(new_summary)"""
content = content.replace(old_traffic_save, new_traffic_save)

# Phase B #7: Traffic day IST
utc_to_ist_func = """def _utc_ts_to_ist_date(ts: str) -> str:
    \"\"\"Convert a GitHub UTC timestamp string to IST date string YYYY-MM-DD.\"\"\"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(IST).strftime("%Y-%m-%d")
    except Exception:
        return ts[:10]

"""
content = content.replace("def _read_file_from_branch", utc_to_ist_func + "def _read_file_from_branch")
content = content.replace('if row.get("timestamp", "").startswith(today):', 'if _utc_ts_to_ist_date(row.get("timestamp", "")) == today:')

# Phase C #4: Explicit --theme
content = content.replace('def generate_stats_section(', 'def generate_stats_section(theme_is_forced: bool = False, ')
# Replace the theme selection block
old_theme_block = """    if theme_name and theme_name in THEMES:
        picked_name = theme_name
        theme = THEMES[theme_name]
        event_note = f"Forced Theme: {theme['label']}"
    elif status == "broken":
        picked_name = "broken"
        theme = None
        event_note = "?? Streak Dropped"
    elif status == "offline":
        picked_name = "offline"
        theme = None
        event_note = _pick_offline_message()
    else:
        picked_name, theme, event_note = pick_theme(now_ist, streak, state, username)"""
new_theme_block = """    if status == "broken":
        picked_name = "broken"
        theme = None
        event_note = "?? Streak Dropped"
    elif status == "offline":
        picked_name = "offline"
        theme = None
        event_note = _pick_offline_message()
    else:
        if theme_name and theme_is_forced and theme_name in THEMES:
            picked_name = theme_name
            theme = THEMES[theme_name]
            event_note = f"Forced Theme: {theme['label']}"
        else:
            picked_name, theme, event_note = pick_theme(now_ist, streak, state, username)"""
content = content.replace(old_theme_block, new_theme_block)

content = content.replace('theme_name=args.theme,', 'theme_name=args.theme,\n            theme_is_forced=user_forced_theme,')
content = content.replace('user_forced_theme = args.theme is not None', '') # just in case
content = re.sub(r'(\n\s*)args = parser\.parse_args\(\)', r'\1args = parser.parse_args()\n\1user_forced_theme = args.theme is not None', content)

# Phase C #6: --date simulation clock
content = content.replace('def compute_streak_status(streak: int, state: dict) -> str:', 'def compute_streak_status(streak: int, state: dict, now_ist=None) -> str:')
content = content.replace('now = _now_ist()', 'now = now_ist if now_ist else _now_ist()', 1) # inside compute_streak_status

content = content.replace('def update_streak_state(streak: int, state: dict) -> dict:', 'def update_streak_state(streak: int, state: dict, now_ist=None) -> dict:')
# inside update_streak_state
content = re.sub(r'def update_streak_state\(.*?:\n\s*now = _now_ist\(\)', r'def update_streak_state(streak: int, state: dict, now_ist=None) -> dict:\n    now = now_ist if now_ist else _now_ist()', content, 1)

content = content.replace('def _check_missing_festival_years() -> None:', 'def _check_missing_festival_years(now_ist=None) -> None:')
content = re.sub(r'def _check_missing_festival_years\(.*?:\n\s*now = _now_ist\(\)', r'def _check_missing_festival_years(now_ist=None) -> None:\n    now = now_ist if now_ist else _now_ist()', content, 1)

content = content.replace('def fetch_recent_activity(username: str, token: str = None, n: int = 5) -> list[dict]:', 'def fetch_recent_activity(username: str, token: str = None, n: int = 5, now_utc=None) -> list[dict]:')
content = content.replace('now = datetime.now(timezone.utc)', 'now = now_utc if now_utc else datetime.now(timezone.utc)')
# ensure diff doesn't go negative
old_diff = """            event_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            diff = now - event_time"""
new_diff = """            event_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            diff = now - event_time
            if diff.total_seconds() < 0:
                diff = timedelta(0)"""
content = content.replace(old_diff, new_diff)

# fix timezone normal in main
old_sim_dt = """        sim_dt = datetime.strptime(args.date, "%Y-%m-%d")
        now_ist = sim_dt.replace(tzinfo=IST)
        print(f"Simulation mode: time set to {now_ist.isoformat()}")"""
new_sim_dt = """        sim_dt = datetime.strptime(args.date, "%Y-%m-%d")
        if sim_dt.tzinfo is not None:
            sim_dt = sim_dt.astimezone(IST)
        else:
            sim_dt = sim_dt.replace(tzinfo=IST)
        now_ist = sim_dt
        print(f"Simulation mode: time set to {now_ist.isoformat()}")"""
content = content.replace(old_sim_dt, new_sim_dt)

# Phase C #15 Missing README markers
content = content.replace('return False  # Start marker missing', 'return _README_INVALID_MARKERS')
content = content.replace('return False  # End marker missing', 'return _README_INVALID_MARKERS')
content = content.replace('import json', 'import json\n_README_INVALID_MARKERS = "INVALID_MARKERS"', 1)

# Phase D #18 RunResult
content = content.replace('import json', 'import json\nclass _RunResult:\n    SUCCESS = "SUCCESS"\n    DEGRADED = "DEGRADED"\n    FAILED = "FAILED"\n', 1)
content = re.sub(r'(\n\s*)run_state = _load_run_state\(\)', r'\1run_state = _load_run_state()\1run_result = _RunResult.SUCCESS', content)

# replace updated boolean checks in main
old_updated_check = """    if updated:
        if args.dry_run:
            print("✅ Dry run complete — no files modified")
        else:
            print("✅ README.md updated successfully")
            run_state = record_run_success(run_state)
            close_failure_issue(run_state, token, username)
    else:
        print("ℹ️  No update needed — README content unchanged")"""
new_updated_check = """    if updated == _README_INVALID_MARKERS:
        print("❌ Error: DYNAMIC-STATS markers missing from README — structure broken.", file=sys.stderr)
        run_state["consecutive_failures"] = run_state.get("consecutive_failures", 0) + 1
        if not args.dry_run:
            _save_run_state(run_state)
        sys.exit(1)
    elif updated:
        if args.dry_run:
            print("✅ Dry run complete — no files modified")
        else:
            print("✅ README.md updated successfully")
    else:
        print("ℹ️  No update needed — README content unchanged")
        
    if not args.dry_run:
        run_state = record_run_success(run_state)
        close_failure_issue(run_state, token, username)"""
content = content.replace(old_updated_check, new_updated_check)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

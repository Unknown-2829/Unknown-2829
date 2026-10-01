import sys
import os
import re

with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix indent at 2812
content = content.replace(
    '    # \ufffd Stage 4: Project status pings \ufffd\n        if args.skip_pings:\n        print("Skipping project status pings (--skip-pings) - using last-known status")',
    '    # \ufffd Stage 4: Project status pings \ufffd\n    if args.skip_pings:\n        print("Skipping project status pings (--skip-pings) - using last-known status")'
)

# wait the '' characters might be messing up my string replace. Let's just use regex
content = re.sub(
    r'    # [^\n]*Stage 4: Project status pings[^\n]*\n\s*if args\.skip_pings:\n\s*print\("Skipping project status pings \(--skip-pings\)',
    r'    # Stage 4: Project status pings\n    if args.skip_pings:\n        print("Skipping project status pings (--skip-pings)',
    content
)

# Phase B: #14 load_streak_state
old_load = """def load_streak_state() -> dict:
    \"\"\"Load the persisted streak state from disk (data/streak_state.json).\"\"\"
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"last_positive_streak": None, "streak_zero_since": None}"""

new_load = """def load_streak_state() -> dict:
    \"\"\"Load the persisted streak state from disk (data/streak_state.json).\"\"\"
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"last_positive_streak": None, "streak_zero_since": None}
    except (json.JSONDecodeError, IOError) as exc:
        print(f"Warning: streak state is corrupt ({exc}) — using defaults. "
              f"Investigate {STATE_FILE}.", file=sys.stderr)
        return {"last_positive_streak": None, "streak_zero_since": None}"""
content = content.replace(old_load, new_load)

# phase B #14 _load_run_state
old_load_run = """def _load_run_state() -> dict:
    try:
        with open(_RUN_STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}"""
new_load_run = """def _load_run_state() -> dict:
    try:
        with open(_RUN_STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, IOError) as exc:
        print(f"Warning: run state is corrupt ({exc}) — using defaults. "
              f"Investigate {_RUN_STATE_FILE}.", file=sys.stderr)
        return {}"""
content = content.replace(old_load_run, new_load_run)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

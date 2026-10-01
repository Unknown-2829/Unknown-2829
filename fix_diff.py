import sys
import re

with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Phase D #38: Timestamp semantic diff
strip_func = """import re as _re
_TS_PATTERN = _re.compile(r'Last refresh: [\\d\\w :,]+IST')

def _strip_volatile(text: str) -> str:
    return _TS_PATTERN.sub("Last refresh: NORMALIZED", text)

def update_readme("""
content = content.replace("def update_readme(", strip_func, 1)

old_diff_check = """    if new_content == old_content and not force:
        return False  # no update needed"""
new_diff_check = """    if _strip_volatile(new_content) == _strip_volatile(old_content) and not force:
        return False  # no semantic change"""
content = content.replace(old_diff_check, new_diff_check)

# Phase D #34: Critical save failures affect run result
# Let's check where _atomic_write_json is called for streak state
old_save_streak = """def save_streak_state(state: dict) -> None:
    _atomic_write_json(STATE_FILE, state)"""
new_save_streak = """def save_streak_state(state: dict) -> None:
    try:
        _atomic_write_json(STATE_FILE, state)
    except Exception as exc:
        print(f"Error saving streak state: {exc}", file=sys.stderr)
        raise"""
content = content.replace(old_save_streak, new_save_streak)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

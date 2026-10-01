import sys
import re
import json

with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 20: cache_graph retries
# change `[5, 15, 30]` to `[5, 15]`
content = content.replace("_BACKOFF = [5, 15, 30]", "_BACKOFF = [5, 15]")
content = content.replace("with delays of 5, 15, and 30 seconds", "with delays of 5 and 15 seconds") # update docstring

# Fix the exception handling block in cache_graph
old_except = """        except Exception as exc:
            print(
                f"  cache_graph attempt {attempt + 1} failed: {exc}",
                file=sys.stderr,
            )
            if attempt < len(_BACKOFF) - 1:
                print(f"  Retrying in {backoff} s…", file=sys.stderr)
                time.sleep(backoff)
            continue"""
new_except = """        except Exception as exc:
            print(
                f"  cache_graph attempt {attempt + 1} failed: {exc}",
                file=sys.stderr,
            )
            # Don't retry permanent client errors
            exc_str = str(exc)
            if any(f"HTTP {code}" in exc_str for code in ("400", "401", "403", "404")):
                print(f"  Permanent error — not retrying.", file=sys.stderr)
                break
            if attempt < len(_BACKOFF) - 1:
                print(f"  Retrying in {backoff} s…", file=sys.stderr)
                time.sleep(backoff)
            continue"""
content = content.replace(old_except, new_except)

old_status_check = """                if resp.status != 200:
                    raise ValueError(f"HTTP {resp.status}")"""
new_status_check = """                if resp.status != 200:
                    print(
                        f"  cache_graph attempt {attempt + 1}: HTTP {resp.status}",
                        file=sys.stderr,
                    )
                    raise ValueError(f"HTTP {resp.status}")"""
content = content.replace(old_status_check, new_status_check)

# Fix 21: SVG validation
old_svg_check = """    ns_match = _re.match(rb"<svg[^>]+xmlns=\"([^\"]+)\"", stripped)
    ns = ns_match.group(1).decode("utf-8") if ns_match else ""
    ns_prefix = f"{{{ns}}}" if ns else ""

    try:
        root = ET.fromstring(data.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return False"""
new_svg_check = """    try:
        root = ET.fromstring(data.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return False
    # Verify actual SVG root element (handle optional namespace prefix)
    local_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if local_tag != "svg":
        return False"""
content = content.replace(old_svg_check, new_svg_check)

# Fix 22: pick_line() consecutive-day guarantee
old_pick_line = """    key = (now_ist.strftime("%Y-%m-%d") + group).encode()
    idx = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(pool)

    return pool[idx]"""
new_pick_line = """    # Deterministic: hash of YYYY-MM-DD + group
    key = (now_ist.strftime("%Y-%m-%d") + group).encode()
    idx = int.from_bytes(hashlib.sha256(key).digest()[:4], "big") % len(pool)

    # Guarantee no consecutive repeat: if today == yesterday's pick, advance by 1
    yesterday = (now_ist - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_key = (yesterday + group).encode()
    yesterday_idx = int.from_bytes(hashlib.sha256(yesterday_key).digest()[:4], "big") % len(pool)
    if idx == yesterday_idx and len(pool) > 1:
        idx = (idx + 1) % len(pool)

    return pool[idx]"""
content = content.replace(old_pick_line, new_pick_line)

# Fix 24: Anniversary date uses UTC
old_anni = """created_at = repo_info.get("created_at")
        if created_at:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return dt.strftime("%m-%d")"""
new_anni = """created_at = repo_info.get("created_at")
        if created_at:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return dt.astimezone(IST).strftime("%m-%d")"""
content = content.replace(old_anni, new_anni)

# Fix 25: Negative streak override
old_streak_args = """        streak = args.streak
        override = True"""
new_streak_args = """        streak = args.streak
        if streak < 0:
            print(f"Error: --streak must be >= 0, got {streak}", file=sys.stderr)
            sys.exit(1)
        override = True"""
content = content.replace(old_streak_args, new_streak_args)

old_streak_env = """        streak = int(streak_override_env)
        override = True"""
new_streak_env = """        streak = int(streak_override_env)
        if streak < 0:
            print(f"Error: STREAK_OVERRIDE must be >= 0, got {streak}", file=sys.stderr)
            sys.exit(1)
        override = True"""
content = content.replace(old_streak_env, new_streak_env)

# Fix 26: Dead code removal
content = re.sub(r'^import shutil\n', '', content, flags=re.MULTILINE)
content = re.sub(r'^import html\n', '', content, flags=re.MULTILINE)

content = re.sub(r'def build_live_blocks.*?return live_html\n', '', content, flags=re.DOTALL)
content = re.sub(r'live_html = build_live_blocks\(.*?\)\n\s*live_block_str = .*?\n', 'live_block_str = ""\n', content)
content = re.sub(r'def build_project_status_block.*?return html\n', '', content, flags=re.DOTALL)
content = re.sub(r'_LIVE_NOTE = .*?\n\n', '', content, flags=re.DOTALL)
content = re.sub(r'\s*tier_display = theme\["tier"\].replace\(" ", "%20"\)', '', content)
content = re.sub(r'import re as _re\n\s*', '', content)
content = content.replace('_re.search', 're.search')

# Fix 27: _FIXED_EVENTS redundant label
content = re.sub(r'\("(\d{2}-\d{2})", "([^"]+)", "[^"]+"\),', r'("\1", "\2"),', content)
old_fixed_loop = """    for mmdd, theme_key, label in _FIXED_EVENTS:
        if today_mmdd == mmdd:
            return theme_key, THEMES[theme_key], label"""
new_fixed_loop = """    for mmdd, theme_key in _FIXED_EVENTS:
        if today_mmdd == mmdd:
            note = THEMES[theme_key]["label"]
            return theme_key, THEMES[theme_key], note"""
content = content.replace(old_fixed_loop, new_fixed_loop)

# Fix 29: Traffic history
content = content.replace('daily = [r for r in rows if "date" in r]', 'daily = sorted([r for r in rows if "date" in r], key=lambda r: r["date"])')

# Fix 30: Analytics referrer/path values not Markdown-escaped
md_escape_func = """def _md_escape(s: str) -> str:
    \"\"\"Escape Markdown table-sensitive characters.\"\"\"
    return str(s).replace("\\\\", "\\\\\\\\").replace("|", "\\\\|").replace("`", "'")

"""
content = content.replace("def build_analytics_block", md_escape_func + "def build_analytics_block")

old_ref_row = """            ref_rows += f"| `{r.get('ref','?')}` | {r.get('count',0)} | {r.get('uniques',0)} |\\n\""""
new_ref_row = """            ref_rows += f"| `{_md_escape(r.get('ref','?'))}` | {r.get('count',0)} | {r.get('uniques',0)} |\\n\""""
content = content.replace(old_ref_row, new_ref_row)

old_path_row = """            path_rows += f"| `{p.get('path','?')}` | {p.get('count',0)} | {p.get('uniques',0)} |\\n\""""
new_path_row = """            path_rows += f"| `{_md_escape(p.get('path','?'))}` | {p.get('count',0)} | {p.get('uniques',0)} |\\n\""""
content = content.replace(old_path_row, new_path_row)

# Fix 31: Job summary escaping
old_job_summary = """    for label, value in items:
        lines.append(f"| {label} | {value} |\\n\")"""
new_job_summary = """    for label, value in items:
        lines.append(f"| {_md_escape(label)} | {_md_escape(value)} |\\n\")"""
content = content.replace(old_job_summary, new_job_summary)

# Fix 33: ping_url
content = content.replace("t0 = time.time()", "t0 = time.monotonic()")
content = content.replace("elapsed = time.time() - t0", "elapsed = time.monotonic() - t0")

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

import sys
import re

with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: timedelta 365 -> 364
content = content.replace("timedelta(days=365)", "timedelta(days=364)")
content = content.replace("minus 365 days", "minus 364 days") # Update comment if present

# Fix 2: shivratri -> maha_shivratri
content = re.sub(r'\"shivratri\"\s*:', '"maha_shivratri":', content)
content = content.replace('"shivratri"', '"maha_shivratri"')
# Let's do this carefully
content = content.replace("'shivratri'", "'maha_shivratri'")

# Fix 3: Dec 1 reminder issues (idempotency) + remove `_reminder_issued_year`
# In `config/events_data.json` we remove `_reminder_issued_year`.
with open('config/events_data.json', 'r', encoding='utf-8') as f:
    events_data = f.read()
events_data = re.sub(r'\s*"_reminder_issued_year":\s*\d+,?', '', events_data)
# Also fix comments in events_data.json if needed for shivratri -> maha_shivratri
events_data = events_data.replace('"shivratri"', '"maha_shivratri"')
with open('config/events_data.json', 'w', encoding='utf-8') as f:
    f.write(events_data)

new_check_missing_func = """def _check_missing_festival_years() -> None:
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
        print(f"Warning: config/events_data.json missing {next_year} rows for: {missing}",
              file=sys.stderr)
        return

    title = f"[reminder] Add {next_year} festival dates to config/events_data.json"

    # Idempotency: skip if an open reminder issue for this title already exists
    try:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{username}/{username}/issues?state=open&labels=reminder&per_page=50",
            headers={"Authorization": f"token {token}", "User-Agent": _USER_AGENT,
                     "Accept": "application/vnd.github.v3+json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            existing_issues = json.loads(resp.read().decode())
        if any(i.get("title") == title for i in existing_issues):
            print(f"Reminder issue already open for {next_year} — skipping.")
            return
    except Exception as exc:
        print(f"Warning: could not check existing reminder issues: {exc}", file=sys.stderr)
        # Proceed to create if check fails (better to create a dup than miss it entirely)

    body = (
        f"The following festivals are missing {next_year} dates in `config/events_data.json`:\\n\\n"
        + "\\n".join(f"- `{k}`" for k in missing)
        + "\\n\\nPlease verify against an authoritative panchang / Islamic calendar "
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
        print(f"Warning: could not open reminder issue: {exc}", file=sys.stderr)"""

content = re.sub(r'def _check_missing_festival_years\(\) -> None:.*?print\(f"Warning: could not open reminder issue: \{exc\}", file=sys\.stderr\)', new_check_missing_func, content, flags=re.DOTALL)

# Fix 5: skip pings project statuses
new_skip_pings = """    if args.skip_pings:
        print("Skipping project status pings (--skip-pings) — using last-known status")
        project_statuses = {k: v.get("status", "up") for k, v in _load_project_status().items()}"""
content = re.sub(r'if args\.skip_pings:\s+print\("Skipping project status pings \(--skip-pings\)"\)\s+project_statuses = \{\}', new_skip_pings, content)

# Fix 9: _ensure_data_branch
new_ensure_branch = """    if not _ensure_data_branch(username, repo, token):
        print("  Traffic: data branch unavailable — skipping append.", file=sys.stderr)
        return False"""
content = re.sub(r'_ensure_data_branch\(username, repo, token\)', new_ensure_branch, content, count=1)

# Fix 10: Part A
prune_code = """    # Prune stale keys not in canonical tracked set
    stale = [k for k in cache if k not in tracked]
    for k in stale:
        print(f"  Pruning stale repo meta key: {k!r}")
        del cache[k]

    _save_repo_meta(cache)"""
content = content.replace('_save_repo_meta(cache)', prune_code, 1)

# Fix 11: fetch_repo_meta
new_fetch = """        if fresh:
            cached_entry = cache.get(repo, {})
            cache[repo] = {**cached_entry, **fresh}
            print(f"  repo meta {repo}: release={cache[repo].get('release')} commits={cache[repo].get('commits')}")"""
content = re.sub(r'if fresh:\s+cache\[repo\] = fresh\s+print\(f"  repo meta \{repo\}: release=\{fresh\.get\(\'release\'\)\} commits=\{fresh\.get\(\'commits\'\)\}"\)', new_fetch, content)

# Fix 13: Atomic write
atomic_write_func = """def _atomic_write_json(path: str, data: dict) -> None:
    \"\"\"Write JSON atomically via temp file + os.replace.\"\"\"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=parent or ".", suffix=".tmp"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
"""

# Insert _atomic_write_json before save_streak_state
content = content.replace("def save_streak_state(", atomic_write_func + "\ndef save_streak_state(")

# Replace open(..., 'w') in all 5 functions
content = re.sub(r'with open\(STATE_FILE, "w", encoding="utf-8"\) as f:\s*json\.dump\(state, f, indent=2\)\s*f\.write\("\\n"\)', '_atomic_write_json(STATE_FILE, state)', content)

content = re.sub(r'with open\(_TRAFFIC_SUMMARY_FILE, "w"\) as f:\s*json\.dump\(data, f, indent=2\)\s*f\.write\("\\n"\)', '_atomic_write_json(_TRAFFIC_SUMMARY_FILE, data)', content)

content = re.sub(r'with open\(_STATUS_FILE, "w"\) as f:\s*json\.dump\(data, f, indent=2\)\s*f\.write\("\\n"\)', '_atomic_write_json(_STATUS_FILE, data)', content)

content = re.sub(r'with open\(_REPO_META_FILE, "w"\) as f:\s*json\.dump\(data, f, indent=2\)\s*f\.write\("\\n"\)', '_atomic_write_json(_REPO_META_FILE, data)', content)

content = re.sub(r'with open\(_RUN_STATE_FILE, "w"\) as f:\s*json\.dump\(data, f, indent=2\)\s*f\.write\("\\n"\)', '_atomic_write_json(_RUN_STATE_FILE, data)', content)

# Fix 17: Failure counter reset
new_success_block = """    if updated:
        if args.dry_run:
            print("✅ Dry run complete — no files modified")
        else:
            print("✅ README.md updated successfully")
    else:
        print("ℹ️  No update needed — README content unchanged")

    # Reset failure counter on every successful pipeline completion
    # (regardless of whether README content changed)
    if not args.dry_run:
        run_state = record_run_success(run_state)
        close_failure_issue(run_state, token, username)"""

content = re.sub(r'if updated:\s+if args\.dry_run:\s+print\("✅ Dry run complete — no files modified"\)\s+else:\s+print\("✅ README\.md updated successfully"\)\s+run_state = record_run_success\(run_state\)\s+close_failure_issue\(run_state, token, username\)\s+else:\s+print\("ℹ️  No update needed — README content unchanged"\)', new_success_block, content)

# Fix 19: Cache freshness report
content = content.replace("cache_graph(graph_url, os.path.join(ASSETS_DIR, \"activity-graph.svg\"))", "graph_refreshed = cache_graph(graph_url, os.path.join(ASSETS_DIR, \"activity-graph.svg\"))")
content = content.replace("cache_graph(streak_url, os.path.join(ASSETS_DIR, \"streak-card.svg\"))", "streak_refreshed = cache_graph(streak_url, os.path.join(ASSETS_DIR, \"streak-card.svg\"))")

content = content.replace("(\"Graph cache\", \"✅ fresh\" if os.path.exists(os.path.join(ASSETS_DIR, \"activity-graph.svg\")) else \"⚠️ missing\"),", "(\"Graph cache\", \"✅ refreshed\" if graph_refreshed else (\"↩️ existing\" if os.path.exists(os.path.join(ASSETS_DIR, \"activity-graph.svg\")) else \"⚠️ missing\")),")
content = content.replace("(\"Streak card cache\", \"✅ fresh\" if os.path.exists(os.path.join(ASSETS_DIR, \"streak-card.svg\")) else \"⚠️ missing\"),", "(\"Streak card cache\", \"✅ refreshed\" if streak_refreshed else (\"↩️ existing\" if os.path.exists(os.path.join(ASSETS_DIR, \"streak-card.svg\")) else \"⚠️ missing\")),")

# initialize graph_refreshed and streak_refreshed
content = content.replace("if args.dry_run:", "graph_refreshed = False\n    streak_refreshed = False\n\n    if args.dry_run:")

# Fix 20: cache_graph retries
# ... this requires careful replacement, maybe regex ...
# We will do this via a small custom script logic if needed

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

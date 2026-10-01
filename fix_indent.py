import sys
with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = re.sub(
    r'    repo = username\n        if not _ensure_data_branch\(username, repo, token\):\n        print\("  Traffic: data branch unavailable — skipping append\.", file=sys\.stderr\)\n        return False',
    r'    repo = username\n    if not _ensure_data_branch(username, repo, token):\n        print("  Traffic: data branch unavailable - skipping append.", file=sys.stderr)\n        return False',
    content
)
# also try with - instead of em-dash
content = re.sub(
    r'    repo = username\n        if not _ensure_data_branch\(username, repo, token\):\n        print\("  Traffic: data branch unavailable - skipping append\.", file=sys\.stderr\)\n        return False',
    r'    repo = username\n    if not _ensure_data_branch(username, repo, token):\n        print("  Traffic: data branch unavailable - skipping append.", file=sys.stderr)\n        return False',
    content
)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

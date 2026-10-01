import sys
with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
content = content.replace(
    '        fresh = fetch_repo_meta(owner, repo, token)\n                if fresh:\n            cached_entry = cache.get(repo, {})\n            cache[repo] = {**cached_entry, **fresh}',
    '        fresh = fetch_repo_meta(owner, repo, token)\n        if fresh:\n            cached_entry = cache.get(repo, {})\n            cache[repo] = {**cached_entry, **fresh}'
)

content = content.replace(
    '        # Prune stale keys not in canonical tracked set\n    stale = [k for k in cache if k not in tracked]',
    '    # Prune stale keys not in canonical tracked set\n    stale = [k for k in cache if k not in tracked]'
)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

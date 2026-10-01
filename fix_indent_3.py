import sys
with open('phantom_engine.py', 'r', encoding='utf-8') as f:
    content = f.read()

import re
old_text = """    if args.dry_run:
            print("? Dry run complete - no files modified")
        else:
            print("? README.md updated successfully")
            # Stage 4: success - reset failure counter, close any open issue
            run_state = record_run_success(run_state)
            close_failure_issue(run_state, token, username)
    else:
        print("??  No update needed or markers not found")"""

# Let's just fix the whole if args.dry_run block. Wait, I replaced it before but it looks mangled.

# Actually, the original code was:
#    if updated:
#        ...
#    else:
#        ...

# Wait, let me just fix the indentation manually:
content = re.sub(
    r'    if args\.dry_run:\n            print\("([^"]*)"\)\n        else:\n            print\("([^"]*)"\)\n            [^\n]*\n            run_state = record_run_success\(run_state\)\n            close_failure_issue\(run_state, token, username\)\n    else:',
    r'    if updated:\n        if args.dry_run:\n            print("\1")\n        else:\n            print("\2")\n            run_state = record_run_success(run_state)\n            close_failure_issue(run_state, token, username)\n    else:',
    content
)

with open('phantom_engine.py', 'w', encoding='utf-8') as f:
    f.write(content)

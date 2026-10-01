import sys
import glob

for filename in glob.glob('tests/test_*.py'):
    with open(filename, 'r', encoding='utf-8') as f:
        content = f.read()

    # fix update_streak_state mock
    content = content.replace('lambda streak, state: state', 'lambda streak, state, **kwargs: state')
    content = content.replace('lambda *args, **kwargs:', 'lambda *args, **kwargs:') # just in case

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)

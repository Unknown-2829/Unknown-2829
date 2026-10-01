import glob
for f in glob.glob('tests/test_*.py'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    content = content.replace('lambda s, st: st', 'lambda s, st, **kwargs: st')
    content = content.replace('_check_missing_festival_years", lambda: None', '_check_missing_festival_years", lambda **kwargs: None')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)

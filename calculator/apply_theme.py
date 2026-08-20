from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP = {"index.html"}

NAV = '''<nav class="site-nav"><a class="site-back" href="index.html">← 返回式神首頁</a><a class="site-brand" href="index.html">⛩ 鬥技工具</a></nav>'''
LINK = '<link rel="stylesheet" href="theme.css?v=20260820">'

for path in ROOT.glob("*.html"):
    if path.name in SKIP:
        continue
    text = path.read_text(encoding="utf-8")
    changed = False

    if "theme.css" not in text:
        text = text.replace("</head>", f"{LINK}</head>", 1)
        changed = True

    if "site-nav" not in text:
        text = text.replace("<body>", f"<body>{NAV}", 1)
        changed = True

    if changed:
        path.write_text(text, encoding="utf-8")
        print(f"updated {path.name}")

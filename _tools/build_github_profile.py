"""Render the public profile snapshot into the site's GitHub page."""
from pathlib import Path
import re
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT/'github/profile.md').read_text()
# The profile banner/badges are replaced by the site's heading and typography.
source = re.sub(r'<p[^>]*>.*?</p>', '', source, flags=re.S)
body = MarkdownIt('commonmark', {'html': True}).render(source)
page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub | Glecko</title><meta name="description" content="Glenn Bojanov's projects in scientific software, creative coding, and knowledge systems.">
<link rel="icon" href="/favicon.png"><link rel="stylesheet" href="./style.css"><link rel="canonical" href="https://glecko.xyz/github/">
</head><body><header class="topbar"><a class="brand" href="/">GLECKO<span>.</span></a><nav aria-label="Project navigation"><a aria-current="page" href="./">Projects</a><a href="./stats/">Traffic</a><a href="https://github.com/glebo309">GitHub ↗</a></nav></header>
<main class="profile"><div class="eyebrow">Glenn Bojanov / Code</div><h1>Code &amp; projects.</h1><p class="lead">Scientific software, music tools, and experiments in creative coding.</p>
<div class="actions"><a class="button" href="https://github.com/glebo309">Explore my GitHub ↗</a><a class="text-link" href="./stats/">View project traffic →</a></div>
<article>''' + body + '''</article>
<footer>Project descriptions from my <a href="https://github.com/glebo309">GitHub profile</a>. <a href="./stats/">Traffic archive</a></footer></main></body></html>'''
(ROOT/'github/index.html').write_text(page)
print(ROOT/'github/index.html')

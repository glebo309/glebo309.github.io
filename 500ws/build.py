#!/usr/bin/env python3
"""Optional, dependency-free page generator. Run: python3 build.py"""
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo
from html import escape, unescape
from urllib.parse import urlparse, unquote
import json, re, unicodedata, os
from content_tools import load_content, clean_html, safe_url, portable_url
ROOT=Path(__file__).resolve().parent
DATA=load_content(ROOT)
# Clear previously generated redirects so deleted entries cannot leave broken links.
if (ROOT/'route-map.json').exists():
 for old,target in json.loads((ROOT/'route-map.json').read_text()).items():
  if not old.strip('/') or target.startswith('assets/'):continue
  redirect=ROOT/old.lstrip('/')/'index.html'
  if redirect.resolve().is_relative_to(ROOT) and redirect.is_file():redirect.unlink()
# Remove only generated event/news pages before regenerating changed slugs.
for pattern in ['event-*.html','news-*.html','story-*.html','member-*.html']:
 for old_page in ROOT.glob(pattern): old_page.unlink()
TODAY=datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
E=lambda s:escape(str(s),quote=True)
ARROW='<svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 12h15M13 5l7 7-7 7"/></svg>'
UP='<svg class="arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M6 18 18 6M6 6h12v12"/></svg>'
FLOWER='<svg class="flower" viewBox="0 0 100 100" aria-hidden="true">'+''.join(f'<ellipse cx="50" cy="27" rx="11" ry="23" fill="currentColor" transform="rotate({i*45} 50 50)"/>' for i in range(8))+'<circle cx="50" cy="50" r="11" fill="#f5cd62"/></svg>'
EMAIL=DATA.get('email','500wsbern@gmail.com')
HOME=DATA.get('home',{})
NAV=[('About','about.html'),('Community','members.html'),('Events','events.html'),('Stories','stories.html'),('Resources','resources.html')]
BASE='https://www.500womenscientistsfribourgbern.ch'
def slug(s):
 s=unicodedata.normalize('NFKD',unquote(s)).encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+','-',s).strip('-')[:145]
def key(url):return unquote(urlparse(unescape(url)).path).rstrip('/')
ROUTES={'':'index.html','/':'index.html','/contact':'contact.html','/members':'members.html','/news':'news.html','/blog':'stories.html','/events':'events.html','/past-events':'events.html#past-events','/interesting-links':'resources.html','/resources':'resources.html','/good-reads':'resources.html#reading','/500ws-switzerland':'about.html#switzerland'}
ROUTES.update({'/sign':'seri-letter.html','/_files/ugd/cffde5_6d4253c12ab344aca1e64eff0999aecb.pdf':'assets/linked-document.pdf'})
ROUTES.update({'/newsletter-archive':'archive.html#newsletters','/newsletters':'archive.html#newsletters','/oldnews':'archive.html','/pub':'archive.html#documents','/accreditation-initiative':'accreditation-initiative.html'})
for tag in ['1','2','3','SciCommSeptember']:ROUTES['/blog-old/hashtags/'+tag]='stories.html'
for kind,prefix in [('members','member'),('posts','story'),('events','event'),('news','news')]:
 for i,item in enumerate(DATA[kind]):
  item['file']=prefix+'-'+((item['date']+'-') if kind in ['events','news'] else '')+slug((item.get('title') if kind=='news' else item.get('slug')) or item.get('title') or item.get('name') or str(i))+'.html'
  if item.get('source'):ROUTES.setdefault(key(item['source']),item['file'])
def rewrite(body):
 body=clean_html(body)
 def href(m):
  url=unescape(m.group(1)); parsed=urlparse(url)
  if parsed.netloc=='500wsbern.wixsite.com':url='index.html'
  if parsed.netloc in ['www.500womenscientistsfribourgbern.ch','500womenscientistsfribourgbern.ch']:
   target=ROUTES.get(key(url))
   if target:url=target
  return 'href="'+E(url)+'"'
 body=re.sub(r'href="([^"]+)"',href,body)
 body=re.sub(r'<p>(?:\s|&nbsp;|<br\s*/?>)*</p>','',body)
 return body

def brand():return '<a class="brand" href="index.html" aria-label="500 Women Scientists Bern-Fribourg home"><span class="brand-mark"><img src="assets/home-0.webp" alt="" width="1500" height="1159"></span><span class="brand-words">500 WOMEN<br>SCIENTISTS<small>Bern · Fribourg</small></span></a>'
def header(active):
 links=''.join(f'<a href="{url}"'+(' aria-current="page"' if active==url else '')+f'>{title}</a>' for title,url in NAV)
 return f'<a class="skip" href="#main">Skip to content</a><div class="header-space"><header class="site-header"><div class="wrap header-inner">{brand()}<button class="menu-toggle" aria-controls="site-nav" aria-expanded="false">Menu</button><nav class="nav" id="site-nav" aria-label="Main navigation">{links}<a class="btn btn-primary" href="contact.html">Join the community {ARROW}</a></nav></div></header></div>'
def footer():return f'''<footer class="site-footer"><div class="wrap"><div class="footer-grid"><div class="footer-about">{brand()}<p>A local community with a shared belief:<br>science is stronger when everyone belongs.</p></div><div class="footer-links"><h2>Explore the pod</h2><a href="about.html">Our story &amp; mission</a><a href="members.html">Meet the community</a><a href="events.html">Events &amp; gatherings</a><a href="stories.html">Stories from our members</a><a href="news.html">News &amp; open letters</a><a href="archive.html">Newsletters &amp; archive</a><a href="resources.html">Resources &amp; good reads</a></div><div class="footer-links"><h2>Let’s connect</h2><a href="mailto:{EMAIL}">{EMAIL}</a><a href="https://www.instagram.com/500ws_fribourg.bern/">Instagram ↗</a><a href="https://www.linkedin.com/company/500-women-scientists-bern-fribourg">LinkedIn ↗</a><a href="https://m.facebook.com/500-Women-Scientists-Fribourg-Bern-107631694331389/">Facebook ↗</a><a href="contact.html">Join our community</a></div></div><div class="footer-bottom"><span>© 500 Women Scientists Bern-Fribourg</span><span>Independent. Volunteer-led. Open to you.</span></div></div></footer>'''
def page(file,title,body,active='',desc='Connecting, supporting and amplifying women in science in Bern and Fribourg. Discover our community, events and stories.'):
 html=f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><meta name="theme-color" content="#653d82"><meta name="description" content="{E(desc)}"><title>{E(title)} | 500 Women Scientists Bern-Fribourg</title><meta property="og:title" content="{E(title)} | 500 Women Scientists Bern-Fribourg"><meta property="og:description" content="{E(desc)}"><meta property="og:type" content="website"><meta name="referrer" content="strict-origin-when-cross-origin"><link rel="icon" href="assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="styles.css"><script src="site.js" defer></script><noscript><style>.toolbar{{display:none}}@media(max-width:850px){{.menu-toggle{{display:none}}.header-inner{{flex-wrap:wrap;padding-block:15px}}.nav{{display:flex;position:static;flex-wrap:wrap;padding:0;font-size:12px;box-shadow:none;border:0;max-height:none;gap:15px}}.nav .btn{{margin:0}}}}</style></noscript></head><body>{header(active)}<main id="main">{body}</main>{footer()}</body></html>'''
 (ROOT/file).write_text("\n".join(line.rstrip() for line in html.splitlines())+"\n")
def intro(kicker,title,text):return f'<section class="wrap page-intro"><p class="eyebrow">{kicker}</p><h1>{title}</h1><p class="lead">{text}</p></section>'
def cta():return f'<section class="wrap section"><div class="join-panel"><div><p class="eyebrow">There’s a place for you here</p><h2>Bring your curiosity.<br>Find your community.</h2><p>Every discipline. Every career stage. Join a local network of women making science more open and inclusive.</p></div><a class="btn btn-light" href="contact.html">Say hello {ARROW}</a></div></section>'
def formatdate(s):
 try:return date.fromisoformat(s).strftime('%d %B %Y').lstrip('0')
 except:return s or ''
def eventrow(ev,detail=False):
 d=date.fromisoformat(ev['date']);f=ev['file']
 return f'''<article class="event-row" data-event-date="{E(ev['date'])}" data-category="{'upcoming' if ev['date']>=TODAY else 'past'}"><time class="event-date" datetime="{E(ev['date'])}">{d.strftime('%b').upper()}<strong>{d.day:02d}</strong><small>{d.year}</small></time><div><span class="tag">{E(ev['category'])}</span><h3><a href="{f}">{E(ev['title'])}</a></h3><p>{E(ev.get('location') or 'See event details')}</p>{'<a class="text-link" href="'+f+'">Read event details '+ARROW+'</a>' if detail else ''}</div><a class="round-link" href="{f}" aria-label="{E(ev['title'])}, {formatdate(ev['date'])}">{ARROW}</a></article>'''
def storycard(p):return f'''<article class="story-card" data-category="all"><a href="{p['file']}"><div class="story-image"><img src="{E(p.get('image') or 'assets/events-1.webp')}" alt="" width="600" height="400" loading="lazy"></div><div class="story-meta"><span>From the community</span><time datetime="{E(p['date'])}">{formatdate(p['date'])}</time></div><h3>{E(p['title'])}</h3><p>{E(p['author'])}</p><span class="text-link">Read the story {ARROW}</span></a></article>'''
posts=sorted(DATA['posts'],key=lambda x:x['date'],reverse=True)
events=sorted(DATA['events'],key=lambda x:x['date'],reverse=True)
# Home
hero=f'''<section class="wrap hero"><div class="hero-grid"><div><p class="eyebrow">500 Women Scientists · Bern–Fribourg</p><h1>{"<br>".join(E(line) if i < len(HOME["headline"].splitlines())-1 else "<span class=accent>"+E(line)+"</span>" for i,line in enumerate(HOME["headline"].splitlines()))}</h1><p class="lead">{E(HOME["description"])}</p><div class="actions"><a class="btn btn-primary" href="contact.html">Find your community {ARROW}</a><a class="text-link" href="about.html">Get to know us {ARROW}</a></div></div><div class="hero-visual"><img class="hero-photo" src="{E(safe_url(HOME["image"]))}" alt="{E(HOME["imageAlt"])}" width="1800" height="1350" fetchpriority="high"><span class="hero-location">LOCAL CONNECTIONS. SHARED POSSIBILITIES.</span><div class="hero-note">{FLOWER}<p>Different disciplines.<br>Shared ambition.</p></div><span class="hero-caption">Our community, beyond the lab</span></div></div></section><div class="wrap"><div class="intro-strip"><p>LOCAL ROOTS.<br>GLOBAL MOVEMENT.</p><div><strong>Since 2019</strong><span>Connecting women in STEM</span></div><div><strong>All disciplines</strong><span>A wider circle of perspectives</span></div><div><strong>Every career stage</strong><span>A place to belong and grow</span></div></div></div>'''
mission=f'''<section class="wrap section"><div class="mission-intro"><div><p class="eyebrow">Why we come together</p><h2>More voices.<br>Better science.</h2></div><p>{E(HOME["mission"])}</p></div><div class="pillars"><div class="pillar"><span class="number">01</span><h3>Build connections.</h3><p>Meet peers across disciplines, exchange experiences and find support for the next step in your career.</p></div><div class="pillar"><span class="number">02</span><h3>Make science visible.</h3><p>Bring research beyond the lab through talks, outreach and stories that put women scientists in the spotlight.</p></div><div class="pillar"><span class="number">03</span><h3>Help change the culture.</h3><p>Advocate for fairer working conditions and a scientific community where more people can thrive.</p></div></div></section>'''
community=f'''<section class="community-band section"><div class="wrap community-grid"><div class="community-photos"><img src="assets/members-8.webp" alt="Claudia Kasper" loading="lazy" width="300" height="400"><img src="assets/members-13.webp" alt="Ana I. Benítez-Mateos" loading="lazy" width="300" height="400"><img src="assets/members-19.webp" alt="Andrea Fortier" loading="lazy" width="300" height="400"></div><div><p class="eyebrow">The people behind the pod</p><h2>Many paths.<br>One community.</h2><p class="lead">Researchers, science communicators and women working across STEM. Our members bring different experiences, and make this community their own.</p><a class="text-link space-top" href="members.html">Meet our members {ARROW}</a></div></div></section>'''
recent=f'''<section class="wrap section"><div class="section-head"><div><p class="eyebrow">Beyond the everyday</p><h2>Good things happen<br>when we get together.</h2><p class="section-sub">A look back at our gatherings, conversations and shared ideas.</p></div><a class="text-link" href="events.html">Explore our events {ARROW}</a></div>{''.join(eventrow(e) for e in [ev for ev in events if ev['date']<TODAY][:3])}<div class="meeting-callout"><div><h3>New to the pod? Come say hello.</h3><p>Our regular meetings are a relaxed way to meet the community. Email us to find out about the next gathering.</p></div><a class="text-link" href="mailto:{EMAIL}?subject=Next%20pod%20meeting">Ask about the next meeting {ARROW}</a></div></section>'''
stories=f'''<section class="stories-bg section"><div class="wrap"><div class="section-head"><div><p class="eyebrow">Ideas worth sharing</p><h2>Voices from our community.</h2></div><a class="text-link" href="stories.html">All stories {ARROW}</a></div><div class="story-grid">{''.join(storycard(p) for p in posts[:3])}</div></div></section>'''
page('index.html','Good science. Stronger together.',hero+mission+community+recent+stories+cta())
# About
body=intro('Our story','A local community.<br>A shared purpose.','We believe that science should be open, inclusive and collaborative. Our pod brings that belief to life in Bern and Fribourg.')
body+=f'''<section class="wrap page-section"><div class="community-grid"><img class="about-image" src="assets/contact-0.webp" alt="Members together on a retreat in the Swiss mountains" width="1800" height="1350"><div class="prose">{rewrite(DATA['pageContent']['aboutHtml'])}</div></div></section><section class="community-band section"><div class="article-wrap prose"><p class="eyebrow">What brings us together</p>{rewrite(DATA['pageContent']['goalsHtml'])}</div></section><section class="wrap page-section" id="switzerland"><div class="article-wrap prose"><img src="assets/switzerland-0.webp" alt="500 Women Scientists Switzerland" width="500"><p class="source-note">The following describes the Swiss association and its founding committee in February 2022.</p>{rewrite(DATA['pageContent']['switzerlandHtml'])}<figure><img src="assets/switzerland-1.webp" alt="The Swiss steering committee in 2022" loading="lazy"><figcaption>The Swiss steering committee in 2022.</figcaption></figure></div></section>'''+cta()
page('about.html','Our story',body,'about.html')
# Members
cards=[]
for m in DATA['members']:
 category='former' if 'former' in m['role'].lower() else 'active'
 role=m['role'];photo=m.get('image') or 'assets/home-0.webp'
 cards.append(f'<article class="member-card" data-category="{category}"><a href="{m["file"]}"><img src="{E(photo)}" alt="{E(m.get("imageAlt") or m["name"])}" width="400" height="400" loading="lazy"><h2>{E(m["name"])}</h2><p>{E(role)}</p><span class="text-link">Meet {E(m["name"].replace("Dr. ","").split()[0])} {ARROW}</span></a></article>')
 body=f'<div class="wrap"><a class="breadcrumb" href="members.html">← Back to the community</a><article class="profile-layout"><img class="profile-photo" src="{E(photo)}" alt="{E(m["name"])}"><div><p class="eyebrow">{E(role)}</p><h1>{E(m["name"])}</h1><div class="prose">{rewrite(m["bioHtml"])}</div><div class="actions">'+''.join(f'<a class="btn btn-outline" href="{E(safe_url(l["url"]))}">{E(l["label"])} {UP}</a>' for l in m.get('links',[]))+'</div></div></article></div>'
 page(m['file'],m['name'],body,'members.html')
body=intro('Our community','The people who<br>make it happen.','Different fields, different journeys. Meet the members and volunteer organisers behind our community.')
body+='''<section class="wrap page-section"><div class="toolbar"><div class="filters" data-filter-group="members" aria-label="Filter members"><button class="filter" data-filter="all" aria-pressed="true">Everyone</button><button class="filter" data-filter="active" aria-pressed="false">Active members</button><button class="filter" data-filter="former" aria-pressed="false">Former members</button></div><div class="search-wrap"><label for="member-search">Find a member</label><input id="member-search" data-search="members" type="search" placeholder="Search by name"></div></div><p class="results-count" data-count="members" aria-live="polite"></p><div class="members-grid" id="members" data-noun="members">'''+''.join(cards)+'''</div><p class="empty-state" data-empty="members" hidden>No members match your search. Try another name or select Everyone.</p></section>'''+cta()
page('members.html','Meet the community',body,'members.html')
# Events
for ev in events:
 state='Upcoming event' if ev['date']>=TODAY else 'From the event archive'
 body=f'<article class="article-wrap"><a class="breadcrumb" href="events.html">← All events</a><p class="eyebrow space-top">{state}</p><h1>{E(ev["title"])}</h1><div class="story-meta"><time datetime="{E(ev["date"])}">{formatdate(ev["date"])}</time><span>{E(ev["category"])}</span></div><p class="lead">{E(ev.get("location") or "")}</p><div class="prose space-top">{rewrite(ev["bodyHtml"])}</div><p class="source-note">This page records the event as announced at the time. <a href="contact.html">Contact the pod</a> for current activities.</p></article>'
 page(ev['file'],ev['title'],body,'events.html')
body=intro('Events & gatherings','Better conversations.<br>New connections.','From informal meetups to workshops and science in the pub, our events make room for ideas, support and shared discovery.')
body+=f'''<section class="wrap page-section"><h2 class="archive-heading" style="margin-top:0">Coming up</h2><div id="upcoming-events">{''.join(eventrow(e,True) for e in events if e['date']>=TODAY)}</div><div class="empty-state" id="no-upcoming"{' hidden' if any(e['date']>=TODAY for e in events) else ''}><h2>Our next gathering is taking shape.</h2><p>There are no upcoming dates listed just yet. Get in touch for the next pod meeting, or follow us on Instagram for updates.</p><div class="actions"><a class="btn btn-primary" href="mailto:{EMAIL}?subject=Next%20pod%20meeting">Ask about the next meeting {ARROW}</a><a class="text-link" href="https://www.instagram.com/500ws_fribourg.bern/">Follow on Instagram {UP}</a></div></div><h2 class="archive-heading">From the archive</h2><p class="section-sub">The conversations and connections we’ve shared.</p><div id="past-events" class="space-top">{''.join(eventrow(e,True) for e in events if e['date']<TODAY)}</div></section>'''+cta()
page('events.html','Events & gatherings',body,'events.html')
# Articles
for p in posts:
 body=p['bodyHtml']
 # The editorial hero replaces an identical leading cover image.
 body=re.sub(r'^\s*<img[^>]*>',lambda match: '' if re.search(r'src=[\"\']'+re.escape(p.get('image',''))+r'[\"\']', match.group(0)) else match.group(0),body,count=1)
 body=f'<article class="article-wrap"><a class="breadcrumb" href="stories.html">← All stories</a><h1>{E(p["title"])}</h1><div class="story-meta"><span>{E(p["author"])}</span><time datetime="{E(p["date"])}">{formatdate(p["date"])}</time></div><img class="article-hero" src="{E(p.get("image") or "assets/events-1.webp")}" alt=""><div class="prose">{rewrite(body)}</div><p class="source-note">From the 500 Women Scientists Bern-Fribourg archive. Originally published {formatdate(p["date"])}.</p><a class="text-link" href="stories.html">Explore more stories {ARROW}</a></article>'
 page(p['file'],p['title'],body,'stories.html')
body=intro('Voices from the community','Science has<br>many stories.','Ideas, experiences and perspectives from our members, collaborators and sister organisations.')
body+='''<section class="wrap page-section"><div class="toolbar"><div data-filter-group="stories" class="filters"><button class="filter" aria-pressed="true" data-filter="all">All stories</button><a class="filter" href="news.html">Pod news &amp; open letters</a></div><div class="search-wrap"><label for="story-search">Find a story</label><input type="search" id="story-search" data-search="stories" placeholder="Topic, title or author"></div></div><p class="results-count" data-count="stories" aria-live="polite"></p><div class="story-grid" id="stories" data-noun="stories">'''+''.join(storycard(p) for p in posts)+f'''</div><p class="empty-state" data-empty="stories" hidden>No stories match your search. Try another title, author or topic.</p><div class="meeting-callout"><div><h3>Have a story to share?</h3><p>We welcome contributions from members, collaborators and organisations working towards equality in science.</p></div><a class="text-link" href="mailto:{EMAIL}?subject=Story%20contribution">Get in touch {ARROW}</a></div></section>'''
page('stories.html','Stories from our community',body,'stories.html')
# News
news_cards=[]
for n in DATA['news']:
 body=f'<article class="article-wrap"><a class="breadcrumb" href="news.html">← All news</a><p class="eyebrow space-top">{E(n.get("category","Pod news"))}</p><h1>{E(n["title"])}</h1><div class="story-meta"><time datetime="{E(n["date"])}">{formatdate(n["date"])}</time></div><div class="prose space-top">{rewrite(n["bodyHtml"])}</div></article>'
 page(n['file'],n['title'],body,'stories.html')
 news_cards.append(f'<article class="news-item"><span class="tag">{E(n.get("category","News"))}</span><h3><a href="{n["file"]}">{E(n["title"])}</a></h3><div class="story-meta">{formatdate(n["date"])}</div><a class="text-link" href="{n["file"]}">Read more {ARROW}</a></article>')
page('news.html','News & open letters',intro('News & advocacy','Our community,<br>in action.','Updates, open letters and reports from the pod and our wider network.')+'<section class="wrap page-section"><div class="news-list">'+''.join(news_cards)+'</div></section>','stories.html')
# Resources preserve the original descriptions and recommendations.
body=intro('Resources & good reads','Knowledge to share.<br>Support to turn to.','A collection of useful organisations and reading recommendations from our community.')+'<section class="wrap page-section"><div class="resource-list">'+''.join(f'<article class="resource"><h2>{E(item["title"])}</h2><div class="prose">{rewrite(item["bodyHtml"])}</div></article>' for item in DATA['resources'])+'</div></section>'
body+='<section class="stories-bg section" id="reading"><div class="wrap"><p class="eyebrow">Our community bookshelf</p><h2>Good reads.</h2><div class="resource-list space-top">'+''.join(f'<article class="resource"><h2>{E(item["title"])}</h2><div class="prose">{rewrite(item["bodyHtml"])}</div></article>' for item in DATA['reading'])+'</div></div></section>'+cta()
page('resources.html','Resources & good reads',body,'resources.html')
# Newsletters and older campaigns remain accessible from the archive.
ROUTES.update({'/newsletter-archive':'archive.html#newsletters','/newsletters':'archive.html#newsletters','/oldnews':'archive.html','/pub':'archive.html#documents','/accreditation-initiative':'accreditation-initiative.html'})
for item in DATA.get('legacyPages',[]):
 page(item['slug']+'.html',item['title'],'<article class="article-wrap"><a class="breadcrumb" href="archive.html">← Community archive</a><p class="eyebrow space-top">Historical campaign</p><h1>'+E(item['title'])+'</h1><div class="prose space-top">'+rewrite(item['bodyHtml'])+'</div></article>','stories.html')
body=intro('The community archive','Our shared history.','Newsletters, campaigns and documents from the Bern–Fribourg pod.')
body+='<section class="wrap page-section" id="newsletters"><h2>Newsletters.</h2><div class="resource-list space-top">'+''.join(f'<article class="resource"><h3>{E(item["title"])}</h3><a class="text-link" href="{E(item["file"])}">Read the newsletter (PDF) {UP}</a></article>' for item in DATA.get('newsletters',[]))+'</div></section>'
body+='<section class="community-band section"><div class="wrap"><h2>Advocacy.</h2><div class="actions"><a class="btn btn-outline" href="accreditation-initiative.html">University accreditation initiative '+ARROW+'</a><a class="btn btn-outline" href="seri-letter.html">2023 SERI letter '+ARROW+'</a><a class="btn btn-outline" href="news.html">News & open letters '+ARROW+'</a></div></div></section>'
body+='<section class="wrap page-section" id="documents"><h2>Campaigns & event documents.</h2><div class="resource-list space-top">'+''.join(f'<article class="resource"><h3>{E(item["title"])}</h3><a class="text-link" href="{E(item["file"])}">Open document (PDF) {UP}</a></article>' for item in DATA.get('legacyDocuments',[]))+'</div></section>'
page('archive.html','Newsletters & community archive',body,'stories.html')
# Contact: real email actions, no fake submission success or third-party form backend.
body=intro('Come as you are','Your next connection<br>starts with hello.','Curious about the pod, looking for a community or planning a collaboration? We’d love to hear from you.')
body+=f'''<section class="wrap page-section"><div class="contact-grid"><div><div class="contact-way"><h2>Join our community.</h2><p>There is no joining fee or commitment. Tell us a little about yourself, and we’ll help you find your place in the pod.</p><a class="btn btn-primary space-top" href="mailto:{EMAIL}?subject=Joining%20500WS%20Bern-Fribourg">Email us to join {ARROW}</a></div><div class="contact-way"><h2>Stay in the loop.</h2><p>Ask to join our mailing list for news and activities. You can also follow us on Instagram and LinkedIn.</p><a class="text-link" href="mailto:{EMAIL}?subject=Mailing%20list%20request">Request mailing list updates {ARROW}</a></div><div class="contact-way"><h2>Let’s make something happen.</h2><p>Have an idea for an event, a story or a collaboration? Send us a message.</p><a class="text-link" href="mailto:{EMAIL}">{EMAIL} {UP}</a></div><p class="section-sub">Email links open your email app. You can also copy the address above.</p></div><div><img class="contact-photo" src="assets/contact-0.webp" alt="The pod together in Grächen, with snow-covered mountains behind them" width="1800" height="1350"><p class="section-sub">Connections that go beyond the workplace.</p></div></div></section><section class="community-band section"><div class="wrap faq"><p class="eyebrow">A few things you might be wondering</p><h2>There’s room for you.</h2><details><summary>Who is the community for?</summary><p>Our community brings together women across STEM, career stages and professional paths, including academia, research institutions, industry, NGOs, science communication and policymaking. We particularly welcome researchers from abroad and underrepresented minorities.</p></details><details><summary>Do I need to work at a particular university?</summary><p>No. We are independent of specific universities and research institutions. Our members bring experiences from different workplaces and disciplines.</p></details><details><summary>Is there a membership fee?</summary><p>There is no joining fee or commitment. Get in touch and we’ll introduce you to the community.</p></details><details><summary>Can I come to an event before joining?</summary><p>Many of our events are open to non-members. Email us to find out about the next gathering and come meet us in person.</p></details><details><summary>Can our organisation collaborate with you?</summary><p>Yes. We are open to collaboration and cross-promotion with groups and projects promoting equality in STEM or academia. Email us with your idea.</p></details></div></section>'''
page('contact.html','Join the community',body,'contact.html')
for letter in DATA.get('letters',[]):
 page('seri-letter.html',letter['title'],intro('Advocacy archive · 23 March 2023',letter['title'],'A letter calling for an independent national reporting centre to address discrimination and harassment in academic institutions.')+'<article class="article-wrap"><p class="source-note">This is a historical campaign page. For questions about the letter, <a href="mailto:500wsbern@gmail.com?subject=2023%20SERI%20letter%20enquiry">contact the pod</a>.</p><div class="prose space-top">'+rewrite(letter['bodyHtml'])+'</div></article>','stories.html')
page('404.html','Page not found',intro('Let’s get you back','A different path?','This page has moved or is no longer available.')+'<section class="wrap page-section"><a class="btn btn-primary" href="index.html">Back to the homepage '+ARROW+'</a></section>')
(ROOT/'assets/favicon.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" rx="22" fill="#f5cd62"/>'+''.join(f'<ellipse cx="50" cy="30" rx="10" ry="20" fill="#653d82" transform="rotate({i*45} 50 50)"/>' for i in range(8))+'<circle cx="50" cy="50" r="10" fill="#f5cd62"/></svg>')
(ROOT/'.nojekyll').write_text('')
# Preserve known incoming links from the former Wix site.
for old,target in ROUTES.items():
 if not old or target.startswith('assets/'):continue
 p=ROOT/old.lstrip('/')/'index.html'
 if p==ROOT/'index.html':continue
 p.parent.mkdir(parents=True,exist_ok=True)
 relative=os.path.relpath(ROOT/target.split('#')[0],p.parent)+('#'+target.split('#',1)[1] if '#' in target else '')
 p.write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="0;url={E(relative)}"><title>Page moved | 500 Women Scientists Bern-Fribourg</title><p>This page has moved. <a href="{E(relative)}">Continue to the new page.</a></p></html>')
(ROOT/'route-map.json').write_text(json.dumps(ROUTES,ensure_ascii=False,indent=2))
print(f'Built {len(list(ROOT.glob("*.html")))} pages, {len(ROUTES)-1} legacy routes. Content: {len(DATA["members"])} members, {len(posts)} stories, {len(events)} events, {len(DATA["news"])} news articles.')

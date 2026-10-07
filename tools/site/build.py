"""Build and validate the static Pages site from the repository's Markdown.

Install tools/site/requirements.txt, then run python tools/site/build.py.
Use --check to detect stale generated files without writing them.
"""
import argparse
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET

import markdown

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
BASE = 'https://anthonyogorman.github.io/ashes-server-lab/'
REPO = 'https://github.com/AnthonyOGorman/ashes-server-lab'
DESCRIPTION = ('Experimental open-source C++20 server emulation for Ashes of Creation: '
               'local Verra exploration, terrain collision, movement, flight and live browser tools.')
PAGES = [
    ('tools/site/home.md', 'index.html', 'Ashes Server Lab — Ashes of Creation Private Server / Server Emulator', DESCRIPTION),
    ('README.md', 'getting-started.html', 'Getting started — Ashes Server Lab', 'Build the experimental Ashes of Creation exploration server, prepare your matching client, generate terrain and troubleshoot local setup.'),
    ('docs/FAQ.md', 'faq.html', 'Ashes of Creation private server FAQ — Ashes Server Lab', 'Factual answers about offline Verra exploration, client compatibility, multiplayer, missing gameplay and this unofficial experimental server emulator.'),
    ('docs/ARCHITECTURE.md', 'architecture.html', 'Server architecture — Ashes Server Lab', 'C++20 runtime, lobby and world protocols, local EOS shim, movement, terrain collision and browser controls for Ashes Server Lab.'),
    ('docs/TERRAIN.md', 'terrain.html', 'Terrain collision — Ashes Server Lab', 'Offline terrain extraction from your own Ashes of Creation client archives, landscape coverage, collision admission and limitations.'),
    ('docs/ROADMAP.md', 'roadmap.html', 'Development roadmap — Ashes Server Lab', 'Research priorities for exploration stability, world fidelity and maintainable server emulation; no promised delivery schedule.'),
    ('docs/VERIFICATION.md', 'verification.html', 'Verification and evidence — Ashes Server Lab', 'Recorded source-only tests, client setup, terrain validation and real-client evidence, including the limits of each result.'),
    ('CONTRIBUTING.md', 'contributing.html', 'Contributing — Ashes Server Lab', 'Contribute reproducible fixes and synthetic tests to the experimental C++ exploration server without distributing proprietary assets or private data.'),
    ('docs/THIRD_PARTY.md', 'third-party.html', 'Licenses and third-party notices — Ashes Server Lab', 'Original MIT lab code, third-party dependency licenses and the exclusion of proprietary client files, SDKs and game assets.'),
]
SOURCE_URLS = {(ROOT / source).resolve(): target for source, target, _, _ in PAGES}


def rewrite_url(value, source):
    """Resolve Markdown's repository-relative links for the published docs root."""
    parsed = urlsplit(html.unescape(value))
    if parsed.scheme or parsed.netloc or not parsed.path:
        return html.unescape(value)
    target = (source.parent / unquote(parsed.path)).resolve()
    fragment = '#' + parsed.fragment if parsed.fragment else ''
    if target in SOURCE_URLS:
        return SOURCE_URLS[target] + fragment
    try:
        repo_path = target.relative_to(ROOT).as_posix()
    except ValueError:
        raise ValueError(f'Link outside repository: {value} in {source}')
    if not target.exists():
        raise ValueError(f'Missing source link: {value} in {source}')
    if target.is_relative_to(DOCS) and target.suffix.lower() != '.md':
        return quote(target.relative_to(DOCS).as_posix()) + fragment
    return REPO + '/blob/main/' + quote(repo_path) + fragment


def render(source, target, title, description):
    path = ROOT / source
    text = path.read_text(encoding='utf-8')
    # GitHub renders Markdown inside its centered README wrapper; remove that
    # presentation wrapper for the static guide, while preserving the source.
    text = text.replace('<div align="center">', '').replace('</div>', '')
    text = text.replace('<details>', '<details markdown="1">')
    body = markdown.markdown(text, extensions=['extra', 'toc'])
    body = re.sub(r'(href|src)="([^"]+)"',
                  lambda match: match[1] + '="' + html.escape(rewrite_url(match[2], path), quote=True) + '"', body)
    body = re.sub(r'<img ', '<img loading="lazy" decoding="async" ', body)
    canonical = BASE if target == 'index.html' else BASE + target
    schema = ''
    if target == 'index.html':
        data = {'@context': 'https://schema.org', '@type': 'SoftwareSourceCode',
                'name': 'Ashes Server Lab', 'description': DESCRIPTION,
                'url': BASE, 'codeRepository': REPO, 'programmingLanguage': 'C++20',
                'runtimePlatform': 'Windows x64', 'license': REPO + '/blob/main/LICENSE',
                'isAccessibleForFree': True}
        schema = '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'
    esc = html.escape
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description, quote=True)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Ashes Server Lab">
<meta property="og:title" content="{esc(title, quote=True)}">
<meta property="og:description" content="{esc(description, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{BASE}social-preview.png">
<meta property="og:image:width" content="1280">
<meta property="og:image:height" content="640">
<meta property="og:image:alt" content="Ashes Server Lab — experimental Ashes of Creation server emulation">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title, quote=True)}">
<meta name="twitter:description" content="{esc(description, quote=True)}">
<meta name="twitter:image" content="{BASE}social-preview.png">
<meta name="twitter:image:alt" content="Ashes Server Lab — experimental Ashes of Creation server emulation">
<link rel="stylesheet" href="site.css">
{schema}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header><nav aria-label="Main navigation"><a href="./">Ashes Server Lab</a><a href="getting-started.html#get-started">Get started</a><a href="faq.html">FAQ</a><a href="architecture.html">Architecture</a><a href="roadmap.html">Roadmap</a><a href="{REPO}">GitHub repository</a></nav></header>
<main id="main">
{body}
<p class="source"><a href="{REPO}/blob/main/{source}">Edit this page's Markdown source on GitHub</a></p>
</main>
<footer><p>Independent, unofficial and experimental. Not affiliated with, supported by, or endorsed by Intrepid Studios. No client or proprietary game assets are distributed. Original code: <a href="{REPO}/blob/main/LICENSE">MIT</a>; <a href="third-party.html">third-party notices</a>.</p><p><a href="verification.html">Verification and limitations</a> · <a href="contributing.html">Contribute</a> · <a href="llms.txt">Curated project guide</a></p></footer>
</body>
</html>
'''


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids, self.links, self.canonical, self.h1s = set(), [], [], 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise ValueError('Duplicate HTML id: ' + attrs['id'])
            self.ids.add(attrs['id'])
        if tag == 'h1':
            self.h1s += 1
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs['href'])
        for attribute in ('href', 'src'):
            if attribute in attrs:
                self.links.append(attrs[attribute])


def validate(outputs):
    pages = {name: Page(text) for name, text in outputs.items() if name.endswith('.html')}
    for name, page in pages.items():
        expected = BASE if name == 'index.html' else BASE + name
        if page.canonical != [expected] or page.h1s != 1:
            raise ValueError(f'Invalid canonical or H1 count: {name}')
        for link in page.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                if not link.startswith(BASE):
                    continue
                parsed = urlsplit(link[len(BASE):])
            destination = unquote(parsed.path) or name
            if destination == './':
                destination = 'index.html'
            if destination not in outputs and not (DOCS / destination).is_file():
                raise ValueError(f'Broken internal link: {name}: {link}')
            if parsed.fragment and destination in pages and parsed.fragment not in pages[destination].ids:
                raise ValueError(f'Broken anchor: {name}: {link}')
    sitemap = ET.fromstring(outputs['sitemap.xml'])
    namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    locations = [element.text for element in sitemap.findall('s:url/s:loc', namespace)]
    expected = [BASE if target == 'index.html' else BASE + target for _, target, _, _ in PAGES]
    if locations != expected:
        raise ValueError('Sitemap does not match published pages')
    print(f'Validated {len(pages)} static pages, canonical URLs, local links/anchors and sitemap.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = {target: render(source, target, title, description)
               for source, target, title, description in PAGES}
    outputs['site.css'] = (ROOT / 'tools/site/site.css').read_text(encoding='utf-8')
    outputs['.nojekyll'] = ''
    urls = ''.join(f'<url><loc>{BASE if target == "index.html" else BASE + target}</loc></url>\n'
                   for _, target, _, _ in PAGES)
    outputs['sitemap.xml'] = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + urls + '</urlset>\n'
    outputs['robots.txt'] = 'User-agent: *\nAllow: /\n\nSitemap: ' + BASE + 'sitemap.xml\n'
    outputs['llms.txt'] = (ROOT / 'tools/site/llms.txt').read_text(encoding='utf-8')
    validate(outputs)
    stale = []
    for filename, content in outputs.items():
        path = DOCS / filename
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                stale.append(filename)
        else:
            path.write_text(content, encoding='utf-8', newline='\n')
    if stale:
        raise SystemExit('Regenerate the site: ' + ', '.join(stale))
    print('Generated site is current.' if args.check else 'Wrote static site to docs/.')


if __name__ == '__main__':
    main()

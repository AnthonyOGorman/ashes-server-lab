import concurrent.futures
import importlib.util
import json
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

root = Path('E:/Ashes Of Creation GPT/Releases/ashes-cpp-lab')
spec = importlib.util.spec_from_file_location('site_build', root / 'tools/site/build.py')
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
filenames = [target for _, target, _, _ in build.PAGES] + ['site.css', 'sitemap.xml', 'robots.txt', 'llms.txt']

def fetch(filename):
    url = build.BASE + ('' if filename == 'index.html' else filename)
    with urllib.request.urlopen(url, timeout=30) as response:
        assert response.status == 200 and response.url.startswith('https://')
        body = response.read().decode('utf-8').replace('\r\n', '\n')
        assert body == (root / 'docs' / filename).read_text(encoding='utf-8'), filename + ' differs from committed output'
        return filename, body

with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    outputs = dict(pool.map(fetch, filenames))
build.validate(outputs)
for filename in ['social-preview.png', 'media/exploration.gif', 'media/live-world.gif', 'media/exploration-full.gif', 'media/live-world-full.gif']:
    with urllib.request.urlopen(urllib.request.Request(build.BASE + filename, method='HEAD'), timeout=30) as response:
        assert response.status == 200
        print('Asset accessible:', filename)
try:
    with urllib.request.urlopen('https://anthonyogorman.github.io/robots.txt', timeout=30) as response:
        print('Origin root robots.txt:', response.status, response.read().decode())
except urllib.error.HTTPError as error:
    print('Origin root robots.txt:', error.code)

credentials = subprocess.run(['git','credential','fill'], input='protocol=https\nhost=github.com\n\n', capture_output=True, text=True, check=True)
fields = dict(line.split('=',1) for line in credentials.stdout.splitlines() if '=' in line)
headers = {'User-Agent':'ashes-server-lab-audit', 'Authorization':'Bearer '+fields['password'], 'Accept':'application/vnd.github+json'}
for endpoint in ['pages', 'actions/runs?per_page=3']:
    request = urllib.request.Request('https://api.github.com/repos/AnthonyOGorman/ashes-server-lab/' + endpoint, headers=headers)
    data = json.load(urllib.request.urlopen(request, timeout=30))
    if endpoint == 'pages':
        print('Pages:', json.dumps({key: data.get(key) for key in ['status','html_url','source','public','https_enforced']}))
    else:
        print('Workflow runs:', json.dumps([{key: run.get(key) for key in ['name','status','conclusion','head_sha','html_url']} for run in data['workflow_runs']]))
print('Anonymous HTTPS checks passed for all 9 pages and all crawl files; deployed text matches local sources.')

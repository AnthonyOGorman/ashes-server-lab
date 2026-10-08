"""Use the existing Git credential for authorized repository maintenance."""
import json
import subprocess
import sys
import urllib.error
import urllib.request

credential = subprocess.run(
    ['git', 'credential', 'fill'],
    input='protocol=https\nhost=github.com\n\n',
    text=True, capture_output=True, check=True,
)
fields = dict(line.split('=', 1) for line in credential.stdout.splitlines() if '=' in line)
headers = {
    'Accept': 'application/vnd.github+json',
    'User-Agent': 'ashes-server-lab-maintenance',
    'Authorization': 'Bearer ' + fields['password'],
    'X-GitHub-Api-Version': '2022-11-28',
}
method, path = sys.argv[1:3]
payload = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
request = urllib.request.Request(
    'https://api.github.com/' + path.lstrip('/'),
    data=json.dumps(payload).encode() if payload is not None else None,
    headers=headers, method=method,
)
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read().decode()
        print(response.status)
        print(content)
except urllib.error.HTTPError as error:
    print(error.code)
    print(error.read().decode())
    sys.exit(1)

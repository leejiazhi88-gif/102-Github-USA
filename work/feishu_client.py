"""Small Feishu Sheets value client; configuration and data stay local."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote, urlencode

BASE = 'https://open.feishu.cn/open-apis/'


def config(path):
    values = {}
    if path.exists():
        for raw in path.read_text(encoding='utf-8-sig').splitlines():
            line = raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('\"\'')
    for key in ('FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'FEISHU_WIKI_TOKEN', 'FEISHU_SHEET_ID'):
        values[key] = os.environ.get(key, values.get(key, ''))
        if not values[key]:
            raise ValueError(f'Missing configuration: {key}')
    return values


def request(method, path, token=None, body=None):
    # Send credentials through stdin, keeping them out of process arguments.
    lines = ['silent', 'show-error', 'max-time = 45', f'request = "{method}"',
             'header = "Content-Type: application/json; charset=utf-8"',
             'url = ' + json.dumps(BASE + path)]
    if token:
        lines.append('header = ' + json.dumps('Authorization: Bearer ' + token))
    if body is not None:
        lines.append('data = ' + json.dumps(json.dumps(body, ensure_ascii=False), ensure_ascii=False))
    result = subprocess.run(['curl', '--config', '-'], input='\n'.join(lines),
                            capture_output=True, text=True, timeout=50)
    if result.returncode:
        raise RuntimeError(f'HTTPS request failed (curl exit {result.returncode})')
    payload = json.loads(result.stdout)
    if payload.get('code') != 0:
        raise RuntimeError(f"Feishu API error {payload.get('code')}: {payload.get('msg')}")
    return payload

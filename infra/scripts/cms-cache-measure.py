#!/usr/bin/env python3
"""Count actual Django dev access-log lines for sequential full document visits.

Run once on the base revision and once after Phase 8, against an otherwise idle
local stack. This script never edits data, starts servers or changes revisions.
"""
import argparse
import datetime
import json
import re
import subprocess
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label', required=True)
parser.add_argument('--origin', default='http://localhost:8090')
parser.add_argument('--page', required=True, help='Ruta publicada, por ejemplo /es/legal/envios')
args = parser.parse_args()
result = {'etapa': args.label, 'visitas': []}
for path in ['/es', args.page]:
    if not path.startswith('/es') or path.startswith('//'):
        parser.error('Usa rutas locales en español')
    for visit in ['primera', 'repetida']:
        start = datetime.datetime.now(datetime.UTC).isoformat()
        req = urllib.request.Request(args.origin.rstrip('/') + path, headers={'Accept': 'text/html'})
        with urllib.request.urlopen(req, timeout=30) as response:
            response.read()
        logs = subprocess.run(
            ['docker', 'compose', '-f', 'infra/docker-compose.dev.yml', 'logs', '--no-color', '--since', start, 'backend'],
            check=True, capture_output=True, text=True,
        )
        endpoints = re.findall(r'"GET (/api/v1/[^ ?"]+)', logs.stdout + logs.stderr)
        result['visitas'].append({'ruta': path, 'visita': visit, 'peticiones': len(endpoints), 'endpoints': endpoints})
print(json.dumps(result, indent=2, ensure_ascii=False))

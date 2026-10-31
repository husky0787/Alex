"""Populate only the owned local showcase PostgreSQL with real provider data."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from market_data.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/showcase'


if __name__ == '__main__':
    config = json.loads((STATE / 'market-private.json').read_text(encoding='utf-8'))
    parsed = urlparse(config['dsn'])
    if parsed.hostname != '127.0.0.1' or parsed.port != 55441 or parsed.username != 'alex_showcase':
        raise RuntimeError('Unexpected showcase market database')
    os.environ['MARKET_DATABASE_URL'] = config['dsn']
    raise SystemExit(main(['--env-file', str(ROOT / '.env'), 'backfill',
                           '--raw-dir', str(STATE / 'market-data'),
                           '--evidence', str(STATE / 'market-backfill-private.json')]))

"""Acceptance-only SQL probe, streamed into the disposable API Pod by smoke.py.

Destructive gap injection is restricted to the local fixture database, with an
explicit command. This file is not included in the application image.
"""
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from urllib.parse import urlsplit

import psycopg

from market_data.calendar import latest_published_session, sessions
from market_data.executions import ExecutionRepository
from market_data.repository import PriceRepository


assert os.environ.get('AWS_ENDPOINT_URL_RDS_DATA') == 'http://fixtures:8081'
dsn = os.environ['MARKET_DATABASE_URL']
assert urlsplit(dsn).hostname == 'postgres' and urlsplit(dsn).path == '/alex'
now = datetime.now(timezone.utc)
end = latest_published_session(now)
start = end - timedelta(days=6)
with psycopg.connect(dsn,autocommit=True) as connection:
    prices = PriceRepository(connection)
    executions = ExecutionRepository(prices)
    if sys.argv[1] == 'gap':
        day = end if sys.argv[2] == 'latest' else sessions(start,end)[-2]
        with connection.transaction():
            connection.execute('DELETE FROM market_observations WHERE price_id IN '
                               '(SELECT id FROM daily_prices WHERE symbol=%s AND trade_date=%s)',('AAPL',day))
            connection.execute('DELETE FROM daily_prices WHERE symbol=%s AND trade_date=%s',('AAPL',day))
        print(json.dumps({'date':str(day)}))
    else:
        print(json.dumps({'start':str(start),'end':str(end),'health':executions.health(now),
                          'executions':executions.recent(),'alerts':executions.alerts(),
                          'price_count':connection.execute('SELECT count(*) FROM daily_prices').fetchone()[0],
                          'observation_count':connection.execute('SELECT count(*) FROM market_observations').fetchone()[0]}))

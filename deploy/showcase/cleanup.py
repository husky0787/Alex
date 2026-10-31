"""Export/check task-owned data; remove only the marked showcase database/login.

Run archive before Terraform cleanup. Run database only after stopping the API
and destroying terraform/11_showcase. Research resources are cleaned through
their separately reviewed Terraform destroy plans, never by account-wide delete.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse, unquote

from environment import STATE, aws, read, save, sql


def ownership():
    target, ledger = read('admin-target-private.json'), read('database-ledger-private.json')
    if ledger['database'] != 'alex_task11' or ledger['role'] != 'alex_task11_app':
        raise RuntimeError('Unexpected cleanup target')
    rows = sql(target, "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='alex_task11'")['records']
    roles = sql(target, "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname='alex_task11_app'")['records']
    if not rows or not roles or rows[0][0].get('stringValue') != ledger['marker'] or roles[0][0].get('stringValue') != ledger['marker']:
        raise RuntimeError('Database/role ownership marker differs; no cleanup permitted')
    return target, ledger


def archive():
    target, ledger = ownership()
    records = {}
    for table in ('users', 'instruments', 'accounts', 'positions', 'jobs'):
        result = sql(target, f'SELECT row_to_json(t)::text FROM {table} t', database='alex_task11')
        records[table] = [json.loads(row[0]['stringValue']) for row in result['records']]
    save('application-archive-private.json', records)
    market = read('market-private.json')
    parsed = urlparse(market['dsn'])
    if parsed.hostname != '127.0.0.1' or parsed.port != 55441 or parsed.username != 'alex_showcase':
        raise RuntimeError('Unexpected market archive source')
    environment = {**os.environ, 'PGPASSWORD': unquote(parsed.password)}
    suffix = '.exe' if os.name == 'nt' else ''
    subprocess.run([str(Path(market['pg_bin']) / ('pg_dump' + suffix)), '-h', '127.0.0.1', '-p', '55441',
                    '-U', 'alex_showcase', '-d', 'postgres', '--format=custom', '--file', str(STATE / 'market-database.dump')],
                   env=environment, check=True, capture_output=True)
    save('archive-receipt-private.json', {'at': datetime.now(timezone.utc).isoformat(), 'marker': ledger['marker'],
                                         'table_counts': {name: len(rows) for name, rows in records.items()}})
    print('Application and market archives saved privately.')


def database():
    target, ledger = read('admin-target-private.json'), read('database-ledger-private.json')
    if ledger['database'] != 'alex_task11' or ledger['role'] != 'alex_task11_app' or target['database'] == 'alex_task11':
        raise RuntimeError('Unexpected cleanup target')
    if read('archive-receipt-private.json')['marker'] != ledger['marker']:
        raise RuntimeError('Matching archive is required before cleanup')
    # Inspect each remaining object on every invocation. A failed DROP ROLE or
    # secret deletion can be resumed after DROP DATABASE without losing checks.
    rows = sql(target, "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='alex_task11'")['records']
    roles = sql(target, "SELECT shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname='alex_task11_app'")['records']
    for records in (rows, roles):
        if records and records[0][0].get('stringValue') != ledger['marker']:
            raise RuntimeError('Remaining database/role ownership marker differs')
    functions = aws('lambda', 'list-functions')['Functions']
    if any(item['FunctionName'].startswith('alex-task11-') for item in functions):
        raise RuntimeError('Destroy the dedicated workers before database cleanup')
    secret = aws('secretsmanager', 'describe-secret', SecretId=ledger['secret_arn'])
    if {item['Key']: item['Value'] for item in secret.get('Tags', [])}.get('OwnerToken') != ledger['marker']:
        raise RuntimeError('Secret ownership marker differs')
    if rows:
        sql(target, 'DROP DATABASE alex_task11 WITH (FORCE)')
    if roles:
        sql(target, 'DROP ROLE alex_task11_app')
    if not secret.get('DeletedDate'):
        aws('secretsmanager', 'delete-secret', SecretId=ledger['secret_arn'], RecoveryWindowInDays=7)
    if sql(target, "SELECT datname FROM pg_database WHERE datname='alex_task11'")['records']:
        raise RuntimeError('Showcase database still exists after cleanup')
    if not sql(target, "SELECT datname FROM pg_database WHERE datname=:database",
               parameters=[{'name': 'database', 'value': {'stringValue': target['database']}}])['records']:
        raise RuntimeError('Original database missing during final verification')
    current = {item['FunctionName']: item for item in functions}
    for original in read('preflight-private.json')['original_functions']:
        item = current.get(original['FunctionName'])
        if not item or any(item[key] != original[key] for key in ('LastModified', 'CodeSha256')):
            raise RuntimeError('Original Lambda inventory differs; inspect before reporting cleanup complete')
    save('database-cleanup-private.json', {'at': datetime.now(timezone.utc).isoformat(),
         'database_removed': True, 'original_database_preserved': True,
         'original_functions_unchanged': len(read('preflight-private.json')['original_functions']), 'secret_recovery_days': 7})
    print('Owned database/login removed; secret scheduled for recovery deletion; originals verified.')


def market():
    config = read('market-private.json')
    expected = (STATE / 'postgres/data').resolve()
    if Path(config['data_directory']).resolve() != expected:
        raise RuntimeError('Unexpected PostgreSQL cleanup directory')
    if not (STATE / 'market-database.dump').is_file():
        raise RuntimeError('Market archive required before stopping the demo database')
    suffix = '.exe' if os.name == 'nt' else ''
    subprocess.run([str(Path(config['pg_bin']) / ('pg_ctl' + suffix)), '-D', str(expected),
                    '-m', 'fast', '-w', 'stop'], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['archive', 'database', 'market'])
    args = parser.parse_args()
    {'archive': archive, 'database': database, 'market': market}[args.action]()

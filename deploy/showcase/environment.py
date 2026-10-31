"""Prepare an isolated showcase; private state is never a publishable artifact.

Run with the backend API uv project and --with sqlparse. Cloud initialization
requires reviewed plans and the budget/ownership boundary in task-11-cloud-window.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/showcase'
sys.path.insert(0, str(ROOT / 'deploy/eks'))
from manage import aws


def save(name, value):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / name).write_text(json.dumps(value, indent=2), encoding='utf-8')


def read(name):
    return json.loads((STATE / name).read_text(encoding='utf-8'))


def sql(target, statement, *, database=None, parameters=None):
    args = dict(resourceArn=target['cluster'], secretArn=target['secret'],
                database=database or target['database'], sql=statement, includeResultMetadata=True)
    if parameters:
        args['parameters'] = parameters
    # Retry only a service-reported resume rejection, not ambiguous execution.
    for attempt in range(3):
        try:
            return aws('rds-data', 'execute-statement', **args)
        except RuntimeError as exc:
            if 'DatabaseResumingException' not in str(exc) or attempt == 2:
                raise
            time.sleep(20)


def preflight(target_path):
    target = json.loads(target_path.read_text(encoding='utf-8-sig'))
    target['database'] = target.get('database') or 'alex'
    existing = sql(target, "SELECT datname FROM pg_database WHERE datname='alex_task11'")
    if existing.get('records'):
        raise RuntimeError('alex_task11 already exists; inspect ownership before any changes')
    functions = aws('lambda', 'list-functions')['Functions']
    if any(item['FunctionName'].startswith('alex-task11-') for item in functions):
        raise RuntimeError('Showcase functions already exist; inspect state before creating resources')
    profile = aws('bedrock', 'get-inference-profile', inferenceProfileIdentifier='us.amazon.nova-pro-v1:0')
    inventory = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'original_functions': [{k: item[k] for k in ('FunctionName', 'LastModified', 'CodeSha256')} for item in functions],
        'sagemaker': aws('sagemaker', 'list-endpoints')['Endpoints'],
        'vector_buckets': aws('s3vectors', 'list-vector-buckets').get('vectorBuckets', []),
        'credit': aws('freetier', 'get-account-plan-state'),
        'bedrock_arns': [profile['inferenceProfileArn']] + [item['modelArn'] for item in profile['models']],
    }
    save('preflight-private.json', inventory)
    save('admin-target-private.json', target)
    print('Preflight saved privately; owned database/functions absent. Review inventory before apply.')


def initialize_database():
    import sqlparse
    target = read('admin-target-private.json')
    ledger_path = STATE / 'database-ledger-private.json'
    if ledger_path.exists():
        raise RuntimeError('Initialization ledger exists; inspect partial or completed setup, do not reset')
    if sql(target, "SELECT datname FROM pg_database WHERE datname='alex_task11'").get('records'):
        raise RuntimeError('Database exists; refusing to overwrite it')
    if sql(target, "SELECT rolname FROM pg_roles WHERE rolname='alex_task11_app'").get('records'):
        raise RuntimeError('Role exists; refusing to overwrite it')
    marker = 'alex-task11-showcase-' + secrets.token_hex(12)
    password = secrets.token_urlsafe(32)
    ledger = {'marker': marker, 'database': 'alex_task11', 'role': 'alex_task11_app', 'stage': 'starting'}
    save(ledger_path.name, ledger)
    sql(target, f"CREATE ROLE alex_task11_app LOGIN PASSWORD '{password}'")
    sql(target, f"COMMENT ON ROLE alex_task11_app IS '{marker}'")
    ledger['stage'] = 'role_created'; save(ledger_path.name, ledger)
    sql(target, 'CREATE DATABASE alex_task11')
    sql(target, f"COMMENT ON DATABASE alex_task11 IS '{marker}'")
    sql(target, 'REVOKE CONNECT ON DATABASE alex_task11 FROM PUBLIC')
    sql(target, 'GRANT CONNECT ON DATABASE alex_task11 TO alex_task11_app')
    ledger['stage'] = 'database_created'; save(ledger_path.name, ledger)
    for statement in sqlparse.split((ROOT / 'backend/database/migrations/001_schema.sql').read_text(encoding='utf-8')):
        sql(target, statement, database='alex_task11')
    for statement in ('REVOKE CREATE ON SCHEMA public FROM PUBLIC',
                      'GRANT USAGE ON SCHEMA public TO alex_task11_app',
                      'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO alex_task11_app',
                      'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO alex_task11_app'):
        sql(target, statement, database='alex_task11')
    from market_data.universe import universe_metadata
    for item in universe_metadata()['symbols']:
        sql(target, 'INSERT INTO instruments(symbol,name,instrument_type) VALUES(:symbol,:name,:kind)',
            database='alex_task11', parameters=[{'name': k, 'value': {'stringValue': item[k]}} for k in ('symbol', 'name', 'kind')])
    secret = aws('secretsmanager', 'create-secret', Name='alex-task11/database',
                 SecretString=json.dumps({'username': 'alex_task11_app', 'password': password}),
                 Tags=[{'Key': 'Project', 'Value': 'alex'}, {'Key': 'Purpose', 'Value': 'task-11-showcase'},
                       {'Key': 'OwnerToken', 'Value': marker}])
    ledger.update(secret_arn=secret['ARN'], stage='initialized')
    save(ledger_path.name, ledger)
    save('application-target-private.json', {'cluster': target['cluster'], 'secret': secret['ARN'], 'database': 'alex_task11'})
    print('Isolated application database initialized; credentials remain in Secrets Manager.')


def initialize_market(pg_bin):
    root = STATE / 'postgres'
    if root.exists():
        raise RuntimeError('Showcase PostgreSQL directory exists; refusing to initialize over it')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 55441))
    root.mkdir(parents=True)
    password = secrets.token_urlsafe(24)
    password_file = root / 'initial-password-private.txt'
    password_file.write_text(password, encoding='utf-8')
    suffix = '.exe' if os.name == 'nt' else ''
    with (root / 'initialize-private.log').open('w', encoding='utf-8') as log:
        try:
            subprocess.run([str(pg_bin / ('initdb' + suffix)), '-D', str(root / 'data'), '-U', 'alex_showcase',
                            '--auth-host=scram-sha-256', '--auth-local=trust', '--pwfile', str(password_file),
                            '--no-locale', '--encoding=UTF8'], check=True, stdout=log, stderr=log)
        finally:
            password_file.unlink(missing_ok=True)
        subprocess.run([str(pg_bin / ('pg_ctl' + suffix)), '-D', str(root / 'data'), '-l', str(root / 'server-private.log'),
                        '-o', '-h 127.0.0.1 -p 55441', '-w', 'start'], check=True, stdout=log, stderr=log)
    dsn = f'postgresql://alex_showcase:{password}@127.0.0.1:55441/postgres'
    save('market-private.json', {'dsn': dsn, 'pg_bin': str(pg_bin), 'data_directory': str(root / 'data')})
    import psycopg
    from market_data.repository import PriceRepository
    with psycopg.connect(dsn, autocommit=True) as connection:
        PriceRepository(connection).migrate()
    print('Owned loopback PostgreSQL initialized and migrated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'database', 'market'])
    parser.add_argument('--admin-target', type=Path)
    parser.add_argument('--pg-bin', type=Path)
    args = parser.parse_args()
    if args.action == 'preflight':
        if not args.admin_target:
            parser.error('--admin-target is required')
        preflight(args.admin_target)
    elif args.action == 'database':
        initialize_database()
    else:
        if not args.pg_bin:
            parser.error('--pg-bin is required')
        initialize_market(args.pg_bin)

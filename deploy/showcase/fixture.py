"""Seed a clearly labelled sample portfolio only in the owned showcase database."""
from decimal import Decimal
import json
from pathlib import Path

import boto3
from botocore.config import Config
from src import Database

STATE = Path(__file__).resolve().parents[2] / '.local/showcase'


def seed():
    target = json.loads((STATE / 'application-target-private.json').read_text(encoding='utf-8'))
    ledger = json.loads((STATE / 'database-ledger-private.json').read_text(encoding='utf-8'))
    if target['database'] != 'alex_task11' or target['secret'] != ledger['secret_arn'] or ledger['stage'] != 'initialized':
        raise RuntimeError('Showcase database ownership/configuration mismatch')
    path = STATE / 'fixture-private.json'
    if path.exists():
        raise RuntimeError('Fixture ledger exists; reuse it rather than creating more sample data')
    database = Database(cluster_arn=target['cluster'], secret_arn=target['secret'], database='alex_task11')
    users = database.users.find_all()
    if len(users) != 1:
        raise RuntimeError('Exactly one real Clerk-authenticated showcase user must exist before seeding')
    user_id = users[0]['clerk_user_id']
    if database.accounts.find_by_user(user_id):
        raise RuntimeError('User already has showcase accounts; do not overwrite their work')
    record = {'user_id': user_id, 'stage': 'starting'}
    path.write_text(json.dumps(record), encoding='utf-8')
    account = database.accounts.create_account(user_id, 'Showcase portfolio (sample)',
                                               'Fictional holdings for engineering acceptance', Decimal('1000'))
    record.update(account_id=account, stage='account_created')
    path.write_text(json.dumps(record), encoding='utf-8')
    for symbol, quantity in [('AAPL', '1'), ('MSFT', '2')]:
        database.positions.add_position(account, symbol, Decimal(quantity))
    record['stage'] = 'positions_created'
    path.write_text(json.dumps(record), encoding='utf-8')
    client = boto3.client('lambda', region_name='us-east-1', config=Config(read_timeout=330, retries={'total_max_attempts': 1}))
    response = client.invoke(FunctionName='alex-task11-tagger', InvocationType='RequestResponse',
                             Payload=json.dumps({'instruments': [{'symbol': 'AAPL', 'name': 'Apple Inc.'},
                                                                 {'symbol': 'MSFT', 'name': 'Microsoft Corporation'}]}).encode())
    result = json.loads(response['Payload'].read())
    (STATE / 'tagger-private.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if response.get('FunctionError') or result.get('statusCode') != 200:
        raise RuntimeError('Tagger failed; inspect saved result before any further paid attempt')
    for symbol in ('AAPL', 'MSFT'):
        instrument = database.instruments.find_by_symbol(symbol)
        if not all(instrument.get(field) for field in ('allocation_regions', 'allocation_sectors', 'allocation_asset_class')):
            raise RuntimeError('Tagger did not persist complete allocations')
    record['stage'] = 'ready'
    path.write_text(json.dumps(record, indent=2), encoding='utf-8')
    print('Sample portfolio created in the isolated database; real Tagger classification persisted.')


if __name__ == '__main__':
    seed()

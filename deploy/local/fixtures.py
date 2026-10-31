"""Local-only JWKS, RDS Data API SQL bridge and recording queue; never deploy to AWS.

Runs the real schema on PostgreSQL. Only ExecuteStatement and SendMessage are
implemented; unsupported operations fail rather than pretending to succeed.
"""
import hashlib
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request, HTTPException


def connect():
    return psycopg.connect(os.environ['FIXTURE_DATABASE_URL'], autocommit=True, connect_timeout=2)


@asynccontextmanager
async def lifespan(app):
    with connect() as connection:
        if connection.execute("SELECT to_regclass('public.users')").fetchone()[0] is None:
            connection.execute(Path('/fixtures/schema.sql').read_text())
        connection.execute("CREATE TABLE IF NOT EXISTS local_queue (id uuid PRIMARY KEY, body text NOT NULL)")
    yield


app = FastAPI(lifespan=lifespan)


@app.get('/.well-known/jwks.json')
def jwks():
    return json.loads(Path('/keys/jwks.json').read_text())


@app.get('/health')
def health():
    with connect() as connection:
        connection.execute('SELECT 1')
    return {'status': 'ready'}


def field(value):
    if value is None:
        return {'isNull': True}
    if isinstance(value, bool):
        return {'booleanValue': value}
    if isinstance(value, int):
        return {'longValue': value}
    if isinstance(value, float):
        return {'doubleValue': value}
    if isinstance(value, (dict, list)):
        return {'stringValue': json.dumps(value)}
    if isinstance(value, (datetime, date)):
        return {'stringValue': value.isoformat()}
    if isinstance(value, (str, Decimal, UUID)):
        return {'stringValue': str(value)}
    raise TypeError(f'Unsupported PostgreSQL result type: {type(value).__name__}')


@app.post('/Execute')
async def execute(request: Request):
    body = await request.json()
    if body.get('transactionId'):
        raise HTTPException(501, 'Transactions are outside the local bridge contract')
    values = {}
    for param in body.get('parameters', []):
        value = param['value']
        values[param['name']] = None if value.get('isNull') else next(iter(value.values()))
    # Named parameters only; preserve PostgreSQL :: casts and never interpolate values.
    sql = re.sub(r'(?<!:):([A-Za-z_][A-Za-z0-9_]*)', r'%(\1)s', body['sql'])
    with connect() as connection:
        cursor = connection.execute(sql, values or None)
        result = {'numberOfRecordsUpdated': max(cursor.rowcount, 0)}
        if cursor.description:
            result['columnMetadata'] = [{'name': col.name} for col in cursor.description]
            result['records'] = [[field(value) for value in row] for row in cursor.fetchall()]
        return result


@app.post('/')
async def queue(request: Request):
    if request.headers.get('x-amz-target') != 'AmazonSQS.SendMessage':
        raise HTTPException(501, 'Only SendMessage is supported')
    body = await request.json()
    if body['QueueUrl'] != 'http://fixtures:8081/queue/alex':
        raise HTTPException(400, 'Unexpected local queue')
    message_id = str(uuid4())
    with connect() as connection:
        connection.execute('INSERT INTO local_queue VALUES (%s, %s)', (message_id, body['MessageBody']))
    return {'MessageId': message_id, 'MD5OfMessageBody': hashlib.md5(body['MessageBody'].encode(), usedforsecurity=False).hexdigest()}

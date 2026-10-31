"""Initialize ONLY the separately owned alex_task09 database and login roles.

Executed once as the bootstrap ServiceAccount with existing admin-secret access.
It does not modify the existing alex database or any existing account records.
"""
import json
import os
import time
from pathlib import Path

import boto3
import psycopg
from psycopg import sql

from market_data.repository import PriceRepository
from market_data.universe import universe_metadata
from market_data.cloud import safe_error

STAGE='load_secrets'


def connect_ready(**kwargs):
    # Retry connection establishment only: never replay CREATE DATABASE/ROLE.
    for attempt in range(1,4):
        try:
            return psycopg.connect(**kwargs)
        except psycopg.OperationalError as exc:
            if exc.sqlstate not in (None,'57P03') or attempt==3:
                raise
            print(json.dumps({'event':'database_connect_retry','attempt':attempt,**safe_error(exc)}),flush=True)
            time.sleep(2)


def main():
    client=boto3.client('secretsmanager')
    def secret(name):
        return json.loads(client.get_secret_value(SecretId=os.environ[name])['SecretString'])
    admin, api, etl = (secret(name) for name in ('ADMIN_SECRET_ARN','API_SECRET_ARN','ETL_SECRET_ARN'))
    connection_args=dict(host=api['host'],user=admin['username'],password=admin['password'],
                         sslmode='verify-full',sslrootcert='/app/rds-ca.pem',connect_timeout=30,autocommit=True)
    initialize(connection_args,api,etl,Path('/app/application-schema.sql'))
    print(json.dumps({'database':'alex_task09','status':'initialized'}))


def initialize(connection_args,api,etl,schema_path):
    global STAGE
    STAGE='validate_identifiers'
    if api['dbname']!= 'alex_task09' or etl['dbname']!='alex_task09':
        raise ValueError('Unexpected acceptance database')
    if api['username']!='alex_task09_api' or etl['username']!='alex_task09_etl':
        raise ValueError('Unexpected acceptance roles')
    STAGE='create_isolated_database_and_roles'
    with connect_ready(dbname='postgres',**connection_args) as connection:
        # Existing database means initialization already happened; fail for operator
        # inspection rather than resetting a possibly populated database.
        if connection.execute("SELECT 1 FROM pg_database WHERE datname='alex_task09'").fetchone():
            raise ValueError('Acceptance database already exists; inspect before reinitializing')
        for value in (api,etl):
            connection.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
                sql.Identifier(value['username']),sql.Literal(value['password'])))
            connection.execute(sql.SQL("COMMENT ON ROLE {} IS 'alex-task09 acceptance only'").format(sql.Identifier(value['username'])))
        connection.execute('CREATE DATABASE alex_task09')
        connection.execute("COMMENT ON DATABASE alex_task09 IS 'alex-task09 acceptance only'")
        connection.execute('REVOKE CONNECT ON DATABASE alex_task09 FROM PUBLIC')
        connection.execute('GRANT CONNECT ON DATABASE alex_task09 TO alex_task09_api, alex_task09_etl')
    STAGE='initialize_application_schema'
    with connect_ready(dbname='alex_task09',**connection_args) as connection:
        connection.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
        connection.execute('GRANT USAGE, CREATE ON SCHEMA public TO alex_task09_api, alex_task09_etl')
        connection.execute(schema_path.read_text())
        connection.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO alex_task09_api')
        connection.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO alex_task09_api')
        for instrument in universe_metadata()['symbols']:
            connection.execute('INSERT INTO instruments(symbol,name,instrument_type) VALUES (%s,%s,%s)',
                               (instrument['symbol'],instrument['name'],instrument['kind']))
        # RDS administrators have CREATEROLE, not PostgreSQL superuser status.
        # Temporarily grant membership so SET ROLE and owner grants work on RDS.
        membership=sql.SQL('GRANT alex_task09_etl TO {}').format(sql.Identifier(connection.info.user))
        revoke=sql.SQL('REVOKE alex_task09_etl FROM {}').format(sql.Identifier(connection.info.user))
        connection.execute(membership)
        try:
            connection.execute('SET ROLE alex_task09_etl')
            STAGE='migrate_market_schema'
            PriceRepository(connection).migrate()
            connection.execute('ALTER DEFAULT PRIVILEGES FOR ROLE alex_task09_etl IN SCHEMA public GRANT SELECT ON TABLES TO alex_task09_api')
            connection.execute('RESET ROLE')
            connection.execute('GRANT SELECT ON ALL TABLES IN SCHEMA public TO alex_task09_api')
        finally:
            connection.execute('RESET ROLE')
            connection.execute(revoke)
        connection.execute('REVOKE CREATE ON SCHEMA public FROM alex_task09_api')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'failed','stage':STAGE,**safe_error(exc)}))
        raise SystemExit(1) from None

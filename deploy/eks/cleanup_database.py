"""Drop only the explicitly marked task09 acceptance database and login roles."""
import json
import os

import boto3
import psycopg

from market_data.cloud import safe_error


def main():
    client=boto3.client('secretsmanager')
    def secret(name):
        return json.loads(client.get_secret_value(SecretId=os.environ[name])['SecretString'])
    admin=secret('ADMIN_SECRET_ARN')
    workload=secret('API_SECRET_ARN')
    if workload['dbname']!='alex_task09':
        raise ValueError('Unexpected database; refusing cleanup')
    with psycopg.connect(host=workload['host'],user=admin['username'],password=admin['password'],
                         dbname='postgres',sslmode='verify-full',sslrootcert='/app/rds-ca.pem',
                         connect_timeout=15,autocommit=True) as connection:
        marker=connection.execute("SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname='alex_task09'").fetchone()
        if marker != ('alex-task09 acceptance only',):
            raise ValueError('Database ownership marker missing; refusing cleanup')
        roles=connection.execute("SELECT rolname,shobj_description(oid,'pg_authid') FROM pg_roles WHERE rolname IN ('alex_task09_api','alex_task09_etl') ORDER BY rolname").fetchall()
        if roles != [('alex_task09_api','alex-task09 acceptance only'),('alex_task09_etl','alex-task09 acceptance only')]:
            raise ValueError('Role ownership markers missing; refusing cleanup')
        connection.execute('DROP DATABASE alex_task09 WITH (FORCE)')
        connection.execute('DROP ROLE alex_task09_api, alex_task09_etl')
    print(json.dumps({'database':'alex_task09','status':'deleted_marked_acceptance_data'}))


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'cleanup_failed',**safe_error(exc)}))
        raise SystemExit(1) from None

"""EKS process entry: Secrets Manager via workload identity, verified TLS to RDS.

No credentials are accepted in arguments or copied into Kubernetes manifests.
The API and ETL ServiceAccounts can read only their own secret.
"""
import argparse
import json
import os
import sys
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError

from . import scheduled


def safe_error(exc):
    """Preserve actionable codes without SQL, provider bodies or credentials."""
    value={'error_code':type(exc).__name__}
    if isinstance(exc,ClientError):
        value['aws_error_code']=exc.response.get('Error',{}).get('Code')
    if getattr(exc,'sqlstate',None):
        value['sqlstate']=exc.sqlstate
    return value


def load_database_environment(secret, *, environ=None):
    environ = os.environ if environ is None else environ
    required = ('username', 'password', 'host', 'dbname')
    if not all(isinstance(secret.get(key), str) and secret[key] for key in required):
        raise ValueError('Database secret lacks required fields')
    # Use connection keywords/URI encoding so punctuation never becomes a DSN option.
    environ['MARKET_DATABASE_URL'] = (
        f"postgresql://{quote(secret['username'],safe='')}:{quote(secret['password'],safe='')}"
        f"@{secret['host']}:5432/{quote(secret['dbname'],safe='')}"
        '?sslmode=verify-full&sslrootcert=/app/rds-ca.pem'
    )
    if secret.get('MASSIVE_API_KEY'):
        environ['MASSIVE_API_KEY'] = secret['MASSIVE_API_KEY']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['api','daily','backfill','monitor','migrate'])
    args, rest = parser.parse_known_args(argv)
    try:
        response = boto3.client('secretsmanager').get_secret_value(SecretId=os.environ['WORKLOAD_SECRET_ARN'])
        load_database_environment(json.loads(response['SecretString']))
        if args.mode == 'api':
            os.execv(sys.executable,[sys.executable,'-m','uvicorn','main:app','--host','0.0.0.0','--port','8000'])
        if args.mode == 'migrate':
            from .__main__ import main as migrate
            return migrate(['migrate'])
        code = scheduled.main([args.mode,*rest])
        if code:
            boto3.client('sns').publish(TopicArn=os.environ['ALERT_TOPIC_ARN'],
                Message=json.dumps({'event':'market_etl_failed','mode':args.mode,
                                    'pod':os.environ.get('POD_NAME'),'exit_code':code}))
        return code
    except Exception as exc:
        # Never log provider bodies, credentials or secret values.
        print(json.dumps({'event':'cloud_entry_failed',**safe_error(exc)}),flush=True)
        if args.mode in ('daily','backfill','monitor') and os.environ.get('ALERT_TOPIC_ARN'):
            try:
                boto3.client('sns').publish(TopicArn=os.environ['ALERT_TOPIC_ARN'],
                    Message=json.dumps({'event':'market_etl_failed','mode':args.mode,
                        'pod':os.environ.get('POD_NAME'),**safe_error(exc),'exit_code':1}))
            except Exception as alert_error:
                print(json.dumps({'event':'alert_delivery_failed',**safe_error(alert_error)}),flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    raise SystemExit(main())

"""Run inside an acceptance Pod to check real role boundaries and bad-data storage.

Invoke with api or etl. The malformed-source probe cannot publish valid prices.
"""
import json
import os
import sys
from datetime import datetime,timezone

import boto3
from botocore.exceptions import ClientError
import httpx
import psycopg

from market_data.cloud import load_database_environment
from market_data.calendar import latest_published_session
from market_data.pipeline import DailyPricePipeline
from market_data.repository import PriceRepository
from market_data.storage import S3RawStore


def denied(call):
    try:
        call()
    except ClientError as exc:
        assert exc.response['Error']['Code'] in ('AccessDenied','AccessDeniedException'), exc.response['Error']['Code']
        return True
    raise AssertionError('Workload unexpectedly received forbidden access')


def main():
    mode=sys.argv[1]
    sm=boto3.client('secretsmanager')
    secret=json.loads(sm.get_secret_value(SecretId=os.environ['WORKLOAD_SECRET_ARN'])['SecretString'])
    load_database_environment(secret)
    result={'role':mode,'identity':boto3.client('sts').get_caller_identity()['Arn']}
    result['admin_secret_denied']=denied(lambda:sm.get_secret_value(SecretId=os.environ['TEST_ADMIN_SECRET_ARN']))
    result['other_workload_secret_denied']=denied(lambda:sm.get_secret_value(SecretId=os.environ['TEST_OTHER_SECRET_ARN']))
    bucket=os.environ['TEST_BUCKET']
    s3=boto3.client('s3')
    if mode=='api':
        result['raw_write_denied']=denied(lambda:s3.put_object(Bucket=bucket,Key='raw/forbidden.json',Body=b'{}'))
    else:
        result['outside_prefix_write_denied']=denied(lambda:s3.put_object(Bucket=bucket,Key='forbidden.json',Body=b'{}'))
        class InvalidSource:
            def fetch(self,*args):
                return httpx.Response(200,json={'task09_fault_injection':True,'status':'OK','ticker':'AAPL','results':[{'c':-1}]})
        with psycopg.connect(os.environ['MARKET_DATABASE_URL'],autocommit=True) as connection:
            before=connection.execute('SELECT count(*) FROM daily_prices').fetchone()[0]
            day=latest_published_session(datetime.now(timezone.utc))
            run=DailyPricePipeline(InvalidSource(),S3RawStore(bucket,s3),PriceRepository(connection)).run('AAPL',day,day)
            after=connection.execute('SELECT count(*) FROM daily_prices').fetchone()[0]
            assert run['status']!='succeeded' and before==after
            result.update(quarantine_run=run,verified_prices_unchanged=True)
    print(json.dumps(result))


if __name__=='__main__':
    main()

"""Isolated SQS-to-Reporter adapter, added to the verified Reporter ZIP.

This acceptance worker intentionally exercises the existing research-unavailable
path; it does not claim to restore all five production agents.
"""
import json
from uuid import UUID

from lambda_handler import lambda_handler as report
from src import Database


def lambda_handler(event, context):
    failures=[]
    for record in event['Records']:
        try:
            # /api/analyze and the existing Planner use a plain UUID body.
            job_id=str(UUID(record['body']))
            result=report({'job_id':job_id},context)
            if result.get('statusCode') != 200:
                raise RuntimeError('Reporter failed')
            payload=json.loads(result['body']) if isinstance(result['body'],str) else result['body']
            if not payload.get('success'):
                raise RuntimeError('Reporter did not save a report')
            Database().client.execute(
                "UPDATE jobs SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=CAST(:id AS UUID)",
                [{'name':'id','value':{'stringValue':job_id}}])
        except Exception as exc:
            print(json.dumps({'event':'analysis_failed','error_code':type(exc).__name__,
                              'message_id':record['messageId']}))
            failures.append({'itemIdentifier':record['messageId']})
    return {'batchItemFailures':failures}

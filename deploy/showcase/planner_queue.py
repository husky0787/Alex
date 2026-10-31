"""Bounded showcase queue adapter; validate persisted outputs, not transport 200."""
import json
from uuid import UUID

from lambda_handler import lambda_handler as planner
from src import Database
from src.snapshots import load_snapshot


def check_outputs(database, job_id):
    snapshot = load_snapshot(database, job_id)
    positions = sum(len(account['positions']) for account in snapshot['accounts'])
    job = database.jobs.find_by_id(job_id)
    required = []
    if positions:
        required.append('report_payload')
    if positions >= 2:
        required.append('charts_payload')
    if snapshot['user_preferences'].get('years_until_retirement'):
        required.append('retirement_payload')
    if job['status'] != 'completed' or any(not job.get(field) for field in required):
        raise RuntimeError('Planner did not persist every required output')


def lambda_handler(event, context):
    failures = []
    for record in event['Records']:
        job_id = None
        try:
            job_id = str(UUID(record['body']))
            result = planner({'job_id': job_id}, context)
            body = json.loads(result['body']) if isinstance(result.get('body'), str) else result.get('body', {})
            if result.get('statusCode') != 200 or not body.get('success'):
                raise RuntimeError('Planner returned a failed application result')
            check_outputs(Database(), job_id)
        except Exception as exc:
            if job_id:
                Database().jobs.update_status(job_id, 'failed', error_message='showcase_analysis_failed')
            print(json.dumps({'event': 'showcase_analysis_failed', 'error_type': type(exc).__name__,
                              'message_id': record['messageId']}))
            failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': failures}

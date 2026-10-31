"""Read back actual showcase jobs and validate persisted evidence end to end."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from src import Database
from src.snapshots import load_snapshot

STATE = Path(__file__).resolve().parents[2] / '.local/showcase'


def verify():
    target = json.loads((STATE / 'application-target-private.json').read_text(encoding='utf-8'))
    if target['database'] != 'alex_task11':
        raise RuntimeError('Unexpected application database')
    database = Database(cluster_arn=target['cluster'], secret_arn=target['secret'], database='alex_task11')
    jobs = database.jobs.find_all()
    (STATE / 'analysis-jobs-private.json').write_text(json.dumps(jobs, indent=2, default=str), encoding='utf-8')
    summary = {'at': datetime.now(timezone.utc).isoformat(), 'jobs': len(jobs), 'states': [job['status'] for job in jobs]}
    if not jobs or any(job['status'] in ('pending', 'running') for job in jobs):
        print(json.dumps(summary))
        raise RuntimeError('Analysis is not complete; no acceptance success may be recorded')
    completed = [job for job in jobs if job['status'] == 'completed']
    if not completed:
        print(json.dumps(summary))
        raise RuntimeError('No completed analysis; private read-back retained for diagnosis')
    job = max(completed, key=lambda item: str(item['created_at']))
    snapshot = load_snapshot(database, job['id'])
    expected = json.loads((STATE / 'research-private.json').read_text(encoding='utf-8'))['retrieved']
    for field in ('report_payload', 'retirement_payload'):
        payload = job.get(field)
        if not payload or payload.get('price_snapshot_sha256') != snapshot['sha256']:
            raise RuntimeError(f'{field} did not use the job price snapshot')
    # Charter stores a map of charts, without a top-level digest field. Check
    # its persisted holding values against the job snapshot instead of inventing
    # a payload contract or rerunning a paid model to satisfy the verifier.
    prices = {row['symbol']: Decimal(row['close']) for row in snapshot['prices']}
    expected_values = {}
    for account in snapshot['accounts']:
        for position in account['positions']:
            symbol = position['symbol']
            expected_values[symbol] = expected_values.get(symbol, Decimal(0)) + Decimal(position['quantity']) * prices[symbol]
    actual_values = {row['name']: Decimal(str(row['value']))
                     for row in job['charts_payload']['top_holdings']['data']}
    if actual_values != expected_values:
        raise RuntimeError('Persisted holding chart differs from frozen quantities/prices')
    research = job['report_payload']['research']
    if research['status'] != 'available':
        raise RuntimeError('Report has no attributed research')
    matched = next((item for item in research['results'] if item['id'] == expected['id']), None)
    if not matched or matched['metadata']['sources'] != expected['metadata']['sources']:
        raise RuntimeError('Report provenance differs from retrieved research')
    content = job['report_payload']['content']
    if any(price['trade_date'] not in content for price in snapshot['prices']):
        raise RuntimeError('Report omits a price trading date')
    summary.update(snapshot_consistent=True, chart_values_match_snapshot=True, research_provenance_preserved=True,
                   verified_symbols=sorted(price['symbol'] for price in snapshot['prices']),
                   price_dates=sorted({price['trade_date'] for price in snapshot['prices']}),
                   report_saved=True, charts_saved=True, retirement_saved=True,
                   created_at=str(job['created_at']), completed_at=str(job['completed_at']))
    (STATE / 'analysis-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary))


if __name__ == '__main__':
    verify()

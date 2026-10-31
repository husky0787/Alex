"""Archive only the acceptance window's named log groups and usage privately."""
from datetime import datetime, timezone
import json

from environment import STATE, aws, read, save


def archive():
    start = datetime.fromisoformat(read('preflight-private.json')['checked_at'])
    end = datetime.now(timezone.utc)
    groups = [f'/aws/lambda/alex-task11-{name}' for name in ('planner', 'tagger', 'reporter', 'charter', 'retirement')]
    groups += ['/aws/lambda/alex-ingest', '/aws/sagemaker/Endpoints/alex-embedding-endpoint']
    counts = {}
    for group in groups:
        events, token = [], None
        while True:
            args = {'logGroupName': group, 'startTime': int(start.timestamp() * 1000), 'endTime': int(end.timestamp() * 1000)}
            if token:
                args['nextToken'] = token
            response = aws('logs', 'filter-log-events', **args)
            events.extend(response.get('events', []))
            following = response.get('nextToken')
            if not following or following == token:
                break
            token = following
        save('logs-' + group.rsplit('/', 1)[-1] + '-private.json', events)
        counts[group] = len(events)
    # CloudWatch model totals are account/window observations, not task invoices.
    usage = []
    for metric in aws('cloudwatch', 'list-metrics', Namespace='AWS/Bedrock')['Metrics']:
        if metric['MetricName'] not in ('Invocations', 'InputTokenCount', 'OutputTokenCount'):
            continue
        if not any('nova-pro' in item['Value'] for item in metric.get('Dimensions', [])):
            continue
        result = aws('cloudwatch', 'get-metric-statistics', Namespace=metric['Namespace'],
                     MetricName=metric['MetricName'], Dimensions=metric['Dimensions'],
                     StartTime=start.isoformat(), EndTime=end.isoformat(), Period=60, Statistics=['Sum'])
        usage.append({'metric': metric, 'datapoints': result.get('Datapoints', [])})
    save('usage-window-private.json', {'from': start.isoformat(), 'to': end.isoformat(), 'observations': usage,
                                     'attribution': 'account/model window, may include other work; not a bill'})
    save('cloud-archive-private.json', {'from': start.isoformat(), 'to': end.isoformat(), 'log_events': counts})
    print(json.dumps({'archived_log_groups': len(counts), 'log_events': sum(counts.values()), 'usage_observations': len(usage)}))


if __name__ == '__main__':
    archive()

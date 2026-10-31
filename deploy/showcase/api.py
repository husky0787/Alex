"""Run the unchanged application with isolated showcase configuration.

Launch using the backend API uv project. Application logs and request evidence
stay private. The request ledger records route templates/status, never tokens,
query strings, user IDs, account IDs or response bodies.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/showcase'


def load(name):
    return json.loads((STATE / name).read_text(encoding='utf-8'))


def application():
    target = load('application-target-private.json')
    if target['database'] != 'alex_task11':
        raise RuntimeError('Refusing to run showcase against another application database')
    ledger = load('database-ledger-private.json')
    if ledger['stage'] != 'initialized' or target['secret'] != ledger['secret_arn']:
        raise RuntimeError('Application database ownership is not initialized')
    os.environ.update(
        PYTHON_DOTENV_DISABLED='1',
        AURORA_CLUSTER_ARN=target['cluster'], AURORA_SECRET_ARN=target['secret'],
        AURORA_DATABASE='alex_task11', DEFAULT_AWS_REGION='us-east-1',
        MARKET_DATABASE_URL=load('market-private.json')['dsn'],
        SQS_QUEUE_URL=load('deployment-private.json')['queue_url']['value'],
        CLERK_JWKS_URL=load('public-config.json')['clerk_jwks_url'],
        CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000',
    )
    sys.path.insert(0, str(ROOT / 'backend/api'))
    import main
    app = main.app
    if main.db.client.database != 'alex_task11' or main.db.client.secret_arn != target['secret']:
        raise RuntimeError('Application configuration escaped the isolated database')

    @app.middleware('http')
    async def record_request(request, call_next):
        response = await call_next(request)
        route = request.scope.get('route')
        entry = {'at': datetime.now(timezone.utc).isoformat(), 'method': request.method,
                 'route': getattr(route, 'path', 'unmatched'), 'status': response.status_code}
        with (STATE / 'http-evidence-private.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(entry) + '\n')
        return response

    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(application(), host='127.0.0.1', port=8000, access_log=False)

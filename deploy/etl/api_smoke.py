"""Real authenticated HTTP status contract against the local Kubernetes API."""
import json
from pathlib import Path
import time

import httpx
import jwt


token = jwt.encode({'sub':'user_etl_smoke','exp':int(time.time())+300},
                   Path('/evidence/signing.pem').read_bytes(),algorithm='RS256',headers={'kid':'local-task07'})
with httpx.Client(base_url='http://127.0.0.1:18080',timeout=20) as client:
    assert client.get('/api/market-data/status').status_code == 403
    response = client.get('/api/market-data/status',headers={'Authorization':'Bearer '+token})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    result = response.json()
    assert result['health']['healthy'], result['health']
    assert len(result['health']['prices']) == 20
    assert {'partial','blocked','succeeded'} <= {e['status'] for e in result['executions']}
    assert {'execution_partial','execution_blocked','missing_session'} <= {e['code'] for e in result['alerts']}
    assert all(p['latest_trade_date']==result['health']['expected_trade_date'] for p in result['health']['prices'])
    Path('/evidence/task08-api.json').write_text(json.dumps(result,indent=2))
    print('Authenticated API reports 20 fresh symbols, durable outcomes and historical alert events.')

"""Exercise the real API over the local NodePort with signed/forged JWTs."""
import json
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

key = Path('/evidence/signing.pem').read_bytes()
run = uuid4().hex[:12]


def headers(user, *, expired=False, forged=False):
    signer = rsa.generate_private_key(public_exponent=65537, key_size=2048) if forged else key
    return {'Authorization':'Bearer '+jwt.encode({'sub':user,'name':user,
        'exp':int(time.time())+(-60 if expired else 600)}, signer, algorithm='RS256',headers={'kid':'local-task07'})}


def check(response, status):
    assert response.status_code==status, (response.status_code,response.text)
    assert response.headers['content-type'].startswith('application/json')
    return response.json()


with httpx.Client(base_url='http://127.0.0.1:18080',timeout=15) as client:
    check(client.get('/health'),200)
    check(client.get('/ready'),200)
    alice,bob=f'user_alice_{run}',f'user_bob_{run}'
    for auth in ({}, {'Authorization':'Bearer invalid'}, headers(alice,expired=True), headers(alice,forged=True)):
        check(client.get('/api/accounts',headers=auth),403)
    for user in (alice,bob):
        profile=check(client.get('/api/user',headers=headers(user)),200)
        assert profile['user']['clerk_user_id']==user and profile['created']
    account=check(client.post('/api/accounts',headers=headers(alice),json={'account_name':'Local smoke','cash_balance':1000}),200)
    aid=account['id']
    check(client.get(f'/api/accounts/{aid}/positions',headers=headers(alice)),200)
    check(client.get(f'/api/accounts/{aid}/positions',headers=headers(bob)),403)
    check(client.put(f'/api/accounts/{aid}',headers=headers(bob),json={'account_name':'Forbidden'}),403)
    accounts=check(client.get('/api/accounts',headers=headers(bob)),200)
    assert accounts == []
    check(client.get('/api/does-not-exist',headers=headers(alice)),404)
    job=check(client.post('/api/analyze',headers=headers(alice),json={}),200)
    saved=check(client.get('/api/jobs/'+job['job_id'],headers=headers(alice)),200)
    assert saved['request_payload']['price_snapshot']['user_id']==alice
    check(client.get('/api/jobs/'+job['job_id'],headers=headers(bob)),403)
    preflight=client.options('/api/accounts',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'GET'})
    assert preflight.status_code==200 and preflight.headers['access-control-allow-origin']=='http://localhost:3000'
    evidence={'health':True,'readiness':True,'invalid_expired_forged_rejected':True,
        'signed_login':True,'cross_user_forbidden':True,'profile_account_persisted':True,
        'analysis_snapshot_queued':True,'cors':True,'run':run,'job_id':job['job_id']}
    Path('/evidence/smoke.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps({k:v for k,v in evidence.items() if k not in ('job_id','run')}))

"""Verify HTTPS/JWT authorization and the real SQS Reporter acceptance path.

Requires rendered deployment, local signer and completed real market ETL.
Only creates explicitly labelled acceptance users/accounts in alex_task09.
"""
import json
import time
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from manage import STATE, config


def main():
    cfg=config()
    key=(STATE/'signing.pem').read_bytes()
    run=uuid4().hex[:12]
    def headers(user,expired=False,forged=False):
        signer=rsa.generate_private_key(public_exponent=65537,key_size=2048) if forged else key
        return {'Authorization':'Bearer '+jwt.encode({'sub':user,'name':user,
            'exp':int(time.time())+(-60 if expired else 900)},signer,algorithm='RS256',headers={'kid':'task09'})}
    def check(response,status):
        if response.status_code!=status:
            raise RuntimeError(f'{response.request.url.path}: expected {status}, received {response.status_code}: {response.text[:250]}')
        assert response.headers['content-type'].startswith('application/json')
        return response.json()
    with httpx.Client(base_url=cfg['endpoint'],timeout=30) as client:
        check(client.get('/health'),200)
        check(client.get('/ready'),200)
        alice,bob='user_task09_alice_'+run,'user_task09_bob_'+run
        for auth in ({},{'Authorization':'Bearer invalid'},headers(alice,expired=True),headers(alice,forged=True)):
            check(client.get('/api/accounts',headers=auth),403)
        for user in (alice,bob):
            profile=check(client.get('/api/user',headers=headers(user)),200)
            assert profile['user']['clerk_user_id']==user
        account=check(client.post('/api/accounts',headers=headers(alice),json={'account_name':'Task09 acceptance','cash_balance':1000}),200)
        aid=account['id']
        check(client.post('/api/positions',headers=headers(alice),
                          json={'account_id':aid,'symbol':'AAPL','quantity':2}),200)
        positions=check(client.get(f'/api/accounts/{aid}/positions',headers=headers(alice)),200)
        check(client.get(f'/api/accounts/{aid}/positions',headers=headers(bob)),403)
        check(client.put(f'/api/accounts/{aid}',headers=headers(bob),json={'account_name':'Forbidden'}),403)
        assert check(client.get('/api/accounts',headers=headers(bob)),200)==[]
        check(client.get('/api/does-not-exist',headers=headers(alice)),404)
        market=check(client.get('/api/market-data/status',headers=headers(alice)),200)
        job=check(client.post('/api/analyze',headers=headers(alice),json={}),200)
        (STATE/('api-pending-'+run+'.json')).write_text(json.dumps({'job_id':job['job_id'],'user_id':alice}))
        check(client.get('/api/jobs/'+job['job_id'],headers=headers(bob)),403)
        deadline=time.monotonic()+300
        while True:
            saved=check(client.get('/api/jobs/'+job['job_id'],headers=headers(alice)),200)
            if saved['status']=='completed':
                break
            if time.monotonic()>deadline:
                raise RuntimeError('SQS Reporter did not complete within five minutes')
            time.sleep(5)
        snapshot=saved['request_payload']['price_snapshot']
        assert snapshot['user_id']==alice
        report=saved['report_payload']
        assert report['price_snapshot_sha256']==snapshot['sha256']
        assert report['research']['status']=='unavailable'
        preflight=client.options('/api/accounts',headers={'Origin':cfg['endpoint'],'Access-Control-Request-Method':'GET'})
        assert preflight.status_code==200 and preflight.headers['access-control-allow-origin']==cfg['endpoint']
        evidence={'observed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'endpoint':cfg['endpoint'],
            'https_json_errors':True,'signed_jwt':True,'invalid_expired_forged_rejected':True,
            'cross_user_forbidden':True,'sqs_report_completed':True,'research_unavailable_explicit':True,
            'snapshot_hash_preserved':True,'job_id':job['job_id'],'positions':positions,'market':market,'job':saved}
        (STATE/'api-evidence.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps({k:v for k,v in evidence.items() if isinstance(v,bool)}))


if __name__=='__main__':
    main()

"""Generate disposable credentials outside the image; run in the API container."""
import json
import secrets
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path('/output')
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
(root/'signing.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
public.update(kid='local-task07', alg='RS256', use='sig')
(root/'jwks.json').write_text(json.dumps({'keys':[public]}))
password = secrets.token_hex(24)
dsn = f'postgresql://alex:{password}@postgres:5432/alex'
objects = [
    {'kind':'Secret','metadata':{'name':'postgres-secrets'},'stringData':{
        'POSTGRES_USER':'alex','POSTGRES_DB':'alex','POSTGRES_PASSWORD':password}},
    {'kind':'Secret','metadata':{'name':'fixture-secrets'},'stringData':{'FIXTURE_DATABASE_URL':dsn}},
    {'kind':'Secret','metadata':{'name':'api-secrets'},'stringData':{
        'MARKET_DATABASE_URL':dsn,'AWS_ACCESS_KEY_ID':'local-only','AWS_SECRET_ACCESS_KEY':'local-only'}},
    {'kind':'ConfigMap','metadata':{'name':'fixture-jwks'},'data':{'jwks.json':json.dumps({'keys':[public]})}},
    {'kind':'ConfigMap','metadata':{'name':'api-config'},'data':{
        'DEFAULT_AWS_REGION':'us-east-1','AWS_EC2_METADATA_DISABLED':'true',
        'AWS_ENDPOINT_URL_RDS_DATA':'http://fixtures:8081','AWS_ENDPOINT_URL_SQS':'http://fixtures:8081',
        'AURORA_CLUSTER_ARN':'arn:aws:rds:us-east-1:000000000000:cluster:local',
        'AURORA_SECRET_ARN':'arn:aws:secretsmanager:us-east-1:000000000000:secret:local',
        'AURORA_DATABASE':'alex','CLERK_JWKS_URL':'http://fixtures:8081/.well-known/jwks.json',
        'SQS_QUEUE_URL':'http://fixtures:8081/queue/alex','CORS_ORIGINS':'http://localhost:3000'}},
]
for item in objects:
    item['apiVersion']='v1'
(root/'config-private.json').write_text(json.dumps({'apiVersion':'v1','kind':'List','items':objects}))
for path in root.iterdir():
    if path.is_file():
        path.chmod(0o600)
print('Generated local-only configuration and signing key; no production credentials used.')

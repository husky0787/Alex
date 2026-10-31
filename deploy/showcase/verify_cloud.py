"""Probe real deployed artifacts and attributed research, without user credentials."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess

import boto3
from botocore.config import Config
import httpx

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.local/showcase'


def outputs(directory):
    return json.loads(subprocess.check_output(['terraform', f'-chdir={ROOT / "terraform" / directory}',
                                               'output', '-json'], text=True, encoding='utf-8'))


def research(source):
    records = json.loads(source.read_text(encoding='utf-8-sig'))
    if len(records) != 1:
        raise RuntimeError('Select exactly one previously captured attributed research record')
    record = records[0]
    from research_chain import validate_document
    config = outputs('3_ingestion')
    document = {'text': record['text'], 'metadata': record['metadata']}
    # Preserve the source identity and observed timestamp; never re-date a replay.
    document['metadata']['research_id'] = record['id']
    validate_document(document)
    response = httpx.post(config['api_endpoint']['value'], json=document,
                          headers={'x-api-key': config['api_key_value']['value']}, timeout=90)
    if response.status_code != 200:
        (STATE / 'ingestion-failure-private.txt').write_text(response.text, encoding='utf-8')
        raise RuntimeError(f'Ingestion returned HTTP {response.status_code}; private diagnostic retained')
    receipt = response.json()
    os.environ.update(RESEARCH_AWS_REGION='us-east-1', VECTOR_BUCKET=config['vector_bucket_name']['value'],
                      INDEX_NAME='financial-research', SAGEMAKER_ENDPOINT='alex-embedding-endpoint')
    from research_chain import search
    retrieved = search('market analysis AAPL MSFT', k=3)
    matched = next((item for item in retrieved if item['id'] == record['id']), None)
    if not matched or matched['metadata']['sources'] != record['metadata']['sources'] or matched['text'] != record['text']:
        raise RuntimeError('Research read-back does not match the captured source')
    (STATE / 'research-private.json').write_text(json.dumps({'receipt': receipt, 'retrieved': matched}, indent=2), encoding='utf-8')
    print('Real ingestion/vector retrieval passed; original research ID, text and sources preserved.')


def workers():
    config = outputs('11_showcase')
    (STATE / 'deployment-private.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    manifest = json.loads((STATE / 'workers/manifest.json').read_text(encoding='utf-8'))
    client = boto3.client('lambda', region_name='us-east-1', config=Config(read_timeout=330, retries={'total_max_attempts': 1}))
    result = {}
    for name, function in config['workers']['value'].items():
        live = client.get_function_configuration(FunctionName=function)
        if base64.b64decode(live['CodeSha256']).hex() != manifest['workers'][name]['sha256']:
            raise RuntimeError(f'{name} deployed hash differs from built artifact')
        event = {'Records': []} if name == 'planner' else {}
        response = client.invoke(FunctionName=function, InvocationType='RequestResponse', Payload=json.dumps(event).encode())
        body = json.loads(response['Payload'].read())
        result[name] = {'function_error': response.get('FunctionError'), 'body': body, 'code_sha256': live['CodeSha256']}
        (STATE / 'imports-private.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        expected = body == {'batchItemFailures': []} if name == 'planner' else body.get('statusCode') == 400
        if response.get('FunctionError') or not expected:
            raise RuntimeError(f'{name} failed runtime import/empty-event probe; inspect private result')
        print(f'{name}: deployed hash and real Lambda import passed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['workers', 'research'])
    parser.add_argument('--captured-research', type=Path)
    args = parser.parse_args()
    if args.action == 'workers':
        workers()
    else:
        if not args.captured_research:
            parser.error('--captured-research is required')
        research(args.captured_research)

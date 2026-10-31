"""Derive private worker inputs from reviewed, already applied research states."""
import argparse

from environment import STATE, aws, read, save
from verify_cloud import outputs


def configure(jwks_url):
    if not jwks_url.startswith('https://') or not jwks_url.endswith('/.well-known/jwks.json'):
        raise ValueError('Supply the real Clerk HTTPS JWKS endpoint')
    target = read('application-target-private.json')
    account = aws('sts', 'get-caller-identity')['Account']
    if target['cluster'].split(':')[4] != account:
        raise RuntimeError('AWS identity differs from the selected application cluster')
    vector_bucket = outputs('3_ingestion')['vector_bucket_name']['value']
    save('workers.tfvars.json', {
        'cluster_arn': target['cluster'], 'database_secret_arn': target['secret'],
        'vector_bucket': vector_bucket,
        'vector_index_arn': f'arn:aws:s3vectors:us-east-1:{account}:bucket/{vector_bucket}/index/financial-research',
        'sagemaker_endpoint_arn': outputs('2_sagemaker')['sagemaker_endpoint_arn']['value'],
        'bedrock_model_arns': read('preflight-private.json')['bedrock_arns'],
        'worker_directory': (STATE / 'workers').as_posix(),
    })
    save('public-config.json', {'clerk_jwks_url': jwks_url})
    print('Worker inputs and public authentication configuration saved under ignored .local/showcase/.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clerk-jwks-url', required=True)
    configure(parser.parse_args().clerk_jwks_url)

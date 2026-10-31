"""Child-process import probe launched by the API contract suite."""
import os
from unittest.mock import patch


def check():
    expected = {key: os.environ[key] for key in ('SQS_QUEUE_URL', 'CLERK_JWKS_URL', 'AURORA_CLUSTER_ARN',
                                                'AURORA_SECRET_ARN', 'AURORA_DATABASE')}
    with patch('dotenv.load_dotenv', side_effect=AssertionError('Explicit configuration must not read .env')), \
         patch('botocore.httpsession.URLLib3Session.send', side_effect=AssertionError('Network forbidden')):
        import main
    assert all(os.environ[key] == value for key, value in expected.items())
    assert main.SQS_QUEUE_URL == expected['SQS_QUEUE_URL']
    assert main.clerk_config.jwks_url == expected['CLERK_JWKS_URL']
    assert main.db.client.database == expected['AURORA_DATABASE']
    assert main.db.client.cluster_arn == expected['AURORA_CLUSTER_ARN']
    assert main.db.client.secret_arn == expected['AURORA_SECRET_ARN']


if __name__ == '__main__':
    check()

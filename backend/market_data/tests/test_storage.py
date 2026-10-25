import io
import unittest

import boto3
from botocore.stub import Stubber

from market_data.storage import S3RawStore


class S3RawStorageTests(unittest.TestCase):
    def test_raw_body_uses_private_encrypted_immutable_s3_write(self):
        client = boto3.client('s3', region_name='us-east-1', aws_access_key_id='testing', aws_secret_access_key='testing')
        key = 'raw/massive/AAPL/run/digest.json'
        body = b'{"results":[]}'
        with Stubber(client) as stub:
            stub.add_response('put_object', {}, {
                'Bucket': 'alex-private-market-test', 'Key': key, 'Body': body,
                'ContentType': 'application/json', 'ServerSideEncryption': 'AES256', 'IfNoneMatch': '*',
            })
            stub.add_response('get_object', {'Body': io.BytesIO(body)}, {'Bucket': 'alex-private-market-test', 'Key': key})
            store = S3RawStore('alex-private-market-test', client)
            self.assertEqual(store.save(key, body), f's3://alex-private-market-test/{key}')
            self.assertEqual(store.read(key), body)
            stub.assert_no_pending_responses()

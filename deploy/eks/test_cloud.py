"""Offline boundaries for cloud credentials, manifests and SQS retry behavior."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import tempfile
import subprocess
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit, unquote

from market_data.cloud import load_database_environment, main
from manifests import manifests, manual_job


class CloudTests(unittest.TestCase):
    def test_recovery_requires_new_ready_uid_and_full_replica_count(self):
        from verify_operations import replacement_ready
        def pod(uid,ready):
            return {'metadata':{'uid':uid},'status':{'conditions':[{'type':'Ready','status':'True' if ready else 'False'}]}}
        before={'old','survivor'}
        self.assertFalse(replacement_ready([pod('survivor',True)],before,2))
        self.assertFalse(replacement_ready([pod('survivor',True),pod('new',False)],before,2))
        self.assertFalse(replacement_ready([pod('survivor',True),pod('old',True)],before,2))
        self.assertTrue(replacement_ready([pod('survivor',True),pod('new',True)],before,2))

    def test_database_wakeup_retries_connect_but_preserves_login_errors(self):
        import bootstrap_database as bootstrap
        import psycopg
        ready=Mock()
        with patch.object(bootstrap.psycopg,'connect',side_effect=[psycopg.OperationalError('timeout'),ready]) as connect, \
                patch.object(bootstrap.time,'sleep'),patch('builtins.print'):
            self.assertIs(bootstrap.connect_ready(dbname='postgres'),ready)
            self.assertEqual(connect.call_count,2)
        with patch.object(bootstrap.psycopg,'connect',side_effect=psycopg.errors.InvalidPassword('private')) as connect, \
                self.assertRaises(psycopg.errors.InvalidPassword):
            bootstrap.connect_ready(dbname='postgres')
        self.assertEqual(connect.call_count,1)

    def test_bootstrap_configmap_failure_also_removes_admin_service_account(self):
        import manage
        cfg={'aurora_cluster_arn':'cluster','database':'alex_task09','alerts_topic_arn':'topic','api_secret_arn':'api-secret',
             'etl_secret_arn':'etl-secret','jobs_queue_url':'queue','endpoint':'https://example.cloudfront.net','bucket':'raw-bucket',
             'aurora_admin_secret_arn':'admin-secret'}
        image='123456789012.dkr.ecr.us-east-1.amazonaws.com/alex-task09@sha256:'+'a'*64
        original=RuntimeError('configmap apply failed')
        def apply(value):
            if value['kind']=='ConfigMap':
                raise original
        with tempfile.TemporaryDirectory() as directory:
            state=Path(directory)
            (state/'manifests.json').write_text(json.dumps(manifests(cfg,image,'{}')))
            with patch.object(manage,'STATE',state),patch.object(manage,'config',return_value=cfg), \
                    patch.object(manage,'apply',side_effect=apply),patch.object(manage,'kube',return_value='') as kube, \
                    patch.object(sys,'argv',['manage.py','bootstrap']),patch('builtins.print'), \
                    self.assertRaises(RuntimeError) as failure:
                manage.main()
            self.assertIs(failure.exception,original)
            self.assertTrue(any(call.args[0]=='delete' and 'serviceaccount/bootstrap' in call.args for call in kube.call_args_list))

    def test_secret_lookup_failure_still_delivers_etl_alert(self):
        secret=Mock();sns=Mock()
        secret.get_secret_value.side_effect=RuntimeError('sensitive provider detail')
        with patch.dict(os.environ,{'WORKLOAD_SECRET_ARN':'secret-arn','ALERT_TOPIC_ARN':'topic-arn'}), \
                patch('market_data.cloud.boto3.client',side_effect=[secret,sns]),patch('builtins.print'), \
                self.assertRaises(SystemExit) as stopped:
            main(['daily'])
        self.assertEqual(stopped.exception.code,1)
        self.assertEqual(json.loads(sns.publish.call_args.kwargs['Message'])['error_code'],'RuntimeError')
        self.assertNotIn('sensitive',sns.publish.call_args.kwargs['Message'])

    def test_cli_secret_input_is_not_in_process_arguments_and_is_removed(self):
        import manage
        def invoke(command,**kwargs):
            self.assertNotIn('test-secret',str(command))
            path=Path(command[command.index('--cli-input-json')+1].removeprefix('file://'))
            self.assertEqual(json.loads(path.read_text())['SecretString'],'test-secret')
            self.input_path=path
            return types.SimpleNamespace(returncode=0,stdout='{}',stderr='')
        with patch('manage.subprocess.run',side_effect=invoke):
            manage.aws('secretsmanager','put-secret-value',SecretString='test-secret')
        self.assertFalse(self.input_path.exists())

    def test_secret_password_cannot_change_tls_connection_options(self):
        env={}
        value={'username':'api','password':'a@x/?sslmode=disable&foo=1','host':'example.rds.amazonaws.com','dbname':'alex_task09'}
        load_database_environment(value,environ=env)
        uri=urlsplit(env['MARKET_DATABASE_URL'])
        self.assertEqual(unquote(uri.password),value['password'])
        self.assertEqual(uri.hostname,value['host'])
        self.assertIn('sslmode=verify-full',uri.query)
        self.assertNotIn('sslmode=disable',uri.query)
        self.assertNotIn('MASSIVE_API_KEY',env)

    def test_failed_etl_publishes_real_alert_request_and_returns_failure(self):
        secret=Mock();sns=Mock()
        secret.get_secret_value.return_value={'SecretString':json.dumps({'username':'etl','password':'secret',
            'host':'example.rds.amazonaws.com','dbname':'alex_task09','MASSIVE_API_KEY':'test-key'})}
        with patch.dict(os.environ,{'WORKLOAD_SECRET_ARN':'secret-arn','ALERT_TOPIC_ARN':'topic-arn','POD_NAME':'job-1'}), \
                patch('market_data.cloud.boto3.client',side_effect=[secret,sns]), \
                patch('market_data.cloud.scheduled.main',return_value=1) as etl:
            self.assertEqual(main(['daily','--raw-bucket','private-bucket']),1)
            etl.assert_called_once_with(['daily','--raw-bucket','private-bucket'])
            message=json.loads(sns.publish.call_args.kwargs['Message'])
            self.assertEqual(message['pod'],'job-1')
            self.assertNotIn('secret',sns.publish.call_args.kwargs['Message'])

    def test_success_does_not_publish_failure(self):
        secret=Mock()
        secret.get_secret_value.return_value={'SecretString':json.dumps({'username':'etl','password':'x','host':'h','dbname':'db'})}
        with patch.dict(os.environ,{'WORKLOAD_SECRET_ARN':'arn'}),patch('market_data.cloud.boto3.client',return_value=secret) as client, \
                patch('market_data.cloud.scheduled.main',return_value=0):
            self.assertEqual(main(['monitor']),0)
            client.assert_called_once_with('secretsmanager')

    def test_cloud_manifests_use_roles_and_digest_without_secret_values(self):
        cfg={'aurora_cluster_arn':'cluster','database':'alex_task09','alerts_topic_arn':'topic','api_secret_arn':'api-secret',
             'etl_secret_arn':'etl-secret','jobs_queue_url':'queue','endpoint':'https://example.cloudfront.net','bucket':'raw-bucket'}
        image='123456789012.dkr.ecr.us-east-1.amazonaws.com/alex-task09@sha256:'+'a'*64
        objects=manifests(cfg,image,'{"keys":[]}')['items']
        self.assertFalse(any(x['kind']=='Secret' for x in objects))
        api=next(x for x in objects if x['kind']=='Deployment' and x['metadata']['name']=='api')
        self.assertEqual(api['spec']['template']['spec']['serviceAccountName'],'api')
        daily=next(x for x in objects if x['kind']=='CronJob' and x['metadata']['name']=='market-daily')
        job=manual_job(daily,'recovery',['backfill','--from','2026-10-01','--to','2026-10-29'])
        self.assertEqual(job['spec']['template']['spec']['serviceAccountName'],'etl')
        self.assertEqual(daily['spec']['jobTemplate']['spec']['template']['spec']['containers'][0]['args'][0],'daily')
        with self.assertRaises(ValueError):
            manifests(cfg,'alex-api:latest','{}')

    def test_reporter_failure_is_returned_for_sqs_retry(self):
        reporter=types.ModuleType('lambda_handler');reporter.lambda_handler=Mock(return_value={'statusCode':500})
        database=types.ModuleType('src');database.Database=Mock()
        with patch.dict(sys.modules,{'lambda_handler':reporter,'src':database}):
            spec=importlib.util.spec_from_file_location('task09_sqs',Path(__file__).with_name('sqs_handler.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with patch('builtins.print'):
                result=module.lambda_handler({'Records':[{'messageId':'m1','body':'18de265b-8b07-4c96-a1c1-49ba326c11cf'}]},None)
            self.assertEqual(result,{'batchItemFailures':[{'itemIdentifier':'m1'}]})
            database.Database.assert_not_called()

    def test_worker_consumes_plain_uuid_body_emitted_by_analyze_api(self):
        job_id='18de265b-8b07-4c96-a1c1-49ba326c11cf'
        reporter=types.ModuleType('lambda_handler')
        reporter.lambda_handler=Mock(return_value={'statusCode':200,'body':'{"success":true}'})
        database=types.ModuleType('src');database.Database=Mock()
        with patch.dict(sys.modules,{'lambda_handler':reporter,'src':database}):
            spec=importlib.util.spec_from_file_location('task09_sqs_success',Path(__file__).with_name('sqs_handler.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            with patch('builtins.print'):
                result=module.lambda_handler({'Records':[{'messageId':'m1','body':job_id}]},None)
            self.assertEqual(result,{'batchItemFailures':[]})
            reporter.lambda_handler.assert_called_once_with({'job_id':job_id},None)
            database.Database.return_value.client.execute.assert_called_once()


if __name__=='__main__':
    unittest.main()

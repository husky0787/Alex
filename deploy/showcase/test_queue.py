import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

snapshot = {'accounts': [{'positions': [{'symbol': 'AAPL'}, {'symbol': 'MSFT'}]}],
            'user_preferences': {'years_until_retirement': 20}}
database = Mock()
worker = Mock()
modules = {'lambda_handler': SimpleNamespace(lambda_handler=worker),
           'src': SimpleNamespace(Database=lambda: database),
           'src.snapshots': SimpleNamespace(load_snapshot=lambda db, job: snapshot)}
spec = importlib.util.spec_from_file_location('showcase_queue', Path(__file__).with_name('planner_queue.py'))
queue = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, modules):
    spec.loader.exec_module(queue)


class QueueCompletion(unittest.TestCase):
    def setUp(self):
        worker.reset_mock()
        database.reset_mock()
        worker.return_value = {'statusCode': 200, 'body': json.dumps({'success': True})}
        database.jobs.find_by_id.return_value = {'status': 'completed', 'report_payload': {'content': 'report'},
                                                'charts_payload': {'charts': [1]}, 'retirement_payload': {'result': 1}}
        self.job = str(uuid4())
        self.record = {'messageId': 'message-1', 'body': self.job}

    def test_all_expected_outputs_are_required_even_when_planner_says_success(self):
        for field in ('report_payload', 'charts_payload', 'retirement_payload'):
            with self.subTest(field=field):
                healthy = database.jobs.find_by_id.return_value.copy()
                database.jobs.find_by_id.return_value[field] = None
                result = queue.lambda_handler({'Records': [self.record]}, None)
                self.assertEqual(result, {'batchItemFailures': [{'itemIdentifier': 'message-1'}]})
                database.jobs.update_status.assert_called_with(self.job, 'failed', error_message='showcase_analysis_failed')
                database.jobs.find_by_id.return_value = healthy

    def test_successful_output_is_acknowledged(self):
        self.assertEqual(queue.lambda_handler({'Records': [self.record]}, None), {'batchItemFailures': []})
        database.jobs.update_status.assert_not_called()

    def test_application_error_is_not_treated_as_transport_success(self):
        worker.return_value = {'statusCode': 500, 'body': json.dumps({'success': False})}
        self.assertTrue(queue.lambda_handler({'Records': [self.record]}, None)['batchItemFailures'])

    def test_malformed_job_cannot_invoke_worker_or_modify_database(self):
        result = queue.lambda_handler({'Records': [{'messageId': 'bad', 'body': 'not-a-job'}]}, None)
        self.assertEqual(result, {'batchItemFailures': [{'itemIdentifier': 'bad'}]})
        worker.assert_not_called()
        database.jobs.update_status.assert_not_called()


if __name__ == '__main__':
    unittest.main()

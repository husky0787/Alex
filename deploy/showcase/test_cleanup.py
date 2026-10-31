"""Ownership and partial-cleanup contracts; no network or database calls."""
from unittest import TestCase, main
from unittest.mock import Mock, patch

import cleanup


class CleanupBoundary(TestCase):
    def setUp(self):
        self.files = {
            'admin-target-private.json': {'database': 'alex'},
            'database-ledger-private.json': {'database': 'alex_task11', 'role': 'alex_task11_app',
                                             'marker': 'owned', 'secret_arn': 'owned-secret'},
            'archive-receipt-private.json': {'marker': 'owned'},
            'preflight-private.json': {'original_functions': []},
        }
        self.statements = []
        self.db_exists = True
        self.role_exists = True
        self.db_marker = 'owned'

    def sql(self, target, statement, **kwargs):
        self.statements.append(statement)
        if 'shobj_description' in statement:
            exists = self.db_exists if 'pg_database' in statement else self.role_exists
            marker = self.db_marker if 'pg_database' in statement else 'owned'
            return {'records': [[{'stringValue': marker}]] if exists else []}
        if statement.startswith('DROP DATABASE'):
            self.db_exists = False
        if statement.startswith('DROP ROLE'):
            self.role_exists = False
        if 'SELECT datname' in statement:
            return {'records': [[{'stringValue': 'alex'}]] if kwargs.get('parameters') else []}
        return {'records': []}

    def aws(self, service, operation, **kwargs):
        if operation == 'list-functions':
            return {'Functions': []}
        if operation == 'describe-secret':
            return {'Tags': [{'Key': 'OwnerToken', 'Value': 'owned'}]}
        return {}

    def run_cleanup(self, aws=None):
        with patch.object(cleanup, 'read', side_effect=self.files.__getitem__), \
             patch.object(cleanup, 'sql', side_effect=self.sql), \
             patch.object(cleanup, 'aws', side_effect=aws or self.aws), \
             patch.object(cleanup, 'save'):
            cleanup.database()

    def test_replaced_database_blocks_all_deletion(self):
        self.db_marker = 'someone-else'
        with self.assertRaisesRegex(RuntimeError, 'ownership marker differs'):
            self.run_cleanup()
        self.assertFalse(any(sql.startswith('DROP') for sql in self.statements))

    def test_unmatched_archive_blocks_all_deletion(self):
        self.files['archive-receipt-private.json']['marker'] = 'another-run'
        with self.assertRaisesRegex(RuntimeError, 'Matching archive'):
            self.run_cleanup()
        self.assertEqual(self.statements, [])

    def test_resume_after_database_drop_preserves_role_and_secret_checks(self):
        self.db_exists = False
        remote = Mock(side_effect=self.aws)
        self.run_cleanup(remote)
        self.assertNotIn('DROP DATABASE alex_task11 WITH (FORCE)', self.statements)
        self.assertIn('DROP ROLE alex_task11_app', self.statements)
        remote.assert_any_call('secretsmanager', 'delete-secret', SecretId='owned-secret', RecoveryWindowInDays=7)

    def test_live_workers_block_database_deletion(self):
        def remote(service, operation, **kwargs):
            if operation == 'list-functions':
                return {'Functions': [{'FunctionName': 'alex-task11-planner'}]}
            return self.aws(service, operation, **kwargs)
        with self.assertRaisesRegex(RuntimeError, 'Destroy the dedicated workers'):
            self.run_cleanup(remote)
        self.assertFalse(any(sql.startswith('DROP') for sql in self.statements))


if __name__ == '__main__':
    main()

"""Boundary tests for provenance, interruption recovery, and failed cleanup."""
from datetime import datetime, timedelta, timezone
import os
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gate
import lifecycle
from window import check_window

SHA = 'a' * 40
NOW = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)


def run(**changes):
    value = dict(id=42, run_attempt=1, head_sha=SHA, head_branch='main',
        event='push', status='completed', conclusion='success',
        head_repository={'full_name': gate.REPO}, path='.github/workflows/ci.yml')
    return value | changes


def owned(release='42-1', expiry=None, status='CREATE_COMPLETE'):
    tags = {'Project': 'alex', 'Purpose': lifecycle.PURPOSE, 'ReleaseId': release,
            'ExpiresAt': (expiry or NOW + timedelta(hours=1)).isoformat()}
    return {'StackId': 'owned-id', 'StackStatus': status,
            'Tags': [{'Key': k, 'Value': v} for k, v in tags.items()]}


class ProvenanceTests(unittest.TestCase):
    def test_only_exact_main_success_from_our_ci_is_eligible(self):
        for change in ({'head_sha': 'b' * 40}, {'head_branch': 'feature'},
                {'event': 'pull_request'}, {'conclusion': 'failure'}, {'status': 'in_progress'},
                {'head_repository': {'full_name': 'fork/Alex'}}, {'path': '.github/workflows/other.yml'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                gate.select_run([run(**change)], SHA)
        self.assertEqual(gate.select_run([run()], SHA)['id'], 42)

    def test_skipped_required_jobs_do_not_count_as_pass(self):
        jobs = [{'name': name, 'conclusion': 'success'} for name in gate.REQUIRED]
        gate.verify_jobs(jobs)
        jobs[0]['conclusion'] = 'skipped'
        with self.assertRaises(ValueError):
            gate.verify_jobs(jobs)

    def test_expired_missing_or_duplicate_images_refused(self):
        artifact = {'id': 2, 'name': 'tested-images', 'expired': False}
        self.assertEqual(gate.select_artifact([artifact])['id'], 2)
        for values in ([], [artifact | {'expired': True}], [artifact, artifact]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                gate.select_artifact(values)

    def test_latest_success_selected_without_using_failed_run(self):
        self.assertEqual(gate.select_run([run(), run(id=43), run(id=44, conclusion='failure')], SHA)['id'], 43)


class OwnershipTests(unittest.TestCase):
    def test_completion_cannot_clean_up_newer_release(self):
        self.assertFalse(lifecycle.recoverable(owned('43-1'), completed_run='42'))
        self.assertTrue(lifecycle.recoverable(owned('42-1'), completed_run='42'))

    def test_schedule_waits_for_expiry(self):
        self.assertFalse(lifecycle.recoverable(owned(), now=NOW))
        self.assertTrue(lifecycle.recoverable(owned(expiry=NOW - timedelta(seconds=1)), now=NOW))

    def test_missing_or_foreign_owner_refused(self):
        for value in ({'Tags': []}, owned('not-a-run')):
            with self.assertRaises(ValueError):
                lifecycle.owner(value)
        value = owned()
        value['Tags'][1]['Value'] = 'original-project'
        with self.assertRaises(ValueError):
            lifecycle.owner(value)

    @patch.dict(os.environ, {'ALEX_CD_CF_ROLE_ARN': 'role', 'ALEX_CD_REPOSITORY': 'registry/alex-cd-api'})
    def test_partial_create_is_waited_then_deleted(self):
        initial = owned(status='CREATE_IN_PROGRESS')
        with patch.object(lifecycle, 'stack', return_value=initial), \
                patch.object(lifecycle, 'wait_terminal', side_effect=[owned(status='CREATE_FAILED'), None]) as wait, \
                patch.object(lifecycle, 'aws') as aws, \
                patch.object(lifecycle, 'delete_images') as images, \
                patch.object(lifecycle, 'evidence') as evidence:
            aws.side_effect = [{}, lifecycle.AwsError('ResourceNotFoundException')]
            lifecycle.cleanup(release_id='42-1')
            self.assertEqual(wait.call_count, 2)
            self.assertEqual(aws.call_args_list[0].args, ('cloudformation', 'delete-stack'))
            images.assert_called_once_with('42-1')
            self.assertTrue(evidence.call_args.args[1]['cluster_absent'])

    @patch.dict(os.environ, {'ALEX_CD_CF_ROLE_ARN': 'role'})
    def test_failed_deletion_is_not_reported_as_success(self):
        with patch.object(lifecycle, 'stack', return_value=owned()), \
                patch.object(lifecycle, 'wait_terminal', side_effect=[owned(), owned(status='DELETE_FAILED')]), \
                patch.object(lifecycle, 'aws'), patch.object(lifecycle, 'evidence') as evidence:
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                lifecycle.cleanup(release_id='42-1')
            evidence.assert_not_called()

    def test_unknown_stack_never_deleted(self):
        with patch.object(lifecycle, 'stack', return_value=owned('43-1')), patch.object(lifecycle, 'aws') as aws:
            with self.assertRaises(ValueError):
                lifecycle.cleanup(release_id='42-1')
            aws.assert_not_called()

    def test_missing_stack_does_not_hide_orphan_cluster(self):
        with patch.object(lifecycle, 'stack', return_value=None), patch.object(lifecycle, 'aws', return_value={'cluster': {}}), \
                patch.object(lifecycle, 'delete_images'), patch.object(lifecycle, 'evidence') as evidence:
            with self.assertRaisesRegex(RuntimeError, 'still exists'):
                lifecycle.cleanup(completed_run='42', completed_attempt='1')
            evidence.assert_not_called()

    def test_recovery_deletes_exact_images_after_stack_already_deleted(self):
        with patch.object(lifecycle, 'stack', return_value=None), \
                patch.object(lifecycle, 'aws', side_effect=lifecycle.AwsError('ResourceNotFoundException')), \
                patch.object(lifecycle, 'delete_images') as images, patch.object(lifecycle, 'evidence'):
            lifecycle.cleanup(completed_run='42', completed_attempt='2')
            images.assert_called_once_with('42-2')

    def test_old_completion_does_not_destroy_new_attempt(self):
        with patch.object(lifecycle, 'stack', return_value=owned('42-2')), \
                patch.object(lifecycle, 'aws') as aws, patch.object(lifecycle, 'delete_images') as images:
            lifecycle.cleanup(completed_run='42', completed_attempt='1')
            aws.assert_not_called()
            images.assert_called_once_with('42-1')

    def test_recovery_requires_attempt(self):
        with patch.object(lifecycle, 'stack', return_value=None), self.assertRaises(ValueError):
            lifecycle.cleanup(completed_run='42')

    @patch.dict(os.environ, {'ALEX_CD_REPOSITORY': 'registry/alex-cd-api'})
    def test_delete_only_exact_tags_and_propagate_ecr_failure(self):
        with patch.object(lifecycle, 'aws', return_value={}) as aws:
            lifecycle.delete_images('42-1')
            self.assertEqual(aws.call_args.kwargs['imageIds'], [
                {'imageTag': 'cd-42-1-baseline'}, {'imageTag': 'cd-42-1-candidate'}])
        with patch.object(lifecycle, 'aws', return_value={'failures': [{'failureCode': 'KmsError'}]}):
            with self.assertRaises(RuntimeError):
                lifecycle.delete_images('42-1')

    def test_missing_stack_only_accepts_exact_not_found(self):
        for error in ('AccessDenied', 'ValidationError unrelated input'):
            with patch.object(lifecycle, 'aws', side_effect=lifecycle.AwsError(error)):
                with self.assertRaises(lifecycle.AwsError):
                    lifecycle.stack()


class WindowTests(unittest.TestCase):
    def test_expired_unbounded_and_insufficient_windows_refused(self):
        for expiry in (NOW, NOW + timedelta(hours=1), NOW + timedelta(days=2)):
            with self.assertRaises(ValueError):
                check_window(expiry.isoformat(), NOW)
        self.assertEqual(check_window((NOW + timedelta(hours=3)).isoformat(), NOW), NOW + timedelta(hours=3))


class DiagnosticsTests(unittest.TestCase):
    def test_kubernetes_reason_survives_without_publishing_secret_output(self):
        import cloud_acceptance
        failure = SimpleNamespace(returncode=1, stdout='private-manifest',
                                  stderr='Error from server (Forbidden): secret-value')
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(cloud_acceptance, 'STATE', Path(directory)), \
                patch.object(cloud_acceptance.subprocess, 'run', return_value=failure), \
                patch.object(cloud_acceptance, 'evidence') as evidence:
            with self.assertRaisesRegex(RuntimeError, 'Forbidden'):
                cloud_acceptance.kube('apply', '-f', '-', data='private-manifest')
            self.assertIn('secret-value', (Path(directory) / 'kubectl-private.log').read_text())
            self.assertEqual(evidence.call_args.args[1]['reason'], 'Forbidden')
            self.assertNotIn('secret-value', str(evidence.call_args))


if __name__ == '__main__':
    unittest.main()

"""Release behavior at the Kubernetes boundary; live drills run separately."""
from copy import deepcopy
import unittest
from release import release, ReleaseError

OLD = 'registry.example/api@sha256:' + '1' * 64
NEW = 'registry.example/api@sha256:' + '2' * 64
COMMIT = 'a' * 40


class Cluster:
    def __init__(self, fail=False, rollback_fail=False, concurrent=False):
        self.value = {'metadata': {'resourceVersion': '1', 'generation': 1},
                      'spec': {'replicas': 2, 'template': {'metadata': {'annotations': {'keep': 'yes'}},
                               'spec': {'containers': [{'name': 'api', 'image': OLD}]}}},
                      'status': {'observedGeneration': 1, 'updatedReplicas': 2,
                                 'readyReplicas': 2, 'availableReplicas': 2}}
        self.fail, self.rollback_fail, self.concurrent = fail, rollback_fail, concurrent
        self.writes = []

    def read(self):
        return deepcopy(self.value)

    def replace_template(self, current, template):
        self.writes.append(deepcopy(template))
        self.value['spec']['template'] = deepcopy(template)

    def wait(self):
        if self.fail and len(self.writes) == 1:
            if self.concurrent:
                self.value['spec']['template']['metadata']['annotations']['other'] = 'release'
            raise ReleaseError('candidate did not become ready')
        if self.rollback_fail:
            raise ReleaseError('rollback did not become ready')


class ReleaseTests(unittest.TestCase):
    def test_success_records_commit_and_both_immutable_images(self):
        cluster = Cluster()
        result = release(cluster, NEW, COMMIT, lambda: None)
        self.assertEqual((result['status'], result['previous_image'], result['image']), ('succeeded', OLD, NEW))
        self.assertEqual(cluster.value['spec']['template']['metadata']['annotations']['alex.dev/commit'], COMMIT)

    def test_failed_candidate_restores_previous_template_and_reports_failure(self):
        cluster = Cluster(fail=True)
        old = deepcopy(cluster.value['spec']['template'])
        result = release(cluster, NEW, COMMIT, lambda: None)
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(cluster.value['spec']['template'], old)

    def test_rollback_failure_is_not_reported_as_recovery(self):
        result = release(Cluster(fail=True, rollback_fail=True), NEW, COMMIT, lambda: None)
        self.assertEqual(result['status'], 'rollback_failed')

    def test_concurrent_release_is_not_overwritten_by_rollback(self):
        cluster = Cluster(fail=True, concurrent=True)
        result = release(cluster, NEW, COMMIT, lambda: None)
        self.assertEqual(result['status'], 'rollback_failed')
        self.assertEqual(len(cluster.writes), 1)

    def test_mutable_tags_and_unhealthy_baselines_are_rejected_before_writing(self):
        for invalid in ('registry.example/api:latest', NEW):
            cluster = Cluster()
            if invalid == NEW:
                cluster.value['status']['readyReplicas'] = 1
            with self.assertRaises(ReleaseError):
                release(cluster, invalid, COMMIT, lambda: None)
            self.assertEqual(cluster.writes, [])

    def test_post_release_smoke_failure_also_rolls_back(self):
        cluster = Cluster()
        calls = []
        def smoke():
            calls.append(1)
            if len(calls) == 2:
                raise ReleaseError('readiness smoke failed')
        self.assertEqual(release(cluster, NEW, COMMIT, smoke)['status'], 'rolled_back')
        self.assertEqual(len(calls), 3)


if __name__ == '__main__':
    unittest.main()

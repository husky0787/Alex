"""Select only successful, exact-commit CI artifacts from trusted main runs."""
import json
import os
import re
import urllib.parse
import urllib.request

REPO = 'husky0787/Alex'
REQUIRED = {'backend', 'frontend', 'image-and-rollout'}


def eligible(run, sha):
    return (run.get('head_sha') == sha and run.get('head_branch') == 'main'
            and run.get('event') in ('push', 'workflow_dispatch')
            and run.get('status') == 'completed' and run.get('conclusion') == 'success'
            and run.get('head_repository', {}).get('full_name') == REPO
            and run.get('path') == '.github/workflows/ci.yml')


def select_run(runs, sha):
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ValueError('A full workflow commit is required')
    matches = [r for r in runs if eligible(r, sha)]
    if not matches:
        raise ValueError('No successful main CI for this exact commit; run CI first')
    return max(matches, key=lambda r: (r['id'], r.get('run_attempt', 1)))


def verify_jobs(jobs):
    by_name = {job['name']: job for job in jobs}
    if not all(by_name.get(name, {}).get('conclusion') == 'success' for name in REQUIRED):
        raise ValueError('Required CI jobs did not all pass')


def select_artifact(artifacts):
    matches = [a for a in artifacts if a['name'] == 'tested-images' and not a['expired']]
    if len(matches) != 1:
        raise ValueError('Tested images missing/expired/ambiguous; rerun full CI')
    return matches[0]


def api(path):
    request = urllib.request.Request('https://api.github.com/repos/' + REPO + '/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                 'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != 'refs/heads/main':
        raise SystemExit('Release only from this repository main branch')
    sha = os.environ['GITHUB_SHA']
    query = urllib.parse.urlencode({'head_sha': sha, 'branch': 'main', 'per_page': 100})
    run = select_run(api('actions/workflows/ci.yml/runs?' + query)['workflow_runs'], sha)
    verify_jobs(api(f"actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100")['jobs'])
    artifact = select_artifact(api(f"actions/runs/{run['id']}/artifacts?per_page=100")['artifacts'])
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
        output.write(f"run_id={run['id']}\nartifact_id={artifact['id']}\n")
    print(f"Verified CI run {run['id']} for {sha}; artifact {artifact['id']}")


if __name__ == '__main__':
    main()

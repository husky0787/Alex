# Issue tracker: GitHub

Specs and tasks live in GitHub Issues at https://github.com/husky0787/Alex.
Use the GitHub CLI (`gh`). Pass `--repo husky0787/Alex` explicitly on repository commands; use `repos/husky0787/Alex/` for API paths.

On this Windows workspace, if `gh` is unavailable on PATH, invoke the portable executable at `D:/learn/production/.tools/github-cli/bin/gh.exe`. Other checkouts can use their installed `gh`.

## Authentication

Use the configured GitHub identity with write access to this repository. If authentication is unavailable, preserve the prepared work locally and request sign-in. Keep credentials out of repository files, issue bodies, and command output.

## Operations

- Create: `gh issue create --repo husky0787/Alex --title "..." --body-file <file>`.
- Read: `gh issue view <number> --repo husky0787/Alex --json number,title,body,labels,comments`.
- List: `gh issue list --repo husky0787/Alex --state open --json number,title,body,labels,assignees`; add label filters as needed.
- Update body: `gh issue edit <number> --repo husky0787/Alex --body-file <file>`.
- Comment: `gh issue comment <number> --repo husky0787/Alex --body-file <file>`.
- Labels: `gh issue edit <number> --repo husky0787/Alex --add-label "..."` or `--remove-label "..."`; use `triage-labels.md` for triage roles.
- Close completed work: `gh issue close <number> --repo husky0787/Alex`. Record verification evidence before closing.

Use UTF-8 files with actual newlines for multiline bodies. A request to publish to the tracker means creating a GitHub issue; a request to fetch a ticket means reading its body and comments. Resolve ambiguous bare numbers as an issue or PR before editing, since they share a number space.

## Parent and blocking relationships

Keep the spec as a parent issue and implementation tickets as its sub-issues. Use supported CLI commands or the native API:

- Look up a numeric database ID: `gh api repos/husky0787/Alex/issues/<number> --jq .id`.
- Attach a child: `gh api --method POST repos/husky0787/Alex/issues/<parent>/sub_issues -F sub_issue_id=<child-database-id>`.
- Add a blocker: `gh api --method POST repos/husky0787/Alex/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-database-id>`.

Database IDs differ from issue numbers. If the native relationship is unavailable, record `Part of #<parent>` and `Blocked by: #<number>` in the child, and maintain the parent's task list. Work starts only when all blockers are closed. Closing a child does not automatically authorize closing its parent.

## Pull requests as a triage surface

PRs as a request surface: no.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`, containing Notes, Decisions-so-far, and Fog.
- Children: sub-issues labelled `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`; create these additional labels when that workflow requires them.
- Frontier: the map's open, unassigned children with no open blockers, in map order.
- Claim: assign the selected issue to the authenticated operator before work.
- Resolve: append the answer, close the child, and add a concise linked decision to the map.

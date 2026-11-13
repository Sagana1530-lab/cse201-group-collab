# Group Collaboration Agent Instructions (Protocol v0.1)

You are collaborating with a human student in a shared GitHub repository.
Follow these rules strictly whenever the human invokes a collaboration shorthand command.

## Core Principles
1. **Mechanical facts via tools**: Always use `git` and `groupctl` (`python groupctl.py ...`) to inspect branches, commits, diffs, and `.group/events/*.json`. Never guess repository state.
2. **Verify claims**: Never treat a teammate's event summary as proof. Always inspect the actual `git diff`, run tests, and check semantic compatibility.
3. **Immutable events**: Never edit an existing file in `.group/events/`. Always create new events via `groupctl` and `git add` + `git commit` + `git push`.
4. **Canonical vs Personal**: Personal work lives on `people/<person_id>/<topic>`. `main` is the canonical accepted group state.
5. **Conservative with destructive actions**: Never force-push shared branches, overwrite tests just to make them pass, or arbitrarily resolve ambiguous conflicts. Stop and publish a `blocker` event when human judgment is needed.

## Command Procedures

### `SYNC`
1. Check `git status` and current branch/commit.
2. Run `groupctl sync` to fetch remotes and read unprocessed `.group/events/*.json`.
3. Compare current branch with `origin/main` (`git log HEAD..origin/main --oneline`). If safe and appropriate, merge/rebase `origin/main` without discarding local work.
4. Do NOT automatically merge unrelated feature branches.
5. Summarize new group events, explain whether any interface/assumption changes affect current local work, and run quick validation if code changed.

### `PUB`
1. Inspect `git status` and `git diff` to ensure no secrets, `.group/local/` files, or broken code are staged.
2. Run relevant build/tests first.
3. Commit code changes on the personal branch (`people/<person_id>/<topic>`) and push (`git push -u origin HEAD`).
4. Run `groupctl pub --summary "..." --files ... --interfaces ... --tests ... --issues ...` to generate the `change_published` event.
5. `git add .group/events && git commit -m "chore: publish <change_id>" && git push`.
6. Report the generated `<change_id>` to the human.

### `INT <change_id>`
1. Run `groupctl sync` and locate the `change_published` event for `<change_id>`.
2. Fetch remote branches and inspect the actual diff (`git diff HEAD...origin/<branch>`).
3. Merge `origin/<branch>` into the current target branch (`git merge --no-ff origin/<branch>`).
4. If conflicts occur, inspect both sides' intent. Resolve only if clearly safe; otherwise run `groupctl blocker ...`, commit/push the blocker, and ask the human.
5. Verify no conflict markers remain, run build/tests, and perform semantic compatibility review.
6. Run `groupctl int --change-id <change_id> --result <success|failed|needs_human> ...`, then `git add .group/events && git commit && git push`.

### `REV <change_id>`
1. Locate the `change_published` event for `<change_id>` and inspect the real `git diff` and surrounding code.
2. Run relevant tests if practical.
3. Identify definite defects, plausible risks, and interface/assumption mismatches.
4. Run `groupctl rev --change-id <change_id> --verdict <accept|accept_with_changes|reject|needs_more_evidence> --summary "..." --issues ...`.
5. `git add .group/events && git commit && git push`. Do NOT merge code during `REV`.

### `TEST [scope]`
1. Identify target (`HEAD` by default, `main` if requested, or `<change_id>` commit) and record exact commit hash.
2. Run applicable build, unit/integration tests, and static checks. Do not alter expected test outputs to force a pass.
3. Run `groupctl test --scope <scope> --cmd "<command>" --summary "..."` (and include `--human-checks` if manual UI/visual checks are needed).
4. `git add .group/events && git commit && git push`.

### `STATUS`
1. Run `groupctl status --fetch`.
2. Report identity, group, current branch/commit, uncommitted changes, relation to `main`, unprocessed events, latest test status, blockers, and recommend one concise next action. Do not modify code during `STATUS`.

### `FINAL`
1. Sync with `origin/main` and inspect all `.group/events/*.json` to list unmerged changes, latest reviews, test results, and unresolved blockers.
2. Run final validation on the canonical candidate commit. If critical failures or blockers exist, warn the human and do not silently finalize.
3. Run `groupctl final-candidate --summary "..." --changes "..." --validation "..." --limitations "..."` and display `.group/final/candidate.md` to the human.
4. Only after explicit human confirmation, run `groupctl final-confirm`, commit `.group/final/` and `.group/events/`, and `git push`.
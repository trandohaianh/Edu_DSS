# Personal-data git history remediation plan (C1.2 — PLAN ONLY, NOT EXECUTED)

## Scope

- **Status: PLANNED.** History has **not** been rewritten. C1.2 explicitly forbids rewriting it.
- This document contains **no personal values**. Files are identified by path and commit only.

## 1. Problem statement

- An employee export CSV unrelated to EduDSS was committed under `app/dữ liệu/`. It contains personal data of real people.
- C1.1 removed it from the working tree and the image:
  - `.gitignore`;
  - `.dockerignore`;
  - `test_c1_release_data_hygiene.py`.
- It remains in git history:
  - the canonical CSV path is present in **193 commits**;
  - a raw copy exists in commits `41e4622`, `5ad4d93`, `711d834`, `8f6edf6`, `e7b0ae5`, `ec961f4` and `fe3721a`;
  - **31 branches** reach at least one affected commit.
- Anyone with a clone, a fork, a CI cache, a bundle, or a Docker image built before C1.1 may hold a copy.

Removing a file in a new commit does **not** remove it from history. Only a coordinated rewrite plus invalidation of every copy does.

## 2. Decision owner and preconditions

The rewrite is an irreversible, outward-facing operation. It requires:

1. Written approval from the repository owner, and from the data controller if the university is the controller.
2. Evaluation of whether the exposure is a notifiable personal-data incident under the applicable law, and handling of any notification. This is a legal and privacy decision, outside engineering.
3. A freeze window: announce it, then stop all pushes and merges. The CI and CD workflows are disabled for the duration.
4. **Key rotation is handled separately.** `KEY_ROTATION_REQUIRED = YES` until the owner confirms that the exposed provider keys were rotated. A history rewrite does not un-leak a key.

## 3. Backup before anything

- **Full mirror**: `git clone --mirror <remote> edudss-pre-rewrite.git`. Store it encrypted, offline, access-restricted, and with a deletion date. It contains the personal data, so it is itself sensitive.
- **Portable bundle**: `git bundle create edudss-pre-rewrite.bundle --all`, then check it with `git bundle verify`.
- **Inventory**: record `git for-each-ref` (every branch and tag with its SHA) and the list of open PRs.
- **Retention**: delete the pre-rewrite mirror and bundle once the rewrite is verified and the retention period agreed with the data controller has elapsed. Record who deleted them and when.

## 4. Rewrite method

- **Tool**: `git filter-repo`. It is the maintained tool that git recommends; do not use `filter-branch`.
- **Where**: on a fresh mirror clone, never on a working clone.
- **Command**:

  ```
  git filter-repo --invert-paths --path "app/dữ liệu/" --path-glob "**/nhanvien_export*.csv"
  ```

  Add every path of the raw copies, found with the listing below, before running it.
- **Finding every copy by content**: list each blob, whatever its name.

  ```
  git rev-list --all --objects | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)'
  ```

  Then filter by the CSV header signature, and also remove those blob IDs with `--strip-blobs-with-ids`.
- **Tags**: `filter-repo` rewrites all refs, including tags. Signed tags lose their signatures and must be re-signed.
- **Side effects**: `filter-repo` expires the reflog and gc's the rewritten mirror, so the old objects are gone locally.

## 5. Verification (before any push)

All of the following must hold on the rewritten mirror:

- `git log --all -- "app/dữ liệu"` is empty.
- A blob scan (the content-signature search from §4 over `git rev-list --all --objects`) finds nothing.
- `git grep` of the header signature over `$(git rev-list --all)` finds nothing.
- `python tools/secret_scan.py --history` is clean.
- The branch and tag count matches the inventory, and the tip trees are identical to before except for the removed paths: compare `git diff <old-tip> <new-tip> --stat` per branch.
- A CI run on the rewritten mirror, in a private fork, passes.

## 6. Force-push and remote impact

- Temporarily lift branch protection on the protected branches, then force-push:

  ```
  git push --force --mirror
  ```

  Afterwards, re-enable protection.
- **GitHub specifics**: old commits remain reachable by SHA through cached views, forks and PR refs (`refs/pull/*`), which cannot be force-pushed.
  - Open a GitHub Support request to purge cached views and dangling objects for the listed SHAs.
  - Ask the owners of forks to delete their forks.
- **Open PRs** must be recreated against the rewritten history, because their base SHAs change.
- **Collaborators**: send a notice that says:
  - every SHA changed;
  - `git pull` must not be used;
  - they must re-clone, and must not push old branches, because that would reintroduce the data. Pre-receive checks or a CI secret or data scan on push catch mistakes.

## 7. Invalidating old copies

| Copy | Action |
|---|---|
| Developer clones, including other worktrees | delete them and re-clone. Confirm per person |
| CI caches and artifacts | delete the Actions caches and the artifacts of old runs |
| Git bundles and backups | delete them, except the encrypted pre-rewrite mirror (§3) until its deletion date |
| Docker images built before C1.1 | the `.dockerignore` fix is from C1.1, so older images may contain the CSV.<br>• Delete them locally: `docker image ls`, then `docker image rm`.<br>• Delete them in every registry: both tags and digests, then run registry garbage collection.<br>• Record the deleted digests |
| Deployed containers or hosts running old images | redeploy from a post-C1.1 digest, then prune the old image |
| Exports, zips and documents that embedded the CSV | search the shared drives and delete |

## 8. After the rewrite

- Keep `test_c1_release_data_hygiene.py`, the `.gitignore`/`.dockerignore` rules and the secret/data scans in CI. They prevent re-introduction.
- Record in the release notes that history was rewritten, with the date and the new root SHAs. Do not describe the data.
- Close the incident record with the verification evidence from §5 and the invalidation checklist from §7.

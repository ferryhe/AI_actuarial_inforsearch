# Gitee Mirror Sync

This repository syncs `main` to Gitee with `.github/workflows/sync-gitee.yml`.

## Required GitHub Secrets

Create these repository secrets in GitHub:

- `GITEE_SSH_PRIVATE_KEY`: a private SSH key with write access to `git@gitee.com:jghe/AI_actuarial_inforsearch.git`.
- `GITEE_KNOWN_HOSTS`: pinned SSH host keys for `gitee.com`.

Do not store these values in the repository.

## Setup

1. Create a dedicated SSH key for this sync job.
2. Add the public key to the Gitee repository with write access.
3. Add the private key as the GitHub secret `GITEE_SSH_PRIVATE_KEY`.
4. Add the Gitee SSH host keys as the GitHub secret `GITEE_KNOWN_HOSTS`.
5. Keep the Gitee `main` branch history aligned with GitHub `main`; the workflow uses a normal push and intentionally does not force-push.

The workflow runs after every push to GitHub `main` and can also be run manually with `workflow_dispatch`.

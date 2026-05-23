# Gitee Mirror Sync

This repository syncs `main` to Gitee with `.github/workflows/sync-gitee.yml`.

## Required GitHub Settings

Create these settings in the GitHub repository:

- Repository secret `GITEE_TOKEN`: a Gitee token with write access to `https://gitee.com/jghe/AI_actuarial_inforsearch`.
- Repository variable `GITEE_USER`: the Gitee username, currently `jghe`.

Do not store these values in the repository.

## Setup

1. Create or choose a Gitee token for `jghe` with repository write access.
2. Add that token as the GitHub repository secret `GITEE_TOKEN`.
3. Add `jghe` as the GitHub repository variable `GITEE_USER`.
4. Make sure the Gitee repository exists. If its `main` branch was initialized separately, the workflow will fetch it first and then update `main` with `--force-with-lease` so the mirror can converge without exposing the token in the remote URL.

The workflow runs after every push to GitHub `main` and can also be run manually with `workflow_dispatch`.

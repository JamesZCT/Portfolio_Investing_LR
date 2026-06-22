# Public / Private Split

This repository is intended to be safe as a public demo and reusable research lab.

## Public Repository

Keep these in the public repo:

- Application code.
- Example configurations such as `example_config.yaml` and `example_hk_config.yaml`.
- Public demo snapshot JSON.
- Documentation and setup runbooks.
- Portfolio templates and benchmark comparison logic.

Public workflows must use only example configs. They should not consume private holdings from `PORTFOLIO_CONFIG_YAML` or any brokerage export.

## Private Portfolio Layer

Keep these in a private repo, private GitHub secret, or local-only file:

- Real holdings and target weights.
- Brokerage exports.
- Tax lots, account balances, cash balances, and account IDs.
- API tokens and notification secrets.
- Personal notes that reveal investment intent or position sizing.

The private layer can reuse this project as a template, submodule, or package. It can then run the same snapshot exporter with private config and publish to a private destination.

## Self-Hosted Runner Safety

The RTX 3090 Ti self-hosted runner should only run trusted workflows:

- `schedule` events from `main`.
- Manual `workflow_dispatch` runs by a repository maintainer.

Do not add `pull_request` triggers to workflows that run on `[self-hosted, windows, local-llm]`. Public pull requests must stay on GitHub-hosted runners.

## Publication Checklist

Before making this repository public:

- Confirm `config.yaml` is ignored and absent from git history.
- Confirm generated `web/public/data/*.json` is public demo data only.
- Confirm public workflows do not read `PORTFOLIO_CONFIG_YAML`.
- Confirm self-hosted workflows do not run on pull requests.
- Scan for secrets in the current tree and git history.


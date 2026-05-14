---
inclusion: always
---

# Build Standards and Tooling

## Dependency Management
- Use **uv** (https://docs.astral.sh/uv/) for all Python dependency management
- Use `pyproject.toml` (not `requirements.txt`) as the project manifest
- Pin all dependencies with exact versions in `uv.lock`
- Separate dev dependencies from runtime dependencies using `[dependency-groups]`

## Code Quality
- Use **ruff** (https://astral.sh/ruff) for Python linting and formatting
- Use **mypy** (https://www.mypy-lang.org/) for static type checking
- All Python code must have type annotations
- ruff and mypy must pass with zero errors before any commit

## TypeScript Code Quality
- Use **typescript-eslint** (https://typescript-eslint.io/) for TypeScript linting (`infra/`)
- Use **Prettier** (https://prettier.io/) for TypeScript formatting (`infra/`)
- ESLint config: `infra/eslint.config.mjs` (flat config, strict typed rules + `eslint-config-prettier`)
- Prettier config: `infra/.prettierrc.json` (single quotes, 100-char print width, trailing commas)
- typescript-eslint and Prettier must pass with zero errors before any commit

## Infrastructure as Code
- Use **CDK TypeScript** for all AWS infrastructure definitions
- All AWS resources required to provision the solution must be defined in CDK code
- CDK stacks must be tested (using `aws-cdk-lib/assertions`)
- Infrastructure lives in the `infra/` directory
- Apply **cdk-nag** (`AwsSolutionsChecks`) as a CDK Aspect in every stack to enforce AWS Solutions best-practice rules at synth time
- Use `NagSuppressions` to document and suppress accepted risks with a clear justification comment
- Run **checkov** against the synthesised CloudFormation output (`infra/cdk.out/`) to catch IaC misconfigurations and CIS/NIST policy violations

## Pre-commit Checks
The pre-commit hook must run all of the following in order:
1. `make precommit`
1. Conventional commit message validation

## Versioning and Commits
- Use **semantic versioning** (SemVer) for all releases
- Use **Conventional Commits** (https://www.conventionalcommits.org/en/v1.0.0/) for all commit messages
  - Format: `<type>(<scope>): <description>`
  - Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `ci`
- Small, frequent commits following DevOps principles

## Build Automation
- Use **GNU Make** (`Makefile`) for all build, test, and deploy actions
- The default target (`make` with no arguments) must print a help message listing all available targets
- Document every target with a `## description` comment on the same line — the help target auto-generates output from these comments
- **AWS credentials for local development**: define `MAYBE_SOURCE` at the top of the Makefile using `$(wildcard session-environment.sh)` and `$(if ...)`, then prefix any AWS-touching recipe with `$(MAYBE_SOURCE)` so credentials are sourced in the same subshell as the command — no cross-subshell export issues
- `session-environment.sh` must export `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, and `AWS_DEFAULT_REGION=us-east-1` (Nova 2 Sonic is only available in us-east-1, us-west-2, and ap-northeast-1)
- `session-environment.sh` must be listed in `.gitignore` — it must never be committed
- Standard targets must include:
  - `make install` — install all dependencies via uv
  - `make lint` — run ruff check + mypy (Python)
  - `make lintfix` — run ruff with automated fixing of issues and formatting
  - `make secscan` - run both semgrep and bandit security scanners
  - `make format` — run ruff format (Python)
  - `make tslint` — run typescript-eslint on `infra/` TypeScript source
  - `make tsformat` — run Prettier on `infra/` TypeScript source
  - `make test` — run pytest
  - `make test-unit` — run unit tests only (exclude integration)
  - `make synth` — run cdk synth
  - `make deploy` — run cdk deploy
  - `make cdknag` — run cdk-nag AwsSolutions checks against the CDK stack
  - `make checkov` — run checkov IaC security scan against the synthesised CloudFormation template
  - `make precommit` — run full pre-commit suite (lint + format + security + type check, Python + TypeScript)
  - `make clean` — remove build artifacts

## Source Control and CI/CD
- Remote: https://github.com/digitizdat/writer-tools.git
- Use **GitHub Actions** for CI/CD automation
  - CI workflow: triggered on push/PR, runs `make precommit` and `make test`
  - Deploy workflow: triggered on release tag, runs `make deploy`
- Workflows call Make targets (not raw commands) to keep CI/CD DRY

## Task Completion
Prior to completing a task, run `make precommit` and `make test` and fix any issues that emerge until both `make precommit` and `make test` run clean.
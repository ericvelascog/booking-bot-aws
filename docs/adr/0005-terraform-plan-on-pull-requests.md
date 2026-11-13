# ADR-0005: `terraform plan` on pull requests, with a read-only role

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

CI checks that the Terraform code is formatted, valid and free of known misconfigurations, but not what it would do to AWS. A one-line change can replace a database or delete a load balancer, and that only shows up in `terraform plan`, which until now ran on my PC. The reviewer of a pull request should see the plan next to the code.

Running the plan in GitHub Actions needs AWS credentials, and that is the hard part. A `pull_request` workflow runs the version of the workflow **from the pull request's branch**. Whoever can open a pull request in this repository decides what code runs with those credentials.

## Options considered

1. **Keep planning locally.** Free and simple, but the plan is not part of the review, and nothing proves it was run.
2. **A Terraform automation server** (Atlantis, HCP Terraform). Plans and applies from pull request comments, with locking and policies. But it means a server to run and secure, or a paid plan, for a one-person project.
3. **A GitHub Actions workflow with its own read-only OIDC role.** No stored keys and no server. For the role's permissions:
   - **a custom list** of the `Describe`/`Get`/`List` actions that Terraform needs. This is the tightest, but it is long, and it breaks with every new resource type until someone adds the missing action;
   - **AWS's `ReadOnlyAccess` plus an explicit `Deny` on reading data.** It reads the configuration of anything. A `Deny` always wins over an `Allow`, so it can never read the contents that `ReadOnlyAccess` would otherwise allow: app secrets, logs, table items, audit logs.

## Decision

Option 3, with `ReadOnlyAccess` plus explicit denies ([`github-oidc.tf`](../../infra/bootstrap/github-oidc.tf), role `booking-bot-github-plan`), and the workflow [`plan.yml`](../../.github/workflows/plan.yml):

- **Who:** the trust policy accepts only tokens whose subject is this repository's `pull_request`, matched with the immutable owner and repository IDs. GitHub does not issue OIDC tokens to pull requests from forks.
- **What it cannot do:** change anything (no write actions in `ReadOnlyAccess`), or read the bot's secrets in SSM, log events (they contain phone numbers), DynamoDB items, or CloudTrail's files and event history. All of this was checked with the IAM policy simulator: 7 reads the plan needs are allowed, 8 data reads are explicitly denied and 4 writes are implicitly denied.
- **No lock:** `plan -lock=false`, because the role cannot write the lock file. A plan changes nothing, so it does not need the lock.
- **The output is public** (public repository): Terraform already hides sensitive values, such as the origin secret and the alert email, now marked `sensitive`. The script also replaces the account ID with `***` in the comment. In the logs, the role ARNs are repository secrets, so GitHub masks them, and the AWS login step masks the account ID everywhere else ([troubleshooting #010](../troubleshooting.md)).
- **`edge` is skipped while `app` is down**, because it reads the app's load balancer and has nothing to compare against.
- **One comment per pull request**, edited on every push, with a summary table and each stack's plan in a collapsible section.
- **Not a required check.** The workflow only runs when `infra/` changes, and GitHub would block every other pull request waiting for a required check that never runs. The plan is information for the reviewer. Format, validation and the security scan remain the gates.

## Consequences

- Every infrastructure pull request shows what it would create, change or destroy, and a `destroy` gets a ⚠️ in the summary.
- Anyone who can open a pull request here can read the configuration of the account, the Terraform state and the origin secret. Today that is only me. The origin secret only proves that traffic comes through CloudFront.
- The role reads more than the plan strictly needs, for example the configuration of services that this project does not use.
- `apply` is still manual, from my PC, after the merge.
- **In production** I would:
  - generate a custom read-only policy from the actions that CloudTrail records during real plans;
  - make the plan a required check;
  - require an approving review from someone else;
  - run `apply` from the pipeline after the merge, with a separate role that only the `main` branch can assume.

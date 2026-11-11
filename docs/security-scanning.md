# Security scanning

Every pull request is scanned for security misconfigurations, and the merge is blocked if anything is found that has not been fixed or accepted with a reason. This page lists what is scanned and the decision taken on each finding.

## What runs, and when

| Scanner | What it checks | When |
|---|---|---|
| [checkov](https://www.checkov.io/) | Terraform (`infra/`), the Dockerfile, the GitHub Actions workflows, and secrets committed by mistake | Every pull request, CI job `Security scan (checkov)` ([`ci.yml`](../.github/workflows/ci.yml)) |
| [Trivy](https://trivy.dev/) | Known vulnerabilities (CVEs) in the image: the Debian packages and the Python libraries. Fails on any `HIGH` or `CRITICAL` that already has a fix | Every pull request, in the `App` job, right after `docker build` |
| ECR image scanning | Known vulnerabilities in the image's OS packages | Every image push |
| Dependabot | New versions of the GitHub Actions used by the workflows | Monthly, as one pull request |

The versions of checkov and Trivy are pinned in the workflow. A new version brings new rules, so upgrading is a pull request of its own, not a surprise failure on an unrelated change.

Trivy ignores vulnerabilities that have no fix yet (`ignore-unfixed`). Nothing can be done about them in this repository, and they would block every pull request. ECR's scan still reports them.

## First scan: 35 findings

The first scan (2026-11-11, checkov 3.4.3) passed 302 checks and failed 35: 34 in Terraform, 1 in the Dockerfile, none in the workflows and no secrets. 4 were fixed and 31 were accepted.

### Fixed

| Check | Resource | Change |
|---|---|---|
| `CKV_AWS_131` | ALB | Drops HTTP headers with invalid names (`drop_invalid_header_fields`), a free defence against request smuggling. |
| `CKV2_AWS_12` | VPC default security group | Managed by Terraform with no rules, so it blocks all traffic. Nothing uses it, but anything created without a security group would get it. |
| `CKV2_AWS_32` | CloudFront | Adds AWS's managed security headers policy to every response: `Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options` and `Referrer-Policy`. |
| `CKV2_AWS_61` | Terraform state bucket | Lifecycle rule: old versions expire after 90 days, always keeping the 10 newest of each file. Without it, versioning keeps every old state forever, and every lock file too (each `plan` or `apply` creates and deletes one). |

### Accepted, with a reason

Each accepted finding has an inline `# checkov:skip=<check>:<reason>` comment on the resource, so the reason is reviewed together with the code and printed in the scan output. They fall into five groups.

**1. No own domain (6).** Viewers use HTTPS on CloudFront's default `*.cloudfront.net` certificate. The ALB has no certificate, because ACM certificates need a domain, so the CloudFront → ALB hop and the ALB → task hop are HTTP ([ADR-0002](adr/0002-cloudfront-edge-stack.md)). With the default certificate, CloudFront does not allow choosing the minimum TLS version either.
`CKV_AWS_2`, `CKV_AWS_103`, `CKV2_AWS_20`, `CKV_AWS_378`, `CKV_AWS_174`, `CKV2_AWS_42`

**2. Fixed monthly cost (12).** The budget is $10 a month and the app stack runs about two hours per session, so controls with a fixed monthly price were left out:
- *Customer managed KMS keys* for DynamoDB, CloudWatch Logs, ECR, SSM, S3 and SNS. Everything is already encrypted at rest with keys owned or managed by AWS. A customer managed key ($1 a month each) adds control over who can decrypt, through the key policy, and an audit trail of every use. For SNS there is also a technical reason: CloudWatch cannot publish to a topic encrypted with the AWS managed key `aws/sns`.
  `CKV_AWS_119`, `CKV_AWS_158`, `CKV_AWS_136`, `CKV_AWS_337`, `CKV_AWS_145`, `CKV_AWS_26`
- *WAF* on CloudFront and on the ALB. CloudFront includes AWS Shield Standard (DDoS protection), and the ALB only accepts CloudFront with the secret origin header. The Log4j rule does not apply to a Python app.
  `CKV_AWS_68`, `CKV2_AWS_28`, `CKV2_AWS_47`
- *A second region*: replication of the state bucket and CloudFront origin failover. The state is protected by versioning and `prevent_destroy`.
  `CKV_AWS_144`, `CKV_AWS_310`
- *NAT Gateway* (about $35 a month): tasks have a public IP for outbound calls, and their security group only accepts the ALB ([ADR-0001](adr/0001-public-subnets-without-nat.md)).
  `CKV_AWS_333`

**3. Extra logs (5).** ALB access logs, CloudFront logs, S3 access logs, VPC flow logs and Container Insights. The app already logs every request it receives to CloudWatch, and the alarms use the ALB metrics. In production these logs would go to a central log archive account.
`CKV_AWS_91`, `CKV_AWS_86`, `CKV_AWS_18`, `CKV2_AWS_11`, `CKV_AWS_65`

**4. Design decisions (3).**
- No deletion protection on the ALB: the stack is destroyed after every session on purpose, and protection would block `terraform destroy`. `CKV_AWS_150`
- Logs are kept for 7 days, not one year: they contain phone numbers, so they are kept no longer than needed (GDPR data minimisation). `CKV_AWS_338`
- No point-in-time recovery on the sessions table: conversations expire after 6 hours and the bookings live in Google Calendar, so there is nothing to restore ([ADR-0003](adr/0003-stateless-sessions-in-dynamodb.md)). `CKV_AWS_28`

**5. Does not apply (5).**
- *False positive:* the ALB's port 80 rule is flagged as open to `0.0.0.0/0`, but its source is CloudFront's managed prefix list. checkov cannot resolve the list, so the rule was checked by hand. `CKV_AWS_260`
- No default root object on CloudFront: this is an API, not a website. `CKV_AWS_305`
- No geo restriction: the callers are Meta's and VAPI's servers, often outside Spain, so blocking countries would break the webhooks. `CKV_AWS_374`
- No event notifications on the state bucket: nothing needs to react when the state changes. `CKV2_AWS_62`
- No `HEALTHCHECK` in the Dockerfile: ECS ignores it, and the ALB checks `GET /health` every 30 seconds. `CKV_DOCKER_2`

## First Trivy scan: 5 vulnerabilities

Trivy's first run (2026-11-11, Trivy 0.76.2) failed the pull request that added it. It found 5 `HIGH` vulnerabilities, all with a fix available, and all 5 were fixed:

| Package | Vulnerabilities | Cause | Fix |
|---|---|---|---|
| `zlib1g` (Debian) | 2 × `HIGH` | Debian had already published the fix, but the official `python:3.12-slim` image had not been rebuilt with it yet. | The Dockerfile now runs `apt-get upgrade` on top of the base image, so Debian security fixes are in every build without waiting for the official image. |
| `starlette` 0.38.6 (Python) | 3 × `HIGH` (CVE-2024-47874, CVE-2026-48818, CVE-2026-54283) | FastAPI 0.115.0 required an old Starlette. | FastAPI upgraded to 0.162.4, which brings Starlette 1.10.0. The 25 tests pass. |

None of the Starlette issues could be exploited in this app as it is: they affect form parsing and `StaticFiles`, and the bot only receives JSON. But upgrading took less time than proving that, and the next change to the app could have made one of them reachable.

## The pipeline is part of the attack surface

In March 2026, attackers took over Trivy's own GitHub Action and moved almost all of its version tags to malicious code that stole the secrets of the pipelines running it ([CVE-2026-33634](https://github.com/advisories/GHSA-69fq-xp46-6x23)). Every workflow that referenced a tag ran the attacker's code. So:

- **Every action is pinned to a full commit SHA**, with the version as a comment: `actions/checkout@3d3c42e… # v7.0.1`. A tag can be moved to other code; a commit cannot. When they were pinned, each major tag pointed to the same commit as its latest release, so the pinning changed nothing that runs.
- **Dependabot keeps the pins up to date.** Without it, pinned actions would never get security fixes. Its pull requests go through CI like any other change.
- **Scanners run where there is nothing to steal.** checkov and Trivy run in the CI workflow, on pull requests, with a read-only token and no AWS credentials or secrets. Only the Deploy workflow, on `main`, can get AWS credentials, and it runs no third-party scanners.
- Trivy is pinned to `trivy-action` v0.36.0 (April 2026, after the incident), which pins its own dependencies by commit, and to Trivy v0.76.2.

## Rules for skipping a check

- Every skip has a reason in the comment and an entry on this page.
- A skip is reviewed in the pull request like any other change.
- A skip is never used to get a pull request through. If a finding cannot be fixed in that pull request and has no good reason to be accepted, it is fixed first.

## In production

The first accepted findings I would turn into fixes are: a domain with ACM certificates and HTTPS end to end (group 1), WAF with AWS managed rules (group 2), one customer managed key per data classification, not one per resource (group 2), and the extra logs shipped to a log archive account (group 3).

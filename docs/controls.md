# IT General Controls (ITGC) mapping

How this project implements the classic ITGC domains (access, change management, operations) in a cloud setting. For each control there is the evidence an auditor could inspect, and the gaps I know about.

> Scope: a portfolio project run by one person. Some controls that need a second person (segregation of duties, access reviews) are listed as gaps, together with how they would be implemented in a team.

## 1. Logical access

| ID | Control objective | Implementation | Evidence |
|---|---|---|---|
| AC-01 | No long-lived credentials | No IAM user has access keys. The CLI uses `aws login`, which issues temporary credentials. CI/CD authenticates with GitHub OIDC and gets credentials that expire after one hour. | IAM → Users → Security credentials; [`infra/bootstrap/github-oidc.tf`](../infra/bootstrap/github-oidc.tf) (`max_session_duration`) |
| AC-02 | Strong authentication for privileged users | MFA is enabled on the root user and on the administrator user. Root is not used for day-to-day work. | IAM → `AccountMFAEnabled = 1`; IAM user `iamadmin` → MFA device |
| AC-03 | Least privilege for workloads | The ECS execution role can only pull from this ECR repository, write to this log group and read `/booking-bot/*` in SSM. The task role can only get, put and delete items in the sessions table (no `Scan`, no other tables), verified with the IAM policy simulator. | [`infra/app/iam.tf`](../infra/app/iam.tf); `aws iam simulate-principal-policy` results in PR #13 |
| AC-04 | Least privilege for automation | The deploy role can only push to this ECR repository, update this ECS service and pass the two app roles to ECS. | [`infra/bootstrap/github-oidc.tf`](../infra/bootstrap/github-oidc.tf) (`github_deploy` policy) |
| AC-05 | Only authorised identities can assume the deploy role | The trust policy accepts only OIDC tokens from this repository's `main` branch, matched on the immutable subject (owner and repository IDs), so a fork or a re-created repository with the same name is rejected. | `github_assume` policy document; [troubleshooting #004](troubleshooting.md) |
| AC-06 | Secrets are protected | Secrets are stored as SSM `SecureString` (KMS-encrypted). They are excluded from Git (`.gitignore`), from the image (`.dockerignore`) and from the Terraform state, because they are uploaded with a script. Only the execution role can read them. | [`scripts/put-secrets.ps1`](../scripts/put-secrets.ps1), [`app/.dockerignore`](../app/.dockerignore), [`.gitignore`](../.gitignore) |
| AC-07 | Network access is restricted | Public traffic enters only through CloudFront (HTTPS). The ALB accepts only CloudFront's managed prefix list and returns `403` without the secret origin header. Tasks accept inbound traffic only from the ALB security group on the app port, and outbound only on 443. | [`infra/app/security.tf`](../infra/app/security.tf), [`infra/app/alb.tf`](../infra/app/alb.tf), [ADR-0002](adr/0002-cloudfront-edge-stack.md) |
| AC-08 | Escalation of privileges is prevented | `iam:PassRole` is limited to the two app roles and to `ecs-tasks.amazonaws.com`, so the pipeline cannot attach a more powerful role to a task. | `PassOnlyTheAppRoles` statement |

**Gaps:** there is no periodic access review, and no IAM Identity Center or permission sets (single administrator user). In a team I would add Identity Center with role-based permission sets and a quarterly access review.

## 2. Change management

| ID | Control objective | Implementation | Evidence |
|---|---|---|---|
| CM-01 | Every change to production is authorised and recorded | `main` is protected: changes enter only through pull requests, with no exceptions for administrators. Force pushes and branch deletion are blocked. | GitHub → Settings → Branches; pull request history |
| CM-02 | Changes are tested before release | Required status checks on every pull request: lint, unit tests and image build for the app, `terraform fmt` and `validate` for the infrastructure, and a security scan (CM-07). A failing check blocks the merge. | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml); closed PR #5 (deliberately broken test, merge blocked) |
| CM-03 | Infrastructure changes are controlled | All infrastructure is defined in Terraform and changed through pull requests. `terraform plan` is reviewed before every `apply`. No manual changes are made in the console. | [`infra/`](../infra), remote state in S3 (versioned) |
| CM-04 | What runs in production is traceable to source | Images are tagged with the commit SHA. ECR tags are immutable. Each deployment is a new task definition revision, and `/health` reports the running version. | ECR image tags; ECS task definition revisions; `GET /health` |
| CM-05 | Deployments are automated and reversible | Deployments run only from `main`, through the Deploy workflow (no manual deploys). Rolling deployment with the circuit breaker rolls back automatically if the new version fails health checks. | [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml); `deployment_circuit_breaker` in [`infra/app/ecs.tf`](../infra/app/ecs.tf) |
| CM-06 | Design decisions are documented | Significant architecture decisions are recorded as ADRs with the options considered and their consequences. | [`docs/adr/`](adr) |
| CM-07 | Security misconfigurations are caught before release | checkov scans the Terraform, the Dockerfile, the workflows and the repository (for secrets) on every pull request, as a required check. Findings are fixed, or accepted with a written reason that is reviewed in the pull request. | `Security scan (checkov)` job in [`ci.yml`](../.github/workflows/ci.yml); [`docs/security-scanning.md`](security-scanning.md) |
| CM-08 | The CI/CD pipeline's own dependencies are controlled | Every GitHub Action is pinned to a full commit SHA, so a moved tag cannot change what runs. Dependabot proposes updates monthly through pull requests. Third-party scanners run only in the CI workflow, which has no AWS credentials or secrets. | `uses:` lines in [`.github/workflows/`](../.github/workflows); [`.github/dependabot.yml`](../.github/dependabot.yml); [`docs/security-scanning.md`](security-scanning.md#the-pipeline-is-part-of-the-attack-surface) |

**Gaps:** there is no segregation of duties, because the same person writes, reviews and merges. In a team I would require an approving review from someone other than the author (with `CODEOWNERS` for `infra/`) and post `terraform plan` on every pull request. The plan-on-PR part is already on the roadmap.

## 3. Operations

| ID | Control objective | Implementation | Evidence |
|---|---|---|---|
| OP-01 | Service health is monitored and failures are recovered | The ALB checks `/health` every 30 s. ECS runs two tasks in two AZs, replaces unhealthy or stopped tasks, and autoscales between 2 and 4. The service is stateless (conversations in DynamoDB), so losing a task loses no data. Tested by stopping a task under traffic, with zero failed requests. | Target group health check in [`infra/app/alb.tf`](../infra/app/alb.tf); [`infra/app/autoscaling.tf`](../infra/app/autoscaling.tf); README → *Resilience, tested* |
| OP-02 | Application activity is logged | Container output goes to CloudWatch Logs with 7-day retention. | `/ecs/booking-bot` log group |
| OP-03 | Critical configuration data is protected against loss | The Terraform state bucket is versioned and encrypted, blocks public access and has `prevent_destroy`. | [`infra/bootstrap/main.tf`](../infra/bootstrap/main.tf) |
| OP-04 | Vulnerabilities in deployed software are identified | Trivy scans the image on every pull request and blocks the merge on any `HIGH` or `CRITICAL` vulnerability that has a fix. ECR scans every image again on push, and every build pulls the latest base image so OS patches are picked up. | Trivy step in [`ci.yml`](../.github/workflows/ci.yml); ECR scan findings; `--pull` in the Deploy workflow |
| OP-05 | Cost is monitored | An AWS Budget alerts at 50 % and 100 % of $10/month (actual) and at 100 % (forecast). Credits are excluded, so usage is visible even while credits pay for it. | Billing → Budgets → `monthly-cost-10usd` |
| OP-06 | Incidents are analysed and lessons recorded | Every real problem is written down with symptom, diagnosis, root cause, fix and lesson. | [`docs/troubleshooting.md`](troubleshooting.md) |
| OP-07 | Failures are detected and someone is notified | CloudWatch alarms on 5xx responses, unhealthy tasks and failed WhatsApp replies (log metric filter) email the operator through SNS, on alarm and on recovery. Each alarm links to a runbook section. The alarms were tested by triggering them. | [`infra/app/alarms.tf`](../infra/app/alarms.tf), [`docs/runbook.md`](runbook.md) |

**Gaps:** there is no dedicated CloudTrail trail (only the default 90-day event history), and alerts go to a single person's email, with no on-call rotation. A CloudTrail trail is on the roadmap.

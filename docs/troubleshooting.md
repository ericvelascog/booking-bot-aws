# Troubleshooting log

Real problems found while building this project, written down right after fixing them.

<!--
## NNN — Short title (YYYY-MM-DD)
- **Symptom:** what I saw (error message, behaviour)
- **Diagnosis:** how I narrowed it down (logs, commands, console)
- **Root cause:** what was actually wrong
- **Fix:** what I changed
- **Lesson:** what I'd check first next time
-->

## 001 — `docker` is not recognized right after installing Docker Desktop (2026-09-30)
- **Symptom:** `docker build` in PowerShell failed with *"El término 'docker' no se reconoce como nombre de un cmdlet..."* (CommandNotFoundException).
- **Diagnosis:** checked the system `PATH` stored in the registry: `C:\Program Files\Docker\Docker\resources\bin` was there, so the install was fine.
- **Root cause:** the PowerShell window had been opened *before* installing Docker. A shell reads `PATH` only once, at startup, so it never saw the new entry.
- **Fix:** closed and reopened PowerShell; `docker build` worked.
- **Lesson:** after installing any CLI tool, open a new terminal before assuming the install failed.

## 002 — App crashes on startup when `.env` has variables Settings doesn't declare (2026-10-06)
- **Symptom:** the first test run stopped before any test ran: `ValidationError ... google_credentials_content: Extra inputs are not permitted`, raised from `config.py`.
- **Diagnosis:** the same image had started fine with `docker run --env-file`. The difference: tests mount `app/` (including `app/.env`), so pydantic-settings *read the .env file*; in the container the values arrive as environment variables and there is no `.env` file inside the image.
- **Root cause:** pydantic-settings rejects unknown keys found in the `.env` file by default. `GOOGLE_CREDENTIALS_CONTENT` (added for container use) is read directly by `calendar_service.py`, so it was not declared in `Settings`. Running the app outside Docker with that `.env` would have crashed too.
- **Fix:** `extra="ignore"` in `Settings.model_config`.
- **Lesson:** "works in the container" is not "works everywhere": config can be loaded from several sources (env vars vs. `.env` file) with different rules. Tests that run the code a different way catch this.

## 003 — `docker login` to ECR fails with `400 Bad Request` in Windows PowerShell (2026-10-09)
- **Symptom:** `aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <registry>` returned `login attempt to https://<registry>/v2/ failed with status: 400 Bad Request`.
- **Diagnosis:** the AWS session was valid and the token was issued (2238 characters, same region as the registry). Running the *exact same pipeline* inside `cmd /c "..."` returned `Login Succeeded`, so the token was fine and the pipe was the difference.
- **Root cause:** Windows PowerShell 5.1 does not pass bytes between two native programs untouched: it decodes the first program's output to text and re-encodes it (encoding + trailing newline) before writing it to the second one's stdin. The registry token arrives altered and is rejected.
- **Fix:** run the pipe through cmd: `cmd /c "aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <registry>"`. (PowerShell 7.4+, Git Bash and the Linux CI runners pass bytes as-is.)
- **Lesson:** when a credential works in one shell and not in another, suspect how the shell transports it, not the credential.

## 004 — Deploy workflow: `Not authorized to perform sts:AssumeRoleWithWebIdentity` (2026-10-14)
- **Symptom:** the first run of the Deploy workflow failed at *Log in to AWS with OIDC* with `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`.
- **Diagnosis:** the role, the OIDC provider and the audience (`sts.amazonaws.com`) were correct, so the suspect was the trust-policy condition on the token's `sub` claim. `gh api repos/ericvelascog/booking-bot-aws/actions/oidc/customization/sub` showed `"use_immutable_subject": true` and the prefix `repo:ericvelascog@234643949/booking-bot-aws@1397462375`.
- **Root cause:** GitHub issues the token with an *immutable subject* (owner and repository names plus their numeric IDs). The trust policy expected the classic `repo:ericvelascog/booking-bot-aws:ref:refs/heads/main`, so the `StringEquals` condition never matched.
- **Fix:** trust condition set to `repo:ericvelascog@234643949/booking-bot-aws@1397462375:ref:refs/heads/main`. This is also safer: a repository recreated with the same name gets a new ID and is rejected.
- **Lesson:** for OIDC trust policies, check the exact claims the identity provider sends instead of copying the format from older docs.

## 005 — `aws login` always fails with `TOKEN_EXPIRED`, even after a fresh sign-in (2026-11-06)
- **Symptom:** after three weeks away, Terraform and the AWS CLI failed to refresh credentials. A new `aws login` (also `--remote`, from a private window with a fresh console session) completed in the browser but the CLI returned `AccessDeniedException ... CreateOAuth2Token: The refresh token has expired (TOKEN_EXPIRED)`.
- **Diagnosis:** the old login cache had been cleared (`aws logout`) and the console session was new, so an expired token was unlikely. I compared the PC clock with the `Date` header of `https://signin.aws.amazon.com`: the PC was **115 s behind**.
- **Root cause:** clock skew. The login flow sends short-lived, time-stamped proofs signed with the local clock; with almost two minutes of drift they arrive already "expired". The error message points at the token, not at the clock.
- **Fix:** enabled automatic time and synced the Windows clock (drift 0 s), then `aws login` worked at the first try.
- **Lesson:** when credentials are rejected as expired right after being issued, check the clock before anything else.

## 006 — First real WhatsApp message on AWS: the bot answers "ha ocurrido un error" (2026-11-07)
- **Symptom:** after pointing the Meta webhook at CloudFront, the verification passed, but the first real message got the bot's generic fallback reply: *"Lo siento, ha ocurrido un error..."*.
- **Diagnosis:**
  - `aws logs tail /ecs/booking-bot --since 20m` showed `GET /webhook ... 200` (Meta's verification) and `POST /webhook ... 200` (the message). The whole path, Meta → CloudFront → ALB → Fargate, worked.
  - The next line explained the failure: `Error code: 401 ... authentication_error, invalid x-api-key` from the Anthropic API.
  - I compared the key stored in SSM with the one in `app/.env` by SHA-256 fingerprint, without printing either. They were identical and well formed (`sk-ant-` prefix, no quotes or whitespace), so the upload was not the problem.
  - Calling the Anthropic API directly from my PC with the same key also returned `401`.
  - `git log --all -S 'sk-ant-'` returned nothing: the key had never been committed, so this was not a leak from this repo.
- **Root cause:** the API key (from the thesis days) had been revoked in the Anthropic Console. Nothing in AWS was wrong.
- **Fix:**
  - Created a new key and checked it against the API (`200`) before uploading it.
  - Uploaded it with `scripts/put-secrets.ps1`.
  - Ran `aws ecs update-service --cluster booking-bot --service booking-bot --force-new-deployment`. ECS injects SSM secrets only when a task starts, so the running task kept the old value until it was replaced. The rolling deployment did that with no downtime.
- **Lesson:** when a call to a third-party API fails with `401`, test the credential directly against the provider before touching the infrastructure. And rotating a secret in SSM is not enough on its own: ECS tasks need a new deployment to pick it up.

## 007 — After merging the DynamoDB code, the bot still forgot conversations (2026-11-09)
- **Symptom:** after merging the change that stores conversations in DynamoDB (PR #14), a WhatsApp test still behaved like the old version. After a task restart, the bot no longer knew the user's name, and the sessions table was empty.
- **Diagnosis:**
  - `/health` still returned the previous commit, so the new code was not running.
  - The Deploy run for the merge had failed in about a minute, with **0 jobs** executed and the message *"This run likely failed because of a workflow file issue"*. The workflow file had not changed, and its previous run had succeeded.
  - GitHub's status page showed an ongoing *"Incident with Actions and Checks API"*, which had started nine minutes before the merge.
- **Root cause:** a GitHub Actions outage. The run could not start any job. Nothing was wrong in the workflow, the code or AWS.
- **Fix:** once GitHub was recovering, I started the Deploy manually with `gh workflow run deploy.yml --ref main` (the workflow has a `workflow_dispatch` trigger for this). `/health` then reported the new commit, and the next message created an item in the table.
- **Lesson:** check what is actually deployed before testing a change. That is exactly why `/health` reports the commit. When a workflow fails with no jobs and no logs, check the provider's status page before debugging the YAML.

## 008 — `terraform destroy` left the ALB, the VPC and the table running (2026-11-10)
- **Symptom:** after a `terraform destroy` at the end of a session, the ALB (with its two public IPs), the VPC, the sessions table and an empty ECS cluster were still running. The Deploy run of the last merge had also failed, at *Deploy to ECS and wait until it is stable*.
- **Diagnosis:**
  - The alarms and the ECS service were already gone, but the rest was not, so the destroy had started and stopped halfway.
  - The state lock file (`app/terraform.tfstate.tflock`) was still in S3. It had been created 23 seconds after the merge to `main`, while the Deploy run was still in progress.
  - The state file had not been written since before the destroy, and no Terraform process was running on the PC.
- **Root cause:** two things together.
  - The destroy was started while the Deploy run was updating the same ECS service, so the Deploy failed when the service was deleted under it.
  - The Terraform process then stopped before finishing (the window was closed), so it could neither save the state nor release the lock.
- **Fix:**
  - Checked that no other Terraform run was in progress, then released the lock with `terraform force-unlock <lock-id>`.
  - Ran `terraform destroy` again. Terraform refreshes the state against AWS first, so the resources that were already deleted were dropped and only the rest was destroyed.
  - The second run seemed stuck for two minutes at `aws_ecs_service.app: Refreshing state...`. That is expected: the AWS provider keeps polling an `INACTIVE` service for up to two minutes before treating it as deleted.
- **Lesson:** wait for the deployment to finish before destroying. Never close a Terraform window in the middle of a run. A silent Terraform is usually waiting for AWS, and interrupting it leaves the lock in place and the state out of date.

## 009 — Terraform fails to refresh the `aws login` session, while the AWS CLI succeeds (2026-11-11)
- **Symptom:** about 40 minutes after `aws login`, `terraform plan` failed in the S3 backend with `failed to refresh cached credentials, create oauth2 token ... ValidationException: The provided authorization grant is invalid, expired, revoked, or malformed`.
- **Diagnosis:**
  - The cached session's access credentials last 15 minutes and are then renewed with a refresh token. After 40 minutes without any AWS call, they had expired, so Terraform had to renew them and that call failed.
  - A minute later, `aws sts get-caller-identity` renewed them **with the same cached refresh token** without any error, and `terraform plan` then worked.
- **Root cause:** not confirmed. The login session was valid, because the CLI could renew it. The failure is in how Terraform renews it. On the previous days it had probably never needed to, because AWS CLI commands run in between kept the credentials fresh.
- **Fix (workaround):** run any AWS CLI command, such as `aws sts get-caller-identity`, before Terraform when the session has been idle for more than 15 minutes.
- **Lesson:** two tools reading the same credential cache can behave differently. Testing the same credential with a second client tells you whether the problem is the credential or the client.

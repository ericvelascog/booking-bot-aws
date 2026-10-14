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

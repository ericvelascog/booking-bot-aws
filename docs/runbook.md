# Runbook

What to do when an alarm email arrives. Each alarm's description links to its section here.

All alarms notify the `booking-bot-alerts` SNS topic (email) when they fire and again when they recover. They are defined in [`infra/app/alarms.tf`](../infra/app/alarms.tf).

## First checks, for any alarm

Commands assume the AWS CLI is logged in (`aws login`) and the region is `eu-west-1`.

1. **Is the service up, and which version is running?**
   ```bash
   curl https://d354dom4m7oqh9.cloudfront.net/health
   ```
   `{"status":"ok","version":"<commit>"}` means at least one task is healthy. Compare the version with the latest merge to `main`. A `502` means the `app` stack is down. A `503` means the ALB has no healthy task.
2. **What has ECS done recently?** (deployments, task starts and stops, failed health checks)
   ```bash
   aws ecs describe-services --cluster booking-bot --services booking-bot --query "services[0].events[0:10].[createdAt,message]" --output text
   ```
3. **What do the logs say?** (last 15 minutes, without the health checks)
   ```bash
   aws logs tail /ecs/booking-bot --since 15m | grep -v "GET /health"
   ```
   Each task writes to its own log stream (`app/app/<task-id>`), so `--format detailed` shows which task logged each line.
4. **Was there a deployment just before?** Check the Deploy workflow in GitHub Actions. A bad version is normally rolled back by the circuit breaker. If it was not, revert the commit on `main` through a pull request; the pipeline deploys the revert.

## http-5xx

**Meaning:** 5 or more `5xx` responses in one minute. The count includes the app's own errors (`HTTPCode_Target_5XX_Count`, usually `500`) and the ALB's (`HTTPCode_ELB_5XX_Count`: `502`/`503`/`504`).

**Impact:** clients get errors. For WhatsApp, Meta retries failed webhook deliveries for a while, so short spikes are usually recovered.

**Diagnose:**
- **`500` from the app:** look for a Python traceback in the logs (step 3). Malformed requests to `/llm/chat/completions` also return `500`. This is a known gap until the voice endpoints require a key.
- **`503` from the ALB:** no healthy task. Check the ECS events (step 2). Tasks failing to start usually mean a bad image, missing secrets in SSM or a missing IAM permission, and the stopped task's reason says which.
- **`504` from the ALB:** a request took longer than the timeout, usually a slow external API (Anthropic, Google Calendar).

**Recover:** fix the cause, or roll back (step 4). The alarm returns to `OK` on its own after a minute without errors.

## unhealthy-targets

**Meaning:** at least one task has failed the ALB health check (`GET /health` every 30 s) for 2 minutes in a row.

**Impact:** with two tasks, usually none for users: the ALB stops sending traffic to the unhealthy task and ECS replaces it. If **every** task is unhealthy, `http-5xx` fires as well (`503`).

**Diagnose:**
- Check the ECS events (step 2) for `failed ELB health checks` and the task that was replaced.
- Check that task's log stream for the last lines before it stopped. A crash at start-up often points to configuration (secrets, environment variables).
- If tasks keep being replaced in a loop, the deployment circuit breaker rolls back after repeated failures. Check whether it did.

**Recover:** usually automatic. ECS replaces the task, and the alarm returns to `OK` when the health checks pass again. If it keeps firing, roll back (step 4).

## message-errors

**Meaning:** the bot failed to answer at least one WhatsApp message in the last 5 minutes. A log metric filter counts the lines `Error procesando mensaje` that `main.py` writes when the processing fails.

This alarm exists because the other two cannot see this failure. The webhook answers `200` to Meta immediately and processes the message afterwards. The user receives a generic "ha ocurrido un error" reply.

**Diagnose:** find the error line in the logs (step 3). The exception message usually names the cause:
- `401 ... invalid x-api-key` from Anthropic: the API key was revoked or rotated. See [troubleshooting #006](troubleshooting.md).
- `AccessDeniedException` from DynamoDB: the task role is missing a permission on the sessions table.
- Errors from the Google Calendar API: the service account lost access to the calendar, or the credentials were rotated.

**Recover:** fix the credential or the permission. Secrets are read only when a task starts, so after changing one in SSM, force a new deployment:
```bash
aws ecs update-service --cluster booking-bot --service booking-bot --force-new-deployment
```
Then send a WhatsApp message to confirm. The alarm returns to `OK` after 5 minutes without errors.

## Testing the alarms

Alarms that have never fired are not trusted. Each one was tested on 2026-11-10:
- `http-5xx`: 10 requests with an invalid body to `/llm/chat/completions` (ten `500`s). The alarm fired within a minute and emailed, then recovered a minute later.
- `message-errors`: a line `Error procesando mensaje de PRUEBA: ...` was written to a test log stream with `aws logs put-log-events`. The alarm fired about 30 seconds later and emailed.
- `unhealthy-targets`: hard to cause on purpose without breaking the app. The notification path is the same as for the other two.

# ADR-0004: Autoscale on requests per task, not CPU

- **Status:** Accepted
- **Date:** 2026-11-10

## Context
With conversations in DynamoDB ([ADR-0003](0003-stateless-sessions-in-dynamodb.md)), the ECS service can run several tasks. It runs a minimum of two, one per Availability Zone, and needs a rule to add tasks under load and remove them afterwards.

The bot is I/O-bound. Almost all of a request's time is spent waiting for the Anthropic API, Google Calendar or the WhatsApp API, not computing. Under heavy traffic, a task fills up with open requests while its CPU stays low.

## Options considered
1. **Target tracking on average CPU** (`ECSServiceAverageCPUUtilization`). This is the usual default, and the original plan. For an I/O-bound app, CPU is a weak signal: it would react late, or not at all.
2. **Target tracking on requests per target** (`ALBRequestCountPerTarget`). The ALB counts the requests it sends to each task. That is close to what actually saturates this app, and it needs no custom metric.
3. **Custom metric for in-flight requests or response latency.** This is the most precise option, but it needs the app to publish metrics and alarms to be maintained. It is too much for this stage.

## Decision
Option 2:
- target tracking on `ALBRequestCountPerTarget`, with a target of **120 requests per task per minute**;
- **between 2 and 4 tasks**. The minimum of 2 keeps one task per AZ. The maximum of 4 caps the cost, even if someone floods the URL;
- **asymmetric cooldowns**: scale out after 60 s, scale in after 300 s. Running short is worse than paying for a few extra minutes.

The ECS service has `lifecycle { ignore_changes = [desired_count] }`. Autoscaling owns the number of tasks, and a `terraform apply` must not reset it.

## Consequences
- AWS creates and manages the two CloudWatch alarms behind the policy (scale out and scale in). While traffic is low, the scale-in alarm sits in `ALARM` state. That is expected: the service is already at its minimum.
- The value of 120 is an estimate, not a measurement. The next step would be a load test to find the request rate at which latency degrades, and to set the target below it.
- Health-check requests from the ALB do not count as traffic, so an idle service stays at two tasks.

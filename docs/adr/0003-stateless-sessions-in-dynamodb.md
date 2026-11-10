# ADR-0003: Keep conversations in DynamoDB so the service is stateless

- **Status:** Accepted
- **Date:** 2026-11-10

## Context
The bot keeps the recent messages of each WhatsApp conversation so that Claude has context ("book it at 5 pm" only makes sense after "I want an appointment on Thursday"). Until now that history lived in a Python dictionary inside the container.

That had two consequences, both seen in practice:
- every deployment or task replacement wiped all conversations;
- the service could not run more than one task. The load balancer spreads messages across tasks, and a task that receives the second message of a conversation knows nothing about the first.

Running a single task means a single point of failure. The goal is two tasks in two Availability Zones, which requires the history to live outside the container.

Constraints: personal budget, so no servers running all the time; the data is personal (phone numbers, names) and short-lived.

## Options considered
1. **Sticky sessions on the ALB.** Each user keeps hitting the same task. No new service is needed, but it does not solve anything: a task restart still loses the conversations, and a dead task takes its users' context with it. Meta's webhook calls do not carry cookies either, so stickiness would not even hold.
2. **ElastiCache (Redis).** The classic session store, with very low latency. But a node runs, and is billed, around the clock (at least ~$12/month), plus subnet groups and security groups to manage.
3. **RDS.** A relational database for a key-value lookup: an always-on instance (~$15/month) and a schema for no benefit.
4. **DynamoDB, on-demand.** Serverless and billed per request: at this volume it costs practically nothing, and nothing at all when idle. A key-value model fits exactly ("phone number → conversation"), and TTL expires data without a cleanup job.

## Decision
Option 4. A `booking-bot-sessions` table in the `app` stack:
- `phone` is the partition key;
- each item holds the last 20 messages and `expires_at`, the table's TTL attribute, set to six hours after the last message.

Details that matter:
- **Strongly consistent reads** (`ConsistentRead=True`). With several tasks, the next message can reach a different task milliseconds after the previous write, and an eventually consistent read could return the conversation without it. A strongly consistent read costs twice as much, which is still negligible.
- **Expiry is also checked on read.** DynamoDB's TTL deletes expired items in the background, sometimes days later, so the app treats an expired item as empty.
- **Least privilege.** The task role can only `GetItem`, `PutItem` and `DeleteItem` on this table. It cannot `Scan`: a compromised container could read a conversation for a number it already knows, but not dump everyone's. Verified with the IAM policy simulator.
- **Gateway VPC endpoint** for DynamoDB. It is free, and traffic from the tasks to the table stays on the AWS network.
- **Two implementations behind the same functions** in `session_store.py`. DynamoDB is used when `SESSIONS_TABLE` is set (Terraform sets it). Otherwise the store stays in memory, for local development and tests. The rest of the bot is unchanged. Tests run both implementations, with DynamoDB faked by moto.

## Consequences
- The service is stateless. It now runs two tasks across two AZs with autoscaling ([ADR-0004](0004-autoscale-on-requests-per-task.md)), and conversations survive deployments and task failures. Both were tested. A task was stopped mid-traffic with zero failed requests, and a WhatsApp conversation started on that task continued correctly on the other one.
- Personal data is kept for at most six hours of inactivity, is encrypted at rest (AWS-owned key) and is deleted automatically.
- No point-in-time recovery: the data expires in hours and the table lives in the stack that is destroyed after each demo.
- **Known limitation: last writer wins.** Each new message is a read followed by a full write. If one person sends two messages at the same instant and they land on different tasks, one can overwrite the other. In a chat where a person writes in turns this is acceptable. The fix would be optimistic locking: a version attribute and a conditional write, retried on conflict.
- In production, I would also consider a customer-managed KMS key and a separate table per environment.

# ADR-0001: Public subnets without a NAT Gateway

- **Status:** Accepted
- **Date:** 2026-10-13

## Context
The ECS tasks must make outbound HTTPS calls (Anthropic API, Google Calendar, WhatsApp Cloud API) and must only receive traffic from the load balancer.

The reference design puts tasks in private subnets and gives them egress through a NAT Gateway. This project is a portfolio demo on a personal budget: the environment is created for demos and destroyed afterwards. A NAT Gateway is billed per hour plus per GB processed (about $0.048/h in eu-west-1, roughly $35/month per NAT if always on), which is more than the rest of the stack combined.

## Options considered
1. **Private subnets + NAT Gateway per AZ.** Tasks have no public IP: the best isolation. Costs ~$35/month per NAT. A single shared NAT halves the cost, but it becomes a single point of failure across AZs.
2. **Private subnets + VPC interface endpoints.** AWS APIs (ECR, CloudWatch Logs, SSM) are reachable without internet access. However, the app still needs the public internet for Anthropic, Google and Meta, so a NAT would still be required. Each interface endpoint also costs ~$8/month per AZ.
3. **Public subnets, tasks with a public IP, locked down by security groups.** No NAT cost. Tasks reach the internet directly through the Internet Gateway. The task security group only accepts traffic from the ALB security group on port 8000, so nothing on the internet can reach a task directly.

## Decision
Option 3. For this workload it gives the same practical exposure (no inbound path except through the ALB) at no extra cost.

## Consequences
- Isolation relies on one control (the task security group) instead of the network layout: a wrong rule would expose the tasks. Mitigated by defining the rule in Terraform and reviewing every change in a pull request.
- Each running task uses a public IPv4 address ($0.005/h).
- **In production** I would move the tasks to private subnets with a NAT Gateway per AZ (or one shared NAT if cost matters more than AZ independence), keeping only the ALB in public subnets.

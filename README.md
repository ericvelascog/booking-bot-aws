# booking-bot-aws

AI booking assistant for physiotherapy clinics (WhatsApp + voice, powered by the Claude API and Google Calendar), containerised with Docker and deployed on **AWS ECS Fargate**. Infrastructure as code with **Terraform**, CI/CD with **GitHub Actions**.

> **Work in progress** — built in public. v0.1.0 target: late October 2026.

## Roadmap

- [ ] Docker image running locally
- [ ] Terraform: remote state (S3), ECR, VPC, ALB, ECS Fargate
- [ ] CI/CD: GitHub Actions, authenticated to AWS with OIDC (no static keys)
- [ ] Docs: architecture diagram, ADRs, costs, troubleshooting log

## Repository layout

```
app/     FastAPI bot (Python)
infra/   Terraform (coming soon)
docs/    Architecture decisions (ADRs) and troubleshooting log
```

# ADR-0002: HTTPS with CloudFront in a permanent edge stack

- **Status:** Accepted
- **Date:** 2026-11-06

## Context
The bot was served over plain HTTP from the ALB. That is not acceptable for a public endpoint, and WhatsApp only delivers webhooks to HTTPS URLs.

HTTPS needs a certificate. An ACM certificate on the ALB requires a domain name, and this project avoids recurring costs. The `app` stack is also destroyed between demos, so the ALB gets a new DNS name every time it is recreated, while external systems (the Meta webhook, the README) need one stable URL.

## Options considered
1. **Custom domain + ACM certificate on the ALB.** HTTPS all the way to the load balancer, with a stable name through a Route 53 alias. Costs a domain (~$10–15/year) and a hosted zone ($0.50/month).
2. **CloudFront inside the `app` stack.** Free HTTPS with the default `*.cloudfront.net` certificate. But the distribution, and therefore the URL, is recreated with every `apply`: the webhook would have to be reconfigured for each demo, and creating and deleting a distribution adds minutes to every cycle.
3. **CloudFront in a separate, permanent `edge` stack.** The distribution is created once and finds the current ALB by name. Same free HTTPS, a URL that never changes, and no cost while idle (CloudFront charges only for traffic).

## Decision
Option 3. Stacks are split by lifecycle, as before:
- `bootstrap` is permanent;
- `edge` is permanent and free while idle;
- `app` is ephemeral.

The ALB is closed to everything except CloudFront in two ways:
- its security group only accepts the AWS-managed prefix list `com.amazonaws.global.cloudfront.origin-facing`;
- its listener returns `403` unless the request carries a secret `X-Origin-Verify` header that only our distribution sends.

The header value is generated in `bootstrap` (it must exist before both `app` and `edge`) and stored in SSM under `/booking-bot-infra/`, outside the path the app container can read.

## Consequences
- The public URL is stable. The webhook is configured once, and the README can link to a live demo.
- Starting the environment takes one more step: `apply` the `app` stack, then the `edge` stack, so that the origin points at the new ALB. `edge` cannot be planned while `app` is down, because it reads the ALB by name. While `app` is down, the URL returns 502.
- The hop from CloudFront to the ALB is plain HTTP, because the ALB has no certificate without a domain. Viewers get HTTPS, and the secret header and the prefix list stop direct access, but traffic between CloudFront and the ALB is not encrypted.
- The shared header value is stored in the Terraform state of three stacks (an encrypted, private bucket). Rotating it means replacing `random_password` in `bootstrap`, then re-applying `app` and `edge`.
- **In production** I would add a domain with an ACM certificate on the ALB and an HTTPS-only origin, or use CloudFront VPC origins with an internal ALB in private subnets. In both cases the traffic would be encrypted end to end.

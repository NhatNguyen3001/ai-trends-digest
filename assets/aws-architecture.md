# AI Trends Digest — AWS Architecture (draw.io)

Source: [`aws-architecture.drawio`](aws-architecture.drawio) — open in [draw.io Desktop](https://www.drawio.com/)
or [app.diagrams.net](https://app.diagrams.net/) (uses the official AWS Architecture Icons). Export a PNG/SVG
from there for the README if you want a rendered image.

Deployment shape **Option B**: the daily batch runs itself on a schedule; the web UI comes up on demand.
Region **ap-southeast-2 (Sydney)**, default VPC, **no NAT Gateway** and **no load balancer** by design.

## Flow

**Daily batch (scheduled):**
1. **EventBridge Scheduler** fires a `RunTask` at 9am Sydney (timezone-aware cron).
2. The **ECS Fargate batch task** (`run_digest`) starts: **pulls its image** from **ECR** and reads
   **secrets** (API keys + SES SMTP creds) from **Secrets Manager** as env vars.
3. It reads/writes **state** on **EFS** (`/data`: Qdrant cross-day memory, `pins.json`, past digests) and
   streams **logs** to **CloudWatch**.
4. It calls **external APIs** over the internet via a public IP (no NAT) — Claude, Voyage, Tavily, and the
   sources (arXiv, RSS, GitHub).
5. It **sends** the digest through **Amazon SES** (SMTP :465), which **delivers** it to **your inbox**.
6. The task exits — you pay only for those minutes.

**Web (on-demand):**
7. You launch the **ECS Fargate web task** (public IP, firewalled to your IP, 1-hour auto-stop) and open it
   in your **browser** over HTTP :8000.
8. It **reads digests** from the same **EFS**, so you browse the real cloud-generated digests.

## Services

| Service | Purpose |
|---|---|
| EventBridge Scheduler | Timezone-aware daily trigger (`cron(0 9 * * ? *)` @ Australia/Sydney) |
| ECS Fargate (batch) | Serverless container that runs the pipeline once and exits |
| ECS Fargate (web) | On-demand serverless container serving the web UI; 1-hour `timeout` auto-stop |
| Amazon ECR | Private registry holding the container image |
| AWS Secrets Manager | One JSON secret (API keys + SES SMTP creds) injected as env |
| Amazon EFS | Persistent `/data` filesystem shared by the batch and web tasks |
| Amazon CloudWatch Logs | Per-run container logs |
| Amazon SES | Transactional email over SMTP (sandbox, self-send) |
| External APIs | Anthropic Claude, Voyage, Tavily, and the arXiv/RSS/GitHub sources |

## Key design decisions

- **Batch is a Fargate *task*, not a service** — pay only for the minutes it runs (~$0.30/mo).
- **No NAT Gateway** — the task uses a public IP + internet gateway, avoiding the ~$32/mo NAT trap.
- **No ALB** — the web is an on-demand task with a public IP (IP-scoped firewall, 1-hour auto-stop),
  avoiding the ~$18/mo always-on load balancer.
- **One Secrets Manager secret**, injected as env — keys never live in the image.
- **State on EFS** — embedded Qdrant + `pins.json` + digests persist with zero code change.
- **Email via SES over SMTP** — same `smtplib` code as local; only the endpoint/creds differ.

**Total AWS cost: ~$1–3/month.**

> Note: if any AWS icon renders as an empty colored square in draw.io, its stencil name needs adjusting
> (the uncertain ones are ECR `elastic_container_registry`, EFS `elastic_file_system`, Secrets Manager
> `secrets_manager`, CloudWatch `cloudwatch`, Fargate `fargate`) — tell me which and I'll correct it.

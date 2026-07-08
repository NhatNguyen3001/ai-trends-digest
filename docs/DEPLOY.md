# Deploying to AWS

A reproducible guide to run AI Trends Digest as a self-running daily job on AWS, plus an on-demand web UI.
This is the **Option B** shape: the batch is always scheduled, the web is brought up on demand. Total cost
is about **$2 to $3 a month**, with no NAT Gateway and no load balancer.

> Replace every placeholder in angle brackets with your own values: `<ACCOUNT_ID>`, `<REGION>` (e.g.
> `ap-southeast-2`), `<SECRET_ARN>`, `<EXEC_ROLE_ARN>`, `<FS_ID>`, `<SUBNET_ID>`, `<SG_ID>`. Keep all
> resources in **one region**: ECS requires a task's secret and EFS to be in the same region as the task.

## Prerequisites

- An AWS account and the **AWS CLI v2** configured (`aws configure`).
- **Docker** to build the image.
- The app image (see the repo `Dockerfile`).

## 1. Push the image to Amazon ECR

```bash
aws ecr create-repository --repository-name ai-trends-digest --region <REGION>
docker build -t ai-trends-digest:latest .
aws ecr get-login-password --region <REGION> \
  | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com
docker tag ai-trends-digest:latest <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-trends-digest:latest
docker push <ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-trends-digest:latest
```

## 2. Set up email (Amazon SES)

1. Verify a sender/recipient email identity in the SES console and click the verification link. Sending to
   your own verified address works inside the SES sandbox, so no production-access request is needed.
2. Create **SMTP credentials** (SES console, SMTP settings). These are SES-specific, not your AWS access
   keys. Note the SMTP endpoint, `email-smtp.<REGION>.amazonaws.com:465`.

## 3. Store secrets (AWS Secrets Manager)

Create one secret named `ai-trends-digest/env` with a JSON value:

```json
{
  "ANTHROPIC_API_KEY": "...",
  "VOYAGE_API_KEY": "...",
  "TAVILY_API_KEY": "...",
  "GITHUB_TOKEN": "",
  "LANGSMITH_API_KEY": "...",
  "SMTP_USER": "<SES SMTP username>",
  "SMTP_PASSWORD": "<SES SMTP password>"
}
```

Copy its ARN into `<SECRET_ARN>`.

## 4. Create the EFS file system

Create an EFS file system in your default VPC (the console creates a mount target per Availability Zone
using the default security group). Note the file system id as `<FS_ID>`. The default security group's
self-referencing rule lets the task reach EFS over NFS, so no extra rule is needed.

## 5. Create the task execution role (IAM)

Create a role trusted by `ecs-tasks.amazonaws.com` with the managed policy
`AmazonECSTaskExecutionRolePolicy`, plus an inline policy allowing `secretsmanager:GetSecretValue` on
`<SECRET_ARN>`. Copy the role ARN into `<EXEC_ROLE_ARN>`.

## 6. Create the CloudWatch log group

```bash
aws logs create-log-group --log-group-name /ecs/ai-trends-digest-batch --region <REGION>
```

## 7. Register the ECS task definition

Save this as `taskdef.json` (Fargate, 1 vCPU / 2 GB), then register it:

```json
{
  "family": "ai-trends-digest-batch",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "1024",
  "memory": "2048",
  "runtimePlatform": { "cpuArchitecture": "X86_64", "operatingSystemFamily": "LINUX" },
  "executionRoleArn": "<EXEC_ROLE_ARN>",
  "containerDefinitions": [
    {
      "name": "batch",
      "image": "<ACCOUNT_ID>.dkr.ecr.<REGION>.amazonaws.com/ai-trends-digest:latest",
      "essential": true,
      "command": ["python", "scripts/run_digest.py"],
      "environment": [
        { "name": "TZ", "value": "Australia/Sydney" },
        { "name": "QDRANT_PATH", "value": "/data/qdrant" },
        { "name": "PINS_PATH", "value": "/data/pins.json" },
        { "name": "DIGEST_DIR", "value": "/data/digests" },
        { "name": "SMTP_HOST", "value": "email-smtp.<REGION>.amazonaws.com" },
        { "name": "SMTP_PORT", "value": "465" },
        { "name": "EMAIL_FROM", "value": "<YOUR_EMAIL>" },
        { "name": "EMAIL_TO", "value": "<YOUR_EMAIL>" }
      ],
      "secrets": [
        { "name": "ANTHROPIC_API_KEY", "valueFrom": "<SECRET_ARN>:ANTHROPIC_API_KEY::" },
        { "name": "VOYAGE_API_KEY", "valueFrom": "<SECRET_ARN>:VOYAGE_API_KEY::" },
        { "name": "TAVILY_API_KEY", "valueFrom": "<SECRET_ARN>:TAVILY_API_KEY::" },
        { "name": "GITHUB_TOKEN", "valueFrom": "<SECRET_ARN>:GITHUB_TOKEN::" },
        { "name": "LANGSMITH_API_KEY", "valueFrom": "<SECRET_ARN>:LANGSMITH_API_KEY::" },
        { "name": "SMTP_USER", "valueFrom": "<SECRET_ARN>:SMTP_USER::" },
        { "name": "SMTP_PASSWORD", "valueFrom": "<SECRET_ARN>:SMTP_PASSWORD::" }
      ],
      "mountPoints": [ { "sourceVolume": "data", "containerPath": "/data", "readOnly": false } ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ai-trends-digest-batch",
          "awslogs-region": "<REGION>",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ],
  "volumes": [
    { "name": "data",
      "efsVolumeConfiguration": { "fileSystemId": "<FS_ID>", "rootDirectory": "/", "transitEncryption": "ENABLED" } }
  ]
}
```

```bash
aws ecs create-cluster --cluster-name ai-trends-digest --region <REGION>
aws ecs register-task-definition --cli-input-json file://taskdef.json --region <REGION>
```

> `TZ=Australia/Sydney` dates the digest in local time. The image installs `tzdata` so this resolves;
> change it to your own timezone.

## 8. Test run (this incurs LLM API cost)

Run the task once with a public IP (no NAT, so the task needs a public IP to reach the internet):

```bash
aws ecs run-task --cluster ai-trends-digest --task-definition ai-trends-digest-batch \
  --launch-type FARGATE --region <REGION> \
  --network-configuration "awsvpcConfiguration={subnets=[<SUBNET_ID>],securityGroups=[<SG_ID>],assignPublicIp=ENABLED}"
```

Watch the task logs in CloudWatch. On success it emails the digest and writes state to EFS.

## 9. Schedule it (Amazon EventBridge Scheduler)

Create a recurring schedule with a cron expression and your timezone (for example
`cron(0 9 * * ? *)` at `Australia/Sydney`), targeting `ecs:RunTask` on the cluster and task definition, with
the same network configuration as step 8 and `AssignPublicIp=ENABLED`. Let the console create the scheduler
IAM role for you.

The batch now runs itself daily.

## On-demand web UI (optional, no load balancer)

Register a second task definition (`ai-trends-digest-web`) that mounts the same EFS and runs the web server
with a 1-hour hard auto-stop:

```
"command": ["timeout", "3600", "python", "scripts/serve_web.py"]
```

Run it with a public IP, opening inbound port 8000 in a dedicated security group scoped to your current IP,
then browse `http://<public-ip>:8000`. Stop the task when done (or let the 1-hour timeout stop it). This
avoids the cost of an always-on service and a load balancer.

## Cost and teardown

- **Cost:** about $2 to $3 a month (Fargate minutes, a small EFS, one Secrets Manager secret, CloudWatch).
  A NAT Gateway (about $32/mo) and an always-on web plus ALB (about $18/mo) are avoided by design.
- **Pause:** disable the EventBridge schedule.
- **Remove cost:** delete the schedule, the EFS file system, and the ECR image. The cluster, task
  definitions, roles, and secret cost little or nothing at rest.

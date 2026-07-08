# Deploying to AWS

A reproducible guide to run AI Trends Digest as a self-running daily job on AWS, plus an on-demand web UI.
This is the **Option B** shape: the batch is always scheduled, the web is brought up on demand. Total cost
is about **$2 to $3 a month**, with no NAT Gateway and no load balancer.

> Replace every placeholder in angle brackets with your own values: `<ACCOUNT_ID>`, `<REGION>` (e.g.
> `ap-southeast-2`), `<VPC_ID>`, `<SUBNET_ID>`, `<SG_ID>` (your VPC's default security group), `<SECRET_ARN>`,
> `<EXEC_ROLE_ARN>`, `<FS_ID>`, `<YOUR_EMAIL>`, and for the on-demand web UI `<WEB_SG_ID>` plus
> `<DEFAULT_SG_ID>` (the same as `<SG_ID>`). Keep all resources in **one region**: ECS requires a task's
> secret and EFS to be in the same region as the task.
>
> Find the defaults with: `aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId"`,
> `aws ec2 describe-subnets --filters Name=vpc-id,Values=<VPC_ID> --query "Subnets[].SubnetId"`, and
> `aws ec2 describe-security-groups --filters Name=vpc-id,Values=<VPC_ID> Name=group-name,Values=default --query "SecurityGroups[0].GroupId"`.

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

Verify: `aws ecr describe-images --repository-name ai-trends-digest --region <REGION>` lists a `latest` tag.

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

Verify: `aws logs tail /ecs/ai-trends-digest-batch --region <REGION> --since 10m` streams the run. On success
the task shows exit code 0, the digest arrives by email, and state is written to EFS (visible on the next run
when cross-day memory kicks in).

## 9. Schedule it (Amazon EventBridge Scheduler)

Create a recurring schedule with a cron expression and your timezone (for example
`cron(0 9 * * ? *)` at `Australia/Sydney`), targeting `ecs:RunTask` on the cluster and task definition, with
the same network configuration as step 8 and `AssignPublicIp=ENABLED`. Let the console create the scheduler
IAM role for you.

The batch now runs itself daily.

## On-demand web UI (optional, no load balancer)

The web UI reads digests from EFS, which is not reachable from your laptop, so the viewer runs in the cloud.
Instead of an always-on service behind a load balancer, run it as an **on-demand Fargate task** with a public
IP, firewalled to your current IP, that stops itself after one hour. Cost when used a few minutes a day is
about $0.30 to $0.50 a month.

### a. Create a dedicated web security group

```bash
aws ec2 create-security-group --group-name digest-web-sg \
  --description "On-demand digest web task: inbound 8000 from my IP" \
  --vpc-id <VPC_ID> --region <REGION>
```

Note the returned group id as `<WEB_SG_ID>`. Leave it with no inbound rules; the `web-up` script sets them
per launch. Also create a web log group: `aws logs create-log-group --log-group-name /ecs/ai-trends-digest-web --region <REGION>`.

### b. Register the web task definition

Same shape as the batch task, with these differences: `family` = `ai-trends-digest-web`, size `0.5 vCPU /
1 GB` (`"cpu": "512"`, `"memory": "1024"`), a **port mapping** for 8000, an `HOST=0.0.0.0` env var, the log
group `/ecs/ai-trends-digest-web`, and a **command with a 1-hour hard auto-stop**:

```json
"command": ["timeout", "3600", "python", "scripts/serve_web.py"],
"portMappings": [ { "containerPort": 8000, "protocol": "tcp" } ]
```

The `timeout 3600` means the container exits after one hour, so a forgotten task cannot run up a bill (no
extra AWS resources needed). The image includes `timeout` (GNU coreutils).

### c. Bring it up (`web-up.ps1`)

This detects your public IP, opens port 8000 to only that IP, launches the task, waits, and prints the URL:

```powershell
$REGION     = "<REGION>"
$CLUSTER    = "ai-trends-digest"
$TASKDEF    = "ai-trends-digest-web"
$WEB_SG     = "<WEB_SG_ID>"       # dedicated SG, inbound 8000
$DEFAULT_SG = "<DEFAULT_SG_ID>"   # default SG, needed for EFS access
$SUBNET     = "<SUBNET_ID>"
$TMP        = "$env:TEMP\web_sg.json"

$myip = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com").Trim()

# Reset the web SG to allow ONLY your current IP on 8000.
$perms = aws ec2 describe-security-groups --group-ids $WEB_SG --region $REGION --query "SecurityGroups[0].IpPermissions" --output json
if ($perms.Trim() -ne "[]") {
    $perms | Out-File -Encoding ascii $TMP
    aws ec2 revoke-security-group-ingress --group-id $WEB_SG --region $REGION --ip-permissions "file://$TMP" | Out-Null
    Remove-Item $TMP
}
aws ec2 authorize-security-group-ingress --group-id $WEB_SG --protocol tcp --port 8000 --cidr "$myip/32" --region $REGION | Out-Null

# Launch the task with a public IP (both SGs: default for EFS, web for inbound 8000).
$net  = "awsvpcConfiguration={subnets=[$SUBNET],securityGroups=[$DEFAULT_SG,$WEB_SG],assignPublicIp=ENABLED}"
$task = aws ecs run-task --cluster $CLUSTER --task-definition $TASKDEF --launch-type FARGATE --region $REGION --network-configuration $net --query "tasks[0].taskArn" --output text
aws ecs wait tasks-running --cluster $CLUSTER --tasks $task --region $REGION
Start-Sleep -Seconds 6   # let the server bind

$eni = aws ecs describe-tasks --cluster $CLUSTER --tasks $task --region $REGION --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value | [0]" --output text
$ip  = aws ec2 describe-network-interfaces --network-interface-ids $eni --region $REGION --query "NetworkInterfaces[0].Association.PublicIp" --output text
Write-Host "Web is up: http://${ip}:8000  (auto-stops in 1 hour)"
```

### d. Take it down (`web-down.ps1`)

Stops the task and closes port 8000 so nothing is reachable while it is down:

```powershell
$REGION="<REGION>"; $CLUSTER="ai-trends-digest"; $TASKDEF="ai-trends-digest-web"; $WEB_SG="<WEB_SG_ID>"
$TMP="$env:TEMP\web_sg.json"

$tasks = aws ecs list-tasks --cluster $CLUSTER --family $TASKDEF --desired-status RUNNING --region $REGION --query "taskArns" --output text
foreach ($t in ($tasks -split "\s+")) { if ($t) { aws ecs stop-task --cluster $CLUSTER --task $t --region $REGION | Out-Null } }

$perms = aws ec2 describe-security-groups --group-ids $WEB_SG --region $REGION --query "SecurityGroups[0].IpPermissions" --output json
if ($perms.Trim() -ne "[]") {
    $perms | Out-File -Encoding ascii $TMP
    aws ec2 revoke-security-group-ingress --group-id $WEB_SG --region $REGION --ip-permissions "file://$TMP" | Out-Null
    Remove-Item $TMP
}
```

**Security note:** the task has a public IP, but the firewall allows only your current IP on port 8000, it is
HTTP and short-lived, and it stops itself after an hour. Do not put sensitive data behind it. For zero public
exposure, run the task without an inbound rule and reach it through an SSM port-forwarding session instead.

## Troubleshooting

- **`535 Authentication Credentials Invalid` on email:** the secret has the wrong SMTP credentials. Use the
  **SES SMTP** username and password (SES console, SMTP settings), not your AWS access keys and not a Gmail
  app password.
- **`554 Email address is not verified`:** the SES identity is still pending. Click the verification link;
  the SES sandbox only sends to verified addresses.
- **Task cannot read the secret / mount EFS:** the secret, the EFS, and the task must be in the **same
  region**. Confirm the console region selector and the CLI `--region` agree on every step.
- **`ResourceNotFoundException` for the log group:** registering a task definition does not create the log
  group. Create it first (step 6).
- **Task starts then cannot reach the internet or pull the image:** make sure `assignPublicIp=ENABLED` is
  set (there is no NAT Gateway, so the task needs a public IP).

## Cost and teardown

- **Cost:** about $2 to $3 a month (Fargate minutes, a small EFS, one Secrets Manager secret, CloudWatch).
  A NAT Gateway (about $32/mo) and an always-on web plus ALB (about $18/mo) are avoided by design.
- **Pause:** disable the EventBridge schedule.
- **Remove cost:** delete the schedule, the EFS file system, and the ECR image. The cluster, task
  definitions, roles, and secret cost little or nothing at rest.

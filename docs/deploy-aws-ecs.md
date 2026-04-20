# Deploy on AWS ECS

Guide to deploy helPRs on AWS using ECS, RDS, and an Application Load Balancer.

!!! warning "Docker socket constraint"
    helPRs spawns ephemeral containers via the Docker socket. **ECS Fargate does not support Docker socket mounting.** You must use **ECS on EC2** for the API task, or run the API on a standalone EC2 instance. The Web service can run on Fargate.

This guide assumes you have completed the [Self-Hosting Setup](self-hosting.md) (GitHub App created, secrets generated).

---

## Architecture

```
                    +--------------------+
                    |    Route 53 /      |
                    |    External DNS    |
                    +---------+----------+
                              |
                    +---------v----------+
                    |        ALB         |
                    |  (TLS via ACM)     |
                    +----+----------+----+
                         |          |
        api.yourdomain   |          |  yourdomain.com
        .com             |          |
              +----------v--+  +----v-----------+
              | ECS Service |  | ECS Service    |
              | API (EC2)   |  | Web (Fargate)  |
              | :8000       |  | :80            |
              +------+------+  +----------------+
                     |
           +---------+---------+
           |                   |
    +------v------+   +--------v--------+
    |    RDS      |   | claude-runner   |
    | PostgreSQL  |   | (spawned on     |
    | 16          |   |  EC2 host via   |
    |             |   |  Docker socket) |
    +-------------+   +-----------------+
```

---

## Prerequisites

- AWS account with appropriate IAM permissions
- AWS CLI v2 configured (`aws configure`)
- Docker installed locally (for building images)
- A domain (managed in Route 53 or externally)
- GitHub App and secrets already created ([Self-Hosting Setup](self-hosting.md))

---

## 1. Infrastructure Setup

### VPC and Networking

Use the default VPC or create a dedicated one:

```bash
# Create VPC (skip if using default)
aws ec2 create-vpc --cidr-block 10.0.0.0/16 --query 'Vpc.VpcId' --output text
```

You need at least 2 subnets in different AZs for the ALB and RDS.

### Security Groups

Create security groups for each component:

```bash
# ALB security group: allow inbound 80/443 from anywhere
aws ec2 create-security-group --group-name helprs-alb-sg --description "helPRs ALB"

# API security group: allow inbound 8000 from ALB only
aws ec2 create-security-group --group-name helprs-api-sg --description "helPRs API"

# DB security group: allow inbound 5432 from API only
aws ec2 create-security-group --group-name helprs-db-sg --description "helPRs DB"
```

### RDS PostgreSQL

```bash
aws rds create-db-instance \
  --db-instance-identifier helprs-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 16 \
  --master-username helprs \
  --master-user-password '<strong-password>' \
  --allocated-storage 20 \
  --db-name helprs \
  --vpc-security-group-ids <db-sg-id> \
  --no-publicly-accessible
```

!!! tip "Security group"
    The RDS security group should only allow inbound PostgreSQL (port 5432) from the ECS API task security group.

Note the RDS endpoint after creation:

```bash
aws rds describe-db-instances --db-instance-identifier helprs-db \
  --query 'DBInstances[0].Endpoint.Address' --output text
```

### ECR Repositories

```bash
aws ecr create-repository --repository-name helprs/api
aws ecr create-repository --repository-name helprs/web
aws ecr create-repository --repository-name helprs/claude-runner
```

### ACM Certificate

```bash
aws acm request-certificate \
  --domain-name yourdomain.com \
  --subject-alternative-names api.yourdomain.com \
  --validation-method DNS
```

Complete DNS validation as prompted. Wait for the certificate status to become `ISSUED`.

---

## 2. Build and Push Images

```bash
# Login to ECR
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# Build and push API
docker build -f infra/docker/Dockerfile.api --target production \
  -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/api:latest apps/api
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/api:latest

# Build and push Web (with build args)
docker build -f infra/docker/Dockerfile.web --target production \
  --build-arg VITE_API_URL=https://api.yourdomain.com \
  --build-arg VITE_GITHUB_APP_SLUG=your-app-slug \
  -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/web:latest apps/web
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/web:latest

# Build and push claude-runner
docker build -f infra/docker/claude-runner/Dockerfile \
  -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest \
  infra/docker/claude-runner
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest
```

---

## 3. Store Secrets

Use AWS Secrets Manager for sensitive values:

```bash
aws secretsmanager create-secret \
  --name helprs/production \
  --secret-string '{
    "SECRET_KEY": "<generated>",
    "FERNET_KEY": "<generated>",
    "ADMIN_PASSWORD": "<generated>",
    "GITHUB_WEBHOOK_SECRET": "<generated>",
    "GITHUB_CLIENT_SECRET": "<from-github>",
    "GITHUB_APP_PRIVATE_KEY": "<base64-encoded-pem>",
    "DATABASE_URL": "postgresql+asyncpg://helprs:<password>@<rds-endpoint>:5432/helprs"
  }'
```

!!! note "PEM key in Secrets Manager"
    Use the base64-encoded PEM for Secrets Manager (JSON does not support multi-line values cleanly).
    The application auto-detects base64 and decodes it.

---

## 4. ECS Cluster and EC2 Instance

```bash
aws ecs create-cluster --cluster-name helprs
```

### EC2 Instance for API

The API task must run on EC2 (not Fargate) to access the Docker socket. Launch an ECS-optimized Amazon Linux 2 instance:

```bash
aws ec2 run-instances \
  --image-id <ecs-optimized-ami> \
  --instance-type t3.medium \
  --iam-instance-profile Name=ecsInstanceRole \
  --security-group-ids <api-sg-id> \
  --user-data '#!/bin/bash
echo ECS_CLUSTER=helprs >> /etc/ecs/ecs.config'
```

!!! tip "Find the ECS-optimized AMI"
    ```bash
    aws ssm get-parameters --names /aws/service/ecs/optimized-ami/amazon-linux-2/recommended/image_id \
      --query 'Parameters[0].Value' --output text
    ```

### Pre-pull claude-runner on EC2

SSH into the EC2 instance and pull the claude-runner image:

```bash
aws ecr get-login-password --region <region> | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker pull <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest
docker tag <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest claude-runner:latest
```

The API spawns containers using the local image name `claude-runner:latest`, so the tag is required.

### Set Up Skills Directory

```bash
# On the EC2 instance
sudo mkdir -p /opt/helprs/skills
sudo chown ec2-user:ec2-user /opt/helprs/skills

# Clone skills from the repo
git clone --depth 1 https://github.com/your-org/helprs.git /tmp/helprs
cp -r /tmp/helprs/skills/* /opt/helprs/skills/
rm -rf /tmp/helprs
```

---

## 5. Task Definitions

### API Task Definition

Create `helprs-api-task.json`:

```json
{
  "family": "helprs-api",
  "requiresCompatibilities": ["EC2"],
  "networkMode": "bridge",
  "executionRoleArn": "arn:aws:iam::<account>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/helprs/api:latest",
      "portMappings": [
        { "containerPort": 8000, "hostPort": 8000, "protocol": "tcp" }
      ],
      "mountPoints": [
        {
          "sourceVolume": "docker-socket",
          "containerPath": "/var/run/docker.sock"
        },
        {
          "sourceVolume": "skills",
          "containerPath": "/app/skills",
          "readOnly": true
        }
      ],
      "environment": [
        { "name": "ENVIRONMENT", "value": "production" },
        { "name": "GITHUB_APP_ID", "value": "<app-id>" },
        { "name": "GITHUB_CLIENT_ID", "value": "<client-id>" },
        { "name": "APP_BASE_URL", "value": "https://yourdomain.com" },
        { "name": "CORS_ORIGINS", "value": "[\"https://yourdomain.com\"]" },
        { "name": "SKILLS_HOST_PATH", "value": "/opt/helprs/skills" },
        { "name": "CONTAINER_TTL_SECONDS", "value": "900" },
        { "name": "UVICORN_WORKERS", "value": "4" }
      ],
      "secrets": [
        { "name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:SECRET_KEY::" },
        { "name": "FERNET_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:FERNET_KEY::" },
        { "name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:DATABASE_URL::" },
        { "name": "ADMIN_PASSWORD", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:ADMIN_PASSWORD::" },
        { "name": "GITHUB_WEBHOOK_SECRET", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:GITHUB_WEBHOOK_SECRET::" },
        { "name": "GITHUB_CLIENT_SECRET", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:GITHUB_CLIENT_SECRET::" },
        { "name": "GITHUB_APP_PRIVATE_KEY", "valueFrom": "arn:aws:secretsmanager:<region>:<account>:secret:helprs/production:GITHUB_APP_PRIVATE_KEY::" }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\""],
        "interval": 15,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 30
      },
      "memory": 1024,
      "cpu": 512,
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/helprs-api",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "api"
        }
      }
    }
  ],
  "volumes": [
    {
      "name": "docker-socket",
      "host": { "sourcePath": "/var/run/docker.sock" }
    },
    {
      "name": "skills",
      "host": { "sourcePath": "/opt/helprs/skills" }
    }
  ]
}
```

```bash
aws ecs register-task-definition --cli-input-json file://helprs-api-task.json
```

### Web Task Definition

Create `helprs-web-task.json`:

```json
{
  "family": "helprs-web",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "256",
  "memory": "512",
  "executionRoleArn": "arn:aws:iam::<account>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "web",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/helprs/web:latest",
      "portMappings": [
        { "containerPort": 80, "protocol": "tcp" }
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost/ || exit 1"],
        "interval": 15,
        "timeout": 5,
        "retries": 3
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/helprs-web",
          "awslogs-region": "<region>",
          "awslogs-stream-prefix": "web"
        }
      }
    }
  ]
}
```

```bash
aws ecs register-task-definition --cli-input-json file://helprs-web-task.json
```

---

## 6. Application Load Balancer

Create an ALB with host-based routing:

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name helprs-alb \
  --subnets <subnet-1> <subnet-2> \
  --security-groups <alb-sg-id>

# Create target groups
aws elbv2 create-target-group --name helprs-api --protocol HTTP --port 8000 \
  --vpc-id <vpc-id> --health-check-path /health --target-type instance

aws elbv2 create-target-group --name helprs-web --protocol HTTP --port 80 \
  --vpc-id <vpc-id> --health-check-path / --target-type ip

# HTTPS listener (default -> web)
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=<acm-cert-arn> \
  --default-actions Type=forward,TargetGroupArn=<web-tg-arn>

# HTTP -> HTTPS redirect
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTP --port 80 \
  --default-actions Type=redirect,RedirectConfig='{Protocol=HTTPS,Port=443,StatusCode=HTTP_301}'

# Routing rule for API subdomain
aws elbv2 create-rule \
  --listener-arn <https-listener-arn> \
  --conditions Field=host-header,Values=api.yourdomain.com \
  --actions Type=forward,TargetGroupArn=<api-tg-arn> \
  --priority 10
```

---

## 7. ECS Services

```bash
# API service (EC2 launch type)
aws ecs create-service \
  --cluster helprs \
  --service-name helprs-api \
  --task-definition helprs-api \
  --desired-count 1 \
  --launch-type EC2 \
  --load-balancers targetGroupArn=<api-tg-arn>,containerName=api,containerPort=8000

# Web service (Fargate)
aws ecs create-service \
  --cluster helprs \
  --service-name helprs-web \
  --task-definition helprs-web \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-1>,<subnet-2>],securityGroups=[<web-sg-id>],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=<web-tg-arn>,containerName=web,containerPort=80
```

---

## 8. DNS Configuration

### Route 53

```bash
aws route53 change-resource-record-sets --hosted-zone-id <zone-id> --change-batch '{
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "yourdomain.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "<alb-hosted-zone>",
          "DNSName": "<alb-dns-name>",
          "EvaluateTargetHealth": true
        }
      }
    },
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "api.yourdomain.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "<alb-hosted-zone>",
          "DNSName": "<alb-dns-name>",
          "EvaluateTargetHealth": true
        }
      }
    }
  ]
}'
```

### External DNS Provider

If your domain is not on Route 53, create CNAME records:

| Type | Host | Value |
|------|------|-------|
| CNAME | `yourdomain.com` | `helprs-alb-<id>.<region>.elb.amazonaws.com` |
| CNAME | `api.yourdomain.com` | `helprs-alb-<id>.<region>.elb.amazonaws.com` |

!!! note "Root domain CNAME"
    Some DNS providers don't allow CNAME on the root domain. Use ALIAS/ANAME records if available, or transfer the domain to Route 53.

---

## 9. Verify

```bash
# Health check
curl -s https://api.yourdomain.com/health
# Expected: {"status":"ok"}

# Frontend
curl -s -o /dev/null -w "%{http_code}" https://yourdomain.com
# Expected: 200
```

Then follow steps 4-6 of the [Self-Hosting Guide](self-hosting.md#step-4-install-the-github-app) to install the GitHub App, configure Claude credentials, and test end-to-end.

---

## 10. CI/CD with GitHub Actions

```yaml
name: Deploy to ECS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<account>:role/github-actions-deploy
          aws-region: <region>

      - id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push images
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
          SHA: ${{ github.sha }}
        run: |
          # API
          docker build -f infra/docker/Dockerfile.api --target production \
            -t $ECR_REGISTRY/helprs/api:latest \
            -t $ECR_REGISTRY/helprs/api:$SHA \
            apps/api
          docker push $ECR_REGISTRY/helprs/api --all-tags

          # Web
          docker build -f infra/docker/Dockerfile.web --target production \
            --build-arg VITE_API_URL=https://api.yourdomain.com \
            --build-arg VITE_GITHUB_APP_SLUG=your-app-slug \
            -t $ECR_REGISTRY/helprs/web:latest \
            -t $ECR_REGISTRY/helprs/web:$SHA \
            apps/web
          docker push $ECR_REGISTRY/helprs/web --all-tags

          # claude-runner
          docker build -f infra/docker/claude-runner/Dockerfile \
            -t $ECR_REGISTRY/helprs/claude-runner:latest \
            infra/docker/claude-runner
          docker push $ECR_REGISTRY/helprs/claude-runner --all-tags

      - name: Update ECS services
        run: |
          aws ecs update-service --cluster helprs --service helprs-api --force-new-deployment
          aws ecs update-service --cluster helprs --service helprs-web --force-new-deployment

      - name: Update claude-runner on EC2
        run: |
          # Pull the new image on the EC2 instance via SSM
          aws ssm send-command \
            --instance-ids <ec2-instance-id> \
            --document-name "AWS-RunShellScript" \
            --parameters 'commands=[
              "aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com",
              "docker pull <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest",
              "docker tag <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest claude-runner:latest"
            ]'
```

!!! tip "Skills sync"
    Add a step to sync the `skills/` directory to the EC2 instance after deploy:
    ```yaml
    - name: Sync skills to EC2
      run: |
        aws ssm send-command \
          --instance-ids <ec2-instance-id> \
          --document-name "AWS-RunShellScript" \
          --parameters 'commands=[
            "cd /opt/helprs/repo && git pull",
            "cp -r skills/* /opt/helprs/skills/"
          ]'
    ```

---

## Cost Estimation

Baseline costs for a minimal deployment (us-east-1 pricing):

| Resource | Spec | Estimated Monthly Cost |
|----------|------|----------------------|
| EC2 t3.medium (API + claude-runner) | 2 vCPU, 4 GB RAM | ~$30 |
| Fargate (Web, 2 tasks) | 0.25 vCPU, 0.5 GB each | ~$15 |
| RDS db.t3.micro (PostgreSQL 16) | 1 vCPU, 1 GB RAM, 20 GB | ~$15 |
| ALB | Fixed + LCU charges | ~$20 |
| ECR storage | ~2 GB images | ~$1 |
| Route 53 hosted zone | 1 zone | $0.50 |
| CloudWatch Logs | Minimal | ~$2 |
| **Total** | | **~$85/month** |

Costs scale primarily with EC2 instance size (concurrent claude-runner containers consume CPU/memory on the host) and ALB traffic.

---

## Scaling Considerations

### Web (Fargate)

Scale horizontally with ECS Service Auto Scaling:

```bash
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --resource-id service/helprs/helprs-web \
  --scalable-dimension ecs:service:DesiredCount \
  --min-capacity 2 --max-capacity 10

aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --resource-id service/helprs/helprs-web \
  --scalable-dimension ecs:service:DesiredCount \
  --policy-name cpu-tracking \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration \
    'TargetValue=70,PredefinedMetricSpecification={PredefinedMetricType=ECSServiceAverageCPUUtilization}'
```

### API (EC2)

The API task is constrained to a single EC2 instance due to the Docker socket requirement. For higher throughput:

- Use a larger instance type (t3.large, t3.xlarge)
- Increase `UVICORN_WORKERS` to match available CPUs
- Each concurrent session spawns one claude-runner container -- size the instance accordingly

### Database (RDS)

- Scale vertically by changing the instance class
- Add read replicas for read-heavy workloads
- Enable Multi-AZ for high availability

### claude-runner Containers

Each session spawns one ephemeral container. Limits:

- `CONTAINER_TTL_SECONDS` prevents runaway containers (default: 900s / 15 min)
- The EC2 instance's CPU and memory limit concurrent sessions
- A t3.medium (4 GB RAM) comfortably runs 2-3 concurrent sessions

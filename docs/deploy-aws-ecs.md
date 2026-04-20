# Deploy on AWS ECS

Guide to deploy helPRs on AWS using ECS, RDS, and an Application Load Balancer.

!!! warning "Docker socket constraint"
    helPRs spawns ephemeral containers via the Docker socket. **ECS Fargate does not support Docker socket mounting.** You must use **ECS on EC2** for the API task, or run the API on a standalone EC2 instance. The Web and DB services can run on Fargate.

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
              /api/*     |          |  /*
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
    |             |   |  EC2 host via   |
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
  --vpc-security-group-ids <sg-id> \
  --no-publicly-accessible
```

!!! tip "Security group"
    The RDS security group should only allow inbound PostgreSQL (port 5432) from the ECS API task security group.

### ECR Repositories

```bash
# Create repositories for each image
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

Complete DNS validation as prompted.

---

## 2. Build and Push Images

```bash
# Login to ECR
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

# Build and push API
docker build -f infra/docker/Dockerfile.api --target production -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/api:latest apps/api
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/api:latest

# Build and push Web (with build args)
docker build -f infra/docker/Dockerfile.web --target production \
  --build-arg VITE_API_URL=https://api.yourdomain.com \
  --build-arg VITE_GITHUB_APP_SLUG=your-app-slug \
  -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/web:latest apps/web
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/web:latest

# Build and push claude-runner
docker build -f infra/docker/claude-runner/Dockerfile \
  -t <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest infra/docker/claude-runner
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
    "GITHUB_APP_PRIVATE_KEY": "<raw-pem-content>",
    "DATABASE_URL": "postgresql+asyncpg://helprs:<password>@<rds-endpoint>:5432/helprs"
  }'
```

---

## 4. ECS Cluster

```bash
aws ecs create-cluster --cluster-name helprs

# For the API task, you need an EC2 capacity provider (Docker socket requirement)
# Register an EC2 instance with the ECS agent installed
```

!!! warning "EC2 instance for API"
    The API task must run on an EC2 instance (not Fargate) to access the Docker socket. Install the ECS agent on an EC2 instance and register it with your cluster. The instance also needs the claude-runner image pre-pulled.

### Pre-pull claude-runner on EC2

SSH into the EC2 instance:

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
docker pull <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest
docker tag <account-id>.dkr.ecr.<region>.amazonaws.com/helprs/claude-runner:latest claude-runner:latest
```

---

## 5. Task Definitions

### API Task Definition

```json
{
  "family": "helprs-api",
  "requiresCompatibilities": ["EC2"],
  "networkMode": "bridge",
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
      "cpu": 512
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

### Web Task Definition

```json
{
  "family": "helprs-web",
  "requiresCompatibilities": ["FARGATE"],
  "networkMode": "awsvpc",
  "cpu": "256",
  "memory": "512",
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
      }
    }
  ]
}
```

---

## 6. Application Load Balancer

Create an ALB with two target groups:

| Target Group | Port | Health Check | Routing Rule |
|-------------|------|-------------|--------------|
| `helprs-api` | 8000 | `/health` | `api.yourdomain.com` |
| `helprs-web` | 80 | `/` | `yourdomain.com` |

```bash
# Create ALB
aws elbv2 create-load-balancer \
  --name helprs-alb \
  --subnets <subnet-1> <subnet-2> \
  --security-groups <sg-id>

# Create target groups
aws elbv2 create-target-group --name helprs-api --protocol HTTP --port 8000 \
  --vpc-id <vpc-id> --health-check-path /health

aws elbv2 create-target-group --name helprs-web --protocol HTTP --port 80 \
  --vpc-id <vpc-id> --target-type ip --health-check-path /

# HTTPS listener with host-based routing
aws elbv2 create-listener \
  --load-balancer-arn <alb-arn> \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=<acm-cert-arn> \
  --default-actions Type=forward,TargetGroupArn=<web-tg-arn>

# Add rule for API subdomain
aws elbv2 create-rule \
  --listener-arn <listener-arn> \
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
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-1>,<subnet-2>],securityGroups=[<sg-id>],assignPublicIp=ENABLED}" \
  --load-balancers targetGroupArn=<web-tg-arn>,containerName=web,containerPort=80
```

---

## 8. DNS

### Route 53

```bash
# Create A record aliases to the ALB
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

### External DNS

If your domain is not on Route 53, create CNAME records pointing to the ALB DNS name:

| Type | Host | Value |
|------|------|-------|
| CNAME | `@` or `yourdomain.com` | `helprs-alb-<id>.<region>.elb.amazonaws.com` |
| CNAME | `api` | `helprs-alb-<id>.<region>.elb.amazonaws.com` |

---

## 9. Skills and claude-runner on EC2

The EC2 instance running the API task needs the skills directory and the claude-runner image. Set up a deploy script:

```bash
#!/bin/bash
# /opt/helprs/update-skills.sh
# Run this after each deploy to sync skills from the repo

cd /opt/helprs
if [ -d "repo" ]; then
  cd repo && git pull
else
  git clone https://github.com/your-org/helprs.git repo
fi

rm -rf /opt/helprs/skills
cp -r repo/skills /opt/helprs/skills
```

Add this to your CI/CD pipeline or run it via SSM Run Command.

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
    steps:
      - uses: actions/checkout@v4

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ secrets.AWS_REGION }}

      - uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push images
        env:
          ECR_REGISTRY: ${{ steps.login-ecr.outputs.registry }}
        run: |
          # API
          docker build -f infra/docker/Dockerfile.api --target production \
            -t $ECR_REGISTRY/helprs/api:latest -t $ECR_REGISTRY/helprs/api:${{ github.sha }} apps/api
          docker push $ECR_REGISTRY/helprs/api --all-tags

          # Web
          docker build -f infra/docker/Dockerfile.web --target production \
            --build-arg VITE_API_URL=https://api.yourdomain.com \
            --build-arg VITE_GITHUB_APP_SLUG=your-app-slug \
            -t $ECR_REGISTRY/helprs/web:latest -t $ECR_REGISTRY/helprs/web:${{ github.sha }} apps/web
          docker push $ECR_REGISTRY/helprs/web --all-tags

          # claude-runner
          docker build -f infra/docker/claude-runner/Dockerfile \
            -t $ECR_REGISTRY/helprs/claude-runner:latest infra/docker/claude-runner
          docker push $ECR_REGISTRY/helprs/claude-runner --all-tags

      - name: Update ECS services
        run: |
          aws ecs update-service --cluster helprs --service helprs-api --force-new-deployment
          aws ecs update-service --cluster helprs --service helprs-web --force-new-deployment
```

---

## Cost Estimation

| Resource | Estimated Monthly Cost |
|----------|----------------------|
| EC2 t3.medium (API) | ~$30 |
| Fargate (Web, 2 tasks) | ~$15 |
| RDS db.t3.micro (PostgreSQL) | ~$15 |
| ALB | ~$20 |
| ECR storage | ~$1 |
| Route 53 hosted zone | $0.50 |
| **Total** | **~$80/month** |

---

## Scaling Considerations

- **Web**: Scale horizontally with Fargate auto-scaling (CPU/memory target tracking)
- **API**: Limited to one EC2 instance due to Docker socket requirement. For higher throughput, use a larger instance type or separate the container orchestration to a dedicated host
- **Database**: Scale RDS vertically or add read replicas
- **claude-runner**: Each session spawns one container. The EC2 instance limits concurrent sessions by available CPU/memory. Set `CONTAINER_TTL_SECONDS` to prevent runaway containers

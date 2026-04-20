# Deploy on Coolify

Step-by-step guide to deploy helPRs on [Coolify](https://coolify.io) v4. This guide assumes you have completed the [Self-Hosting Setup](self-hosting.md) (GitHub App created, secrets generated).

---

## Prerequisites

- Coolify v4 installed and accessible
- A domain with DNS control (e.g., Namecheap, Cloudflare)
- The helPRs GitHub App created ([instructions](self-hosting.md#step-1-create-a-github-app))
- All secrets generated ([instructions](self-hosting.md#step-2-configure-environment))

---

## 1. DNS Configuration

helPRs uses two domains: one for the frontend, one for the API. Create two A records pointing to your Coolify server IP:

| Type | Host | Value |
|------|------|-------|
| A | `@` | `<your-server-ip>` |
| A | `api` | `<your-server-ip>` |

This gives you `yourdomain.com` for the frontend and `api.yourdomain.com` for the API.

!!! tip "Propagation"
    DNS propagation usually takes 1-30 minutes. Verify with:
    ```bash
    dig yourdomain.com +short
    dig api.yourdomain.com +short
    ```

---

## 2. Connect Your Repository

1. In Coolify, go to **Projects** > create a new project (e.g., `helprs`)
2. In the production environment, click **+ New Resource**
3. Choose **Private Repository (with GitHub App)**
4. Follow the prompts to create a Coolify GitHub App and install it on your `helprs` repo
5. Select the repo `helprs`, set:
   - **Branch**: `main`
   - **Build Pack**: `Docker Compose`
   - **Base Directory**: `/`
   - **Docker Compose Location**: `/infra/coolify/docker-compose.prod.yml`
6. Click **Continue**

---

## 3. Environment Variables

Go to **Environment Variables** in your stack configuration. Add all variables:

### Database

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql+asyncpg://helprs:<db-password>@db:5432/helprs` |
| `POSTGRES_PASSWORD` | `<db-password>` (same password as in DATABASE_URL) |

### Security

| Variable | Value |
|----------|-------|
| `SECRET_KEY` | Output of `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `FERNET_KEY` | Output of `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ADMIN_PASSWORD` | Strong password for the `/admin` panel |
| `GITHUB_WEBHOOK_SECRET` | Must match the secret in your GitHub App settings |

### GitHub App

| Variable | Value |
|----------|-------|
| `GITHUB_APP_ID` | Numeric App ID from GitHub App settings |
| `GITHUB_CLIENT_ID` | Client ID (starts with `Iv...`) |
| `GITHUB_CLIENT_SECRET` | Client secret from GitHub App settings |
| `GITHUB_APP_PRIVATE_KEY` | Raw PEM content (see warning below) |

!!! warning "PEM key format in Coolify"
    Coolify supports multi-line values. Paste the **raw PEM content** (from `-----BEGIN RSA PRIVATE KEY-----` to `-----END RSA PRIVATE KEY-----`), NOT the base64-encoded version. The base64 format is only needed for `.env` files which don't support multi-line values.

### URLs

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://api.yourdomain.com` |
| `VITE_GITHUB_APP_SLUG` | Your GitHub App slug (e.g., `helprs-prod`) |
| `APP_BASE_URL` | `https://yourdomain.com` |
| `CORS_ORIGINS` | `["https://yourdomain.com"]` |

### Production

| Variable | Value |
|----------|-------|
| `ENVIRONMENT` | `production` |
| `CONTAINER_TTL_SECONDS` | `900` |
| `UVICORN_WORKERS` | `4` |

!!! note "`SKILLS_HOST_PATH`"
    Leave this empty for now. You'll configure it after the first deploy (see [step 7](#7-configure-skills_host_path)).

---

## 4. Domain Configuration

Go to **Configuration** > **General**:

| Field | Value |
|-------|-------|
| **Domains for api** | `https://api.yourdomain.com` |
| **Domains for web** | `https://yourdomain.com` |

Click **Save**. Coolify generates Let's Encrypt certificates automatically.

!!! warning "Domains may reset on redeploy"
    In some Coolify versions, domains get cleared when the compose file is reloaded. Check the domain fields after each deploy. If this persists, consider adding Traefik labels directly in the compose file.

---

## 5. Important Settings

### General > Build

- **Preserve Repository During Deployment**: **Enable this**. Without it, the `skills/` directory on the host will be empty and claude-runner containers won't have skills to run.

### Advanced > General

- **Auto Deploy**: Enable for automatic redeployment on push to `main`.

---

## 6. First Deploy

Click **Deploy**. Coolify will:

1. Clone the repo
2. Build the API, Web, and claude-runner images
3. Start the API, Web, and DB containers (claude-runner is build-only, not started)
4. Run Alembic migrations automatically (API entrypoint)

### Verify

```bash
# API health
curl -s https://api.yourdomain.com/health
# Expected: {"status":"ok","db":"ok"}

# Frontend
curl -s -o /dev/null -w "%{http_code}" https://yourdomain.com
# Expected: 200

# TLS certificate
curl -sv https://yourdomain.com 2>&1 | grep "issuer"
# Expected: issuer: ... Let's Encrypt ...
```

---

## 7. Configure SKILLS_HOST_PATH

After the first deploy, find the skills directory path on the host:

```bash
# SSH into your server, then:
docker inspect $(docker ps -q -f name=api) | grep -B2 -A5 skills
```

Look for the `Source` field in the skills mount. It will be something like:

```
/data/coolify/applications/<uuid>/skills
```

Go back to Coolify **Environment Variables** and set:

```
SKILLS_HOST_PATH=/data/coolify/applications/<uuid>/skills
```

Redeploy for the change to take effect.

---

## 8. Docker Socket Permissions

The API container runs as non-root (`appuser`) but needs access to the Docker socket. Check the Docker group GID on your server:

```bash
stat -c '%g' /var/run/docker.sock
```

The `docker-compose.prod.yml` has `group_add: ["${DOCKER_GID:-994}"]`. If your server's Docker GID is different from 994, add `DOCKER_GID=<your-gid>` to the environment variables in Coolify.

---

## 9. Verify claude-runner Image

```bash
# On the server:
docker images | grep claude-runner
# Should show: claude-runner:latest

docker ps | grep claude-runner
# Should be empty (it's only spawned on demand)
```

---

## 10. Install the GitHub App

1. Go to `https://yourdomain.com` and sign in with GitHub
2. Click the install button -- you'll be redirected to GitHub
3. Select which repositories to grant access to
4. After installation, go to your installation settings and add your Claude OAuth token

!!! tip "Generate a Claude token"
    ```bash
    claude setup-token
    ```
    Copy the token on a **single line** -- tokens with line breaks will fail authentication.

---

## 11. Test End-to-End

1. Open a pull request on a repository where the GitHub App is installed
2. The bot should comment on the PR with a session link
3. Click **Open session** and select the `challenge-me` skill
4. Verify that the session starts and output streams in real time

---

## Troubleshooting

### Build fails: "path not found"

The compose uses repo-root-relative paths (`./apps/api`, not `../../apps/api`). If you see path errors, ensure:

- **Base Directory** is set to `/`
- **Docker Compose Location** is `/infra/coolify/docker-compose.prod.yml`

### API can't connect to Docker socket

```
Permission denied: /run/docker.sock
```

Check that `group_add` in the compose matches your server's Docker GID. See [step 8](#8-docker-socket-permissions).

### claude-runner image not found

```
No such image: claude-runner:latest
```

The compose must include the claude-runner service with `profiles: [build-only]`. Verify it's present after reloading the compose file.

### Skills directory is empty

Enable **Preserve Repository During Deployment** in Coolify settings. Redeploy after enabling it.

### PEM key errors

```
Unable to load PEM file. MalformedFraming
```

The private key is likely base64-encoded. In Coolify, paste the raw PEM content (multi-line), not the base64 version.

### OAuth token rejected

```
Invalid bearer token
```

- Ensure the token has no whitespace or line breaks
- Regenerate with `claude setup-token` if expired
- Test locally: `CLAUDE_CODE_OAUTH_TOKEN="<token>" claude -p "hello"`

### 422 on session creation

Check that the PR comment link uses the `github_installation_id` (integer), not the internal UUID. This was fixed in commit `c637f68`.

### SSE not streaming

Coolify uses Traefik which handles SSE natively. The API sends `X-Accel-Buffering: no`. If streaming is still buffered, check that no additional proxy layer (e.g., Cloudflare) is buffering responses.

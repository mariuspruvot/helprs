# Self-Hosting Guide

Deploy helPRs from zero to a running instance. By the end you'll have helPRs connected to your GitHub org, running skills against your PRs.

---

## Prerequisites

- **Docker** (20.10+) and **Docker Compose** (v2)
- A **GitHub account** with permission to create a GitHub App
- A **Claude account** -- you'll generate an OAuth token with `claude setup-token`
- A server with a public URL if you want GitHub webhooks (or use a tunnel like ngrok for local dev)

---

## Step 1: Create a GitHub App

Go to [github.com/settings/apps/new](https://github.com/settings/apps/new) and fill in:

| Field | Value |
|-------|-------|
| **GitHub App name** | `helPRs` (or any unique name) |
| **Homepage URL** | Your domain, e.g. `https://helprs.example.com` |
| **Callback URL** | `https://your-domain.com/api/v1/auth/github/callback` |
| **Webhook URL** | `https://your-domain.com/api/v1/webhooks/github` |
| **Webhook secret** | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

### Permissions

Under **Repository permissions**:

| Permission | Access |
|------------|--------|
| Contents | Read-only |
| Pull requests | Read and write |
| Metadata | Read-only (auto-granted) |

Under **Organization permissions**:

| Permission | Access |
|------------|--------|
| Members | Read-only |

### Events

Subscribe to these webhook events:

- **Installation** -- tracks app installs/uninstalls
- **Pull request** -- triggers session creation on PR open/sync

### After creation

1. Note the **App ID** (shown at the top of the app settings page)
2. Note the **Client ID** and generate a **Client secret** (under "OAuth credentials")
3. Generate a **private key** (bottom of the page) -- downloads a `.pem` file
4. Base64-encode the private key for your `.env`:
   ```bash
   base64 -i your-app-name.YYYY-MM-DD.private-key.pem | tr -d '\n'
   ```

---

## Step 2: Configure Environment

```bash
git clone https://github.com/mariuspruvot/helprs.git
cd helprs
cp .env.example .env
```

Edit `.env` and fill in every value:

```bash
# --- Database ---
# For local dev, the defaults work. For production, use strong credentials.
DATABASE_URL=postgresql+asyncpg://helprs:helprs@db:5432/helprs

# --- Secrets ---
# JWT signing key -- keep it secret, keep it safe
SECRET_KEY=           # python -c "import secrets; print(secrets.token_urlsafe(48))"

# Encryption key for stored Claude credentials
FERNET_KEY=           # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Admin panel password (required when ENVIRONMENT=production)
ADMIN_PASSWORD=       # Choose a strong password

# --- GitHub App ---
GITHUB_APP_ID=        # Numeric ID from step 1
GITHUB_CLIENT_ID=     # From "OAuth credentials" section
GITHUB_CLIENT_SECRET= # From "OAuth credentials" section
GITHUB_WEBHOOK_SECRET= # The secret you generated for the webhook URL

# Private key -- base64-encoded PEM (see step 1)
GITHUB_APP_PRIVATE_KEY=

# --- URLs ---
# Where your frontend is accessible (used in PR comments and CORS)
APP_BASE_URL=https://helprs.example.com
CORS_ORIGINS=["https://helprs.example.com"]

# API URL as seen by the frontend (Vite build-time variable)
VITE_API_URL=https://helprs.example.com/api/v1

# --- Environment ---
ENVIRONMENT=production    # Enforces non-empty secrets and disables admin auto-auth

# --- Container ---
CONTAINER_TTL_SECONDS=900  # Max container lifetime (15 min default)
UVICORN_WORKERS=4          # API worker count

# --- Docker ---
# Absolute path to skills/ on the Docker host (for volume mounts into containers)
SKILLS_HOST_PATH=/absolute/path/to/helprs/skills

# --- Postgres (production compose only) ---
POSTGRES_PASSWORD=    # Strong password for production DB
```

> **Private key gotcha**: Docker Compose `env_file` doesn't support multi-line values. Base64-encode the PEM key as shown above, or use a `docker-compose.override.yml` with a YAML block scalar.

---

## Step 3: Deploy

### Option A: Docker Compose (simplest)

```bash
# Build and start all services
docker compose -f infra/coolify/docker-compose.prod.yml up -d --build

# Build the claude-runner image (used for running skills)
make build-runner

# Verify services are healthy
docker compose -f infra/coolify/docker-compose.prod.yml ps
```

The API runs on port 8000, the frontend on port 80. You'll need a reverse proxy (nginx, Caddy, Traefik) in front to handle TLS and route traffic.

**Reverse proxy requirements**:
- Route `/api/v1/*` to the API container (port 8000)
- Route everything else to the web container (port 80)
- **Disable response buffering for SSE**: set `X-Accel-Buffering: no` or equivalent. The API already sends this header, but your reverse proxy must not override it.
- Terminate TLS at the proxy -- neither the API nor web containers handle HTTPS.

### Option B: Coolify

If you use [Coolify](https://coolify.io) for hosting:

1. Create a new service from a Docker Compose file
2. Point it to `infra/coolify/docker-compose.prod.yml` in your repo
3. Set all environment variables from step 2 in the Coolify UI
4. Set `SKILLS_HOST_PATH` to the path on the Coolify host where skills will be mounted
5. Deploy -- Coolify handles TLS termination and domain routing

### Option C: Any Docker host (VPS, cloud)

The production compose file works on any machine with Docker:

```bash
# On your server
git clone https://github.com/mariuspruvot/helprs.git
cd helprs

# Configure environment
cp .env.example .env
# Edit .env...

# Start services
docker compose -f infra/coolify/docker-compose.prod.yml up -d --build
make build-runner

# Set up your preferred reverse proxy (Caddy example)
# Caddyfile:
#   helprs.example.com {
#       handle /api/v1/* {
#           reverse_proxy localhost:8000
#       }
#       handle {
#           reverse_proxy localhost:80
#       }
#   }
```

---

## Step 4: Install the GitHub App

1. Go to your GitHub App settings page
2. Click **Install App** in the sidebar
3. Select your organization or personal account
4. Choose which repositories to grant access to (or all)
5. Click **Install**

### Verify webhook delivery

After installation, GitHub sends an `installation.created` webhook:

1. Go to your GitHub App settings > **Advanced** > **Recent Deliveries**
2. You should see a successful delivery (green checkmark)
3. If it failed, check:
   - Is the webhook URL correct and accessible from the internet?
   - Does the webhook secret match between GitHub and your `.env`?
   - API logs: `docker compose -f infra/coolify/docker-compose.prod.yml logs api`

---

## Step 5: Configure Claude Credentials

helPRs uses BYOK -- each installation stores its own Claude credentials, encrypted at rest.

### Generate a Claude OAuth token

On your local machine (not the server):

```bash
# Install Claude Code CLI if you haven't
npm install -g @anthropic-ai/claude-code

# Generate an OAuth token
claude setup-token
```

This opens a browser for OAuth authentication and outputs a token. Copy it.

### Add credentials via the dashboard

1. Open your helPRs instance in a browser
2. Log in with GitHub (you must be an org member or the app installer)
3. Go to **Installations** and select your installation
4. In the settings, add your Claude OAuth token under the BYOK section

The token is Fernet-encrypted before storage. It's injected into containers as an ephemeral environment variable and never persisted in containers.

### Alternative: Admin panel

For direct database access, use the admin panel at `/admin`:
- **Development**: auto-authenticated (any password works)
- **Production**: requires the `ADMIN_PASSWORD` from your `.env`

---

## Step 6: Test It

1. Open a pull request on a repository where the GitHub App is installed
2. helPRs receives the webhook and creates a session
3. Navigate to your helPRs instance -- you'll see the installation and the PR session
4. Select the **challenge-me** skill to start a Socratic comprehension quiz
5. Answer the questions -- you'll see results streamed in real time
6. After completion, a score card is displayed

If you enabled **Post results to PR** in installation settings, the score card is also posted as a PR comment.

---

## Troubleshooting

### Webhook not received

- Verify the webhook URL is publicly accessible: `curl -I https://your-domain.com/api/v1/webhooks/github`
- Check GitHub App > Advanced > Recent Deliveries for error details
- Check API logs: `docker compose logs api | grep webhook`
- Ensure the webhook secret matches between GitHub and `.env`

### Container won't start

- Verify Docker socket is mounted: check that `/var/run/docker.sock` is accessible to the API container
- Verify the claude-runner image exists: `docker images | grep claude-runner`
- Check `SKILLS_HOST_PATH` is an absolute path and the directory exists on the Docker host
- Check API logs for container creation errors: `docker compose logs api | grep container`

### SSE stream not working / buffered

- Your reverse proxy must not buffer SSE responses. The API sets `X-Accel-Buffering: no` but some proxies ignore this header.
- For nginx: add `proxy_buffering off;` to the `/api/v1/` location block
- For Cloudflare: disable response buffering or use "streaming" mode
- Test raw SSE: `curl -N -H "Authorization: Bearer <token>" https://your-domain.com/api/v1/containers/sessions/<id>/stream`

### CORS errors

- Verify `CORS_ORIGINS` in `.env` includes your frontend URL (as a JSON array)
- CORS errors can also mask 500 errors -- check API logs for unhandled exceptions
- After an API rebuild (`docker compose up --build api`), re-authenticate -- `SECRET_KEY` regeneration invalidates all JWTs

### Container can't reach GitHub

- The claude-runner container needs internet access to clone repos and fetch PR metadata
- If running behind a corporate firewall, ensure containers can reach `github.com` and `api.github.com`
- Check the GitHub token is valid: `docker exec <container> gh auth status`

### Database issues

- Missing database: `docker exec helprs-db-1 psql -U helprs -c "\l"` -- verify `helprs` database exists
- Migration drift: compare `docker exec helprs-api-1 uv run alembic current` with `alembic heads`. If they differ, run migrations: `docker compose exec api uv run alembic upgrade head`
- Missing columns cause 500s that surface as CORS errors in the browser (because the error response lacks CORS headers)

### Checking logs

```bash
# All services
docker compose -f infra/coolify/docker-compose.prod.yml logs -f

# API only
docker compose -f infra/coolify/docker-compose.prod.yml logs -f api

# A specific claude-runner container
docker logs <container-id>

# List running claude-runner containers
docker ps --filter "ancestor=helprs/claude-runner:latest"
```

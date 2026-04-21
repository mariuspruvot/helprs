# Self-Hosting Guide

Deploy helPRs from zero to a running instance. By the end you'll have helPRs connected to your GitHub org, running skills against your PRs.

---

## Prerequisites

- **Docker** (20.10+) and **Docker Compose** (v2)
- A **GitHub account** with permission to create a GitHub App
- A **Claude account** -- you'll generate an OAuth token with `claude setup-token` (or use an Anthropic API key)
- A server with a public URL if you want GitHub webhooks (or use a tunnel like ngrok for local dev)

---

## Step 1: Create a GitHub App

Go to [github.com/settings/apps/new](https://github.com/settings/apps/new) and fill in:

| Field | Value |
|-------|-------|
| **GitHub App name** | `helPRs` (or any unique name) |
| **Homepage URL** | Your domain, e.g. `https://yourdomain.com` |
| **Callback URL** | `https://api.yourdomain.com/api/v1/auth/github/callback` |
| **Webhook URL** | `https://api.yourdomain.com/api/v1/webhooks/github` |
| **Webhook secret** | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

!!! note "URL format depends on your routing setup"
    The examples above use a **subdomain** setup (`api.yourdomain.com`).
    If you use **path-based routing** on a single domain, replace with
    `https://yourdomain.com/api/v1/auth/github/callback` and
    `https://yourdomain.com/api/v1/webhooks/github`.

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
3. Note the **App slug** (the URL-friendly name shown in the URL: `github.com/settings/apps/<slug>`)
4. Generate a **private key** (bottom of the page) -- downloads a `.pem` file
5. Prepare the private key for deployment (see below)

### Private key format

The PEM key must be provided to helPRs as the `GITHUB_APP_PRIVATE_KEY` environment variable. The format depends on your deployment method:

=== "`.env` file (Docker Compose, VPS)"

    Docker Compose `env_file` does not support multi-line values. Base64-encode the PEM:

    ```bash
    base64 -i your-app-name.YYYY-MM-DD.private-key.pem | tr -d '\n'
    ```

    Paste the resulting single-line string as the value of `GITHUB_APP_PRIVATE_KEY` in your `.env` file.
    The application auto-detects base64 and decodes it at startup.

=== "Coolify / platforms with multiline support"

    If your deployment platform supports multi-line environment variables (Coolify does),
    paste the **raw PEM content** directly -- no base64 encoding needed:

    ```
    -----BEGIN RSA PRIVATE KEY-----
    MIIEpAIBAAKCAQEA...
    ...
    -----END RSA PRIVATE KEY-----
    ```

    The application accepts both raw PEM and base64-encoded PEM.

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

# Private key -- base64-encoded PEM for .env, or raw PEM on platforms that support it
GITHUB_APP_PRIVATE_KEY=

# --- URLs ---
# Where your frontend is accessible (used in PR comments and CORS)
APP_BASE_URL=https://yourdomain.com
CORS_ORIGINS=["https://yourdomain.com"]

# API URL as seen by the frontend (Vite build-time variable)
# Subdomain setup:   https://api.yourdomain.com
# Path-based routing: https://yourdomain.com
VITE_API_URL=https://api.yourdomain.com

# GitHub App slug (the URL-friendly app name, used in installation links)
VITE_GITHUB_APP_SLUG=helprs

# --- Environment ---
ENVIRONMENT=production    # Enforces non-empty secrets and disables admin auto-auth

# --- Container ---
CONTAINER_TTL_SECONDS=900  # Max container lifetime (15 min default)
UVICORN_WORKERS=4          # API worker count

# --- Docker ---
# Absolute path to skills/ on the Docker host (for volume mounts into containers)
SKILLS_HOST_PATH=/absolute/path/to/helprs/skills

# Docker group ID on the host (for socket permissions)
DOCKER_GID=994             # Run: getent group docker | cut -d: -f3

# --- Postgres (production compose only) ---
POSTGRES_PASSWORD=    # Strong password for production DB
```

!!! warning "`VITE_API_URL` and `VITE_GITHUB_APP_SLUG` are build-time variables"
    These are baked into the React bundle at build time. Changing them requires rebuilding
    the web container -- setting them at runtime has no effect.

---

## Step 3: Deploy

### Option A: Docker Compose (simplest)

```bash
# Build and start all services. The claude-runner image is built as a side-
# effect and left available on the host for the API to spawn containers from.
docker compose -f infra/coolify/docker-compose.prod.yml up -d --build

# Verify services are healthy
docker compose -f infra/coolify/docker-compose.prod.yml ps
```

!!! note "About the `claude-runner` "Exited" container"
    The `claude-runner` service is a **build-only service**: `docker compose up`
    builds the image, starts the container, which exits immediately (its entrypoint
    is overridden to `/bin/true`) with `restart: "no"`. The container stays in
    `Exited (0)` state and is not restarted — but the image `claude-runner:latest`
    remains available on the host. The API spawns new containers from this image
    per session via the Docker socket.

    This pattern keeps `docker compose up --build` as the single source of truth
    for the whole stack, including the runner image.

The API runs on port 8000, the frontend on port 80. You need a reverse proxy (nginx, Caddy, Traefik) in front to handle TLS and route traffic.

**Reverse proxy requirements**:

- **Subdomain routing** (recommended): route `api.yourdomain.com` to API (port 8000), `yourdomain.com` to web (port 80)
- **Path-based routing** (alternative): route `/api/v1/*` to API, everything else to web
- **Disable response buffering for SSE**: set `X-Accel-Buffering: no` or equivalent. The API already sends this header, but your reverse proxy must not override it.
- Terminate TLS at the proxy -- neither the API nor web containers handle HTTPS.

### Option B: Coolify (recommended for VPS)

See the [Coolify deployment guide](deploy-coolify.md) for step-by-step instructions.

### Option C: AWS ECS

See the [AWS ECS deployment guide](deploy-aws-ecs.md) for cloud deployment.

### Option D: Any Docker host (VPS)

The production compose file works on any machine with Docker:

```bash
# On your server
git clone https://github.com/mariuspruvot/helprs.git
cd helprs

# Configure environment
cp .env.example .env
# Edit .env with your values...

# Start services (the claude-runner image is built as a build-only service)
docker compose -f infra/coolify/docker-compose.prod.yml up -d --build

# Set up your preferred reverse proxy (Caddy example)
# Caddyfile:
#   yourdomain.com {
#       reverse_proxy localhost:80
#   }
#   api.yourdomain.com {
#       reverse_proxy localhost:8000
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

helPRs uses BYOK -- each installation stores its own Claude credentials, encrypted at rest. Two credential types are supported:

### Option A: Claude OAuth token (recommended, zero API cost)

On your local machine (not the server):

```bash
# Install Claude Code CLI if you haven't
npm install -g @anthropic-ai/claude-code

# Generate an OAuth token
claude setup-token
```

This opens a browser for OAuth authentication and outputs a token. Copy it.

!!! warning "OAuth tokens must be single-line"
    The token from `claude setup-token` should be a single continuous string with no
    whitespace or newlines. If you copy it from a terminal and it wraps, make sure
    no line breaks are included when pasting into the dashboard.

### Option B: Anthropic API key

If you prefer to use a standard Anthropic API key (`sk-ant-...`), you can enter it instead.
API key usage is billed to your Anthropic account.

### Add credentials via the dashboard

1. Open your helPRs instance in a browser
2. Log in with GitHub (you must be an org member or the app installer)
3. Go to **Installations** and select your installation
4. In the settings, add your Claude credential (OAuth token or API key) under the BYOK section

The credential is Fernet-encrypted before storage. It's injected into containers as an ephemeral environment variable and never persisted in containers.

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

- Verify the webhook URL is publicly accessible: `curl -I https://api.yourdomain.com/api/v1/webhooks/github`
- Check GitHub App > Advanced > Recent Deliveries for error details
- Check API logs: `docker compose logs api | grep webhook`
- Ensure the webhook secret matches between GitHub and `.env`

### Container won't start

- Verify Docker socket is mounted: check that `/var/run/docker.sock` is accessible to the API container
- Verify the claude-runner image exists: `docker images | grep claude-runner` — if missing, run `docker compose up --build` (the image is built as part of the normal compose up)
- Check `SKILLS_HOST_PATH` is an absolute path and the directory exists on the Docker host
- Verify the `DOCKER_GID` matches the host's Docker group: `getent group docker | cut -d: -f3`
- Check API logs for container creation errors: `docker compose logs api | grep container`

### SSE stream not working / buffered

- Your reverse proxy must not buffer SSE responses. The API sets `X-Accel-Buffering: no` but some proxies ignore this header.
- For nginx: add `proxy_buffering off;` to the API location block
- For Cloudflare: disable response buffering or use "streaming" mode
- Test raw SSE: `curl -N -H "Authorization: Bearer <token>" https://api.yourdomain.com/api/v1/containers/sessions/<id>/stream`

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
docker ps --filter "ancestor=claude-runner:latest"
```

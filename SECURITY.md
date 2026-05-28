# Security Policy

## Supported versions

helPRs is in early development. Only the `main` branch receives security fixes. There is no LTS line.

## Reporting a vulnerability

**Please do not file public GitHub issues for security problems.**

Use GitHub's private vulnerability reporting:

1. Go to [the Security tab of the repository](https://github.com/mariuspruvot/helprs/security)
2. Click **Report a vulnerability**
3. Fill in the form with as much detail as you can (reproduction, impact, suggested fix)

If you cannot use GitHub for any reason, email **marius.pruvot@outlook.fr** with the subject line `helPRs security:`.

### What to include

- A description of the issue and the version / commit it affects
- Steps to reproduce (proof-of-concept is ideal)
- Your assessment of impact (data disclosure, RCE, auth bypass, etc.)
- Any suggested mitigation

### What to expect

- Acknowledgement within 72 hours
- A first assessment within 7 days
- Coordinated disclosure: a fix will be published before public details, and credit will be given unless you ask otherwise

## Scope

In scope:

- The API (`apps/api/`), the web app (`apps/web/`), and the runner image (`infra/docker/claude-runner/`)
- The default `docker-compose` and Coolify deployment recipes
- Container orchestration (privilege escalation, sandbox escape, credential leaks across sessions)

Out of scope:

- Vulnerabilities in upstream dependencies that have not been disclosed upstream (please report to the upstream first)
- Issues that require an attacker to already have admin / database access
- Social engineering of operators or users
- Anything depending on a misconfigured deployment that the documentation explicitly warns against

## Operator responsibilities

helPRs is self-hosted. As an operator you are responsible for:

- Keeping the host OS, Docker, and the helPRs image up to date
- Protecting the `.env` file, the Postgres volume, and the `FERNET_KEY` (loss of the key means stored Claude credentials cannot be decrypted)
- Restricting access to the `/admin` panel (set a strong `ADMIN_PASSWORD`)
- Terminating TLS at a reverse proxy (helPRs does not serve HTTPS directly)
- Treating the Docker socket mounted into the API container as a privileged surface -- only run helPRs on hosts where that is acceptable

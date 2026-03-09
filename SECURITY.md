# Security

## Reporting a vulnerability

If you believe you have found a security vulnerability in this project, please report it responsibly.

- **Preferred**: Open a [private security advisory](https://docs.github.com/en/code-security/security-advisories/adding-a-security-policy-to-your-repository) on this repository (Security tab → Advisories → New draft). This allows us to discuss and fix the issue before it is made public.
- **Alternative**: If you cannot use the GitHub advisory, contact the maintainers (e.g. via the repository owner’s GitHub profile) with a clear description of the issue and steps to reproduce.

We will acknowledge your report and aim to respond within a reasonable time. We ask that you do not disclose the issue publicly until it has been addressed.

## Security practices in this project

- Secrets (API keys, tokens, database URLs) are not committed to the repository. Use environment variables or a secret manager (e.g. GCP Secret Manager) and `.env` for local development (with `.env` in `.gitignore`).
- The Strava webhook verify token must be kept secret; it is not logged.
- If you deploy with public access, restrict production endpoints (e.g. `/profile/{athlete_id}`) using IAM, a reverse proxy, or network controls as appropriate.

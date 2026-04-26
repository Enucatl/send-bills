# Secrets

Put local secret files in this directory.

Expected files:
- `django_secret_key`
- `django_email_host_password`
- `postgres_password`

Keep the actual values out of git. This directory is tracked only so the compose
paths in `docker-compose.yml` resolve to a real location in a fresh checkout.

Recommended permissions:
- Directory: `700`
- Secret files: `600`

Apply them manually with:

```bash
chmod 700 secrets
chmod 600 secrets/django_secret_key secrets/django_email_host_password secrets/postgres_password
```

On `docker.home.arpa`, POSIX ACLs for these paths are managed in
`../puppet-control-repo/data/nodes/docker.yaml`.

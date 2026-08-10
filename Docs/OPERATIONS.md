# UniMate Operations Runbook

## Initial deployment

1. Provision a Linux server with Docker Compose and a separate encrypted backup
   destination or protected Docker volume.
2. Copy `.env.example` to `.env` and set independent random values for the
   database password, initial administrator password, and backup passphrase.
3. Set `UNIMATE_PUBLIC_ORIGIN` to the final HTTPS origin.
4. Run `docker compose up -d --build` and confirm every service is healthy.
5. Configure the university reverse proxy to forward HTTPS traffic to port
   8080 and preserve `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto`.
6. Sign in and replace the initial administrator password before uploading data.

## Routine checks

- `docker compose ps` must show the database, Redis, API, worker, web, and
  backup services running.
- `GET /api/health/live` confirms the API process; `GET /api/health/ready`
  confirms database and queue availability.
- Review the dashboard audit page for failed logins, failed runs, unexpected
  downloads, or deletion events.
- Check free disk capacity for PostgreSQL, private storage, and backups.

## Backups and recovery

The backup service creates an AES-256 encrypted package every 24 hours and
deletes packages older than `BACKUP_RETENTION_DAYS` (30 by default). Each
package has a SHA-256 checksum. Store the passphrase separately from the server.

Before restoring, stop writes and take a current snapshot:

```bash
docker compose stop web worker api backup
docker compose run --rm backup /usr/local/bin/restore.sh \
  /backups/unimate-YYYYMMDDTHHMMSSZ.tar.gz.enc
docker compose up -d
```

Verify login, run history, one artifact download, and `/api/health/ready` after
restoration. Test recovery quarterly using non-production infrastructure.

## Upgrade and rollback

1. Confirm a recent encrypted backup and record the deployed commit.
2. Run the complete test and benchmark suite on the candidate release.
3. Deploy with `docker compose up -d --build`; the API applies migrations before
   accepting traffic.
4. Check health endpoints, login, upload validation, and a small test run.
5. If verification fails, restore the prior image/commit. If the schema changed,
   restore the matching backup rather than manually editing production tables.

## Incident handling

- Queue unavailable: leave runs queued, restore Redis, and restart the worker.
- Worker failure: inspect the non-PII structured logs, restart the worker, and
  create a new run if the prior job is marked failed.
- Suspected account compromise: stop `web`, rotate the administrator password
  and deployment secrets, revoke rows in `admin_sessions`, then review audit
  downloads and deletions.
- Suspected data exposure: isolate the server, preserve audit/database evidence,
  notify the university privacy owner, and do not delete records until approved.

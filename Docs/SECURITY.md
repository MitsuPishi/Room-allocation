# Security and Data Handling

## Data boundary

Questionnaires, normalized student records, assignments, and reports remain on
the university server. Religion, ethnicity, and residence may be retained for
authorized auditing but are excluded from compatibility scoring. Application
logs and audit-event details must not include student names, identifiers, or
questionnaire values.

## Authentication and sessions

- One administrator is bootstrapped from deployment secrets.
- Passwords use Argon2id and the initial password must be changed before any
  protected operation.
- Session tokens are random, stored only as SHA-256 digests, revocable, idle for
  at most 30 minutes, and valid for at most eight hours.
- Browser cookies are Secure, HttpOnly, SameSite=Strict; modifying requests also
  require the session CSRF token.
- Five failed logins from one client within five minutes trigger throttling.

## Storage and downloads

- PostgreSQL stores normalized records and results. Original files and generated
  artifacts live in a private volume and are never exposed as static web paths.
- Every artifact request is authenticated and audited.
- Backups contain the database and private volume together, use AES-256 with
  PBKDF2, have checksums, and expire after 30 days by default.
- The university should enable full-disk encryption on the host as an additional
  at-rest control.

## Deletion

An administrator may delete a non-active run after explicit confirmation. Files
are first moved to private staging, the database transaction removes the run,
assignments, rooms, and—when unused by another run—the dataset, then staged files
are destroyed. Failure rolls staged files back. A non-identifying audit tombstone
retains only the run UUID, actor, time, and whether the dataset was deleted.

Backups age out according to the backup retention window; an operational restore
may temporarily reintroduce deleted records, so deletions must be reapplied after
any restore using the audit tombstones.

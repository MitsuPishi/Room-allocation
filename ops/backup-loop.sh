#!/bin/sh
set -eu

while true; do
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  work="$(mktemp -d "/tmp/unimate-backup-${timestamp}-XXXXXX")"
  pg_dump --format=custom --file="$work/database.dump"
  tar -C /data -czf "$work/storage.tar.gz" .
  tar -C "$work" -czf "$work/package.tar.gz" database.dump storage.tar.gz
  openssl enc -aes-256-cbc -salt -pbkdf2 \
    -in "$work/package.tar.gz" \
    -out "/backups/unimate-${timestamp}.tar.gz.enc" \
    -pass env:UNIMATE_BACKUP_PASSPHRASE
  sha256sum "/backups/unimate-${timestamp}.tar.gz.enc" > "/backups/unimate-${timestamp}.sha256"
  rm -rf "$work"
  find /backups -type f -mtime "+${BACKUP_RETENTION_DAYS:-30}" -delete
  sleep 86400
done

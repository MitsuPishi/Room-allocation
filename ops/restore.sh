#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "Usage: restore.sh /backups/unimate-TIMESTAMP.tar.gz.enc" >&2
  exit 2
fi

encrypted="$1"
checksum="${encrypted%.tar.gz.enc}.sha256"
if [ ! -f "$checksum" ]; then
  echo "Matching SHA-256 checksum file is required: $checksum" >&2
  exit 2
fi
sha256sum -c "$checksum"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
openssl enc -d -aes-256-cbc -pbkdf2 \
  -in "$encrypted" \
  -out "$work/package.tar.gz" \
  -pass env:UNIMATE_BACKUP_PASSPHRASE
tar -C "$work" -xzf "$work/package.tar.gz"
pg_restore --clean --if-exists --no-owner --dbname="$PGDATABASE" "$work/database.dump"
if [ "$(realpath /data)" != "/data" ]; then
  echo "Refusing to replace storage outside the expected /data volume." >&2
  exit 2
fi
rm -rf /data/uploads /data/artifacts
tar -C /data -xzf "$work/storage.tar.gz"
echo "Restore completed. Restart the api and worker services."

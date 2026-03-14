#!/bin/sh
# Ensure the data directory exists and is writable by the pawsino user.
# When a host bind-mount creates ./data as root, the non-root
# container user cannot write the SQLite database file.
# The container starts as root solely to fix permissions, then drops
# privileges to the pawsino user via su-exec.
mkdir -p /app/data
chown -R pawsino:pawsino /app/data
exec su-exec pawsino "$@"

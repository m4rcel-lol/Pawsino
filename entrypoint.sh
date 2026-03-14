#!/bin/sh
# Ensure the data directory is writable by the pawsino user.
# When a host bind-mount creates ./data as root, the non-root
# container user cannot write the SQLite database file.
chown -R pawsino:pawsino /app/data
exec su-exec pawsino "$@"

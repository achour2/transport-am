#!/bin/sh
# Sauvegarde nocturne de la base, conservée 30 jours.
# crontab : 0 3 * * * /srv/transbagages/deploiement/sauvegarde.sh
set -e
DEST=/srv/sauvegardes
mkdir -p "$DEST"
pg_dump transbagages | gzip > "$DEST/transbagages-$(date +%F).sql.gz"
find "$DEST" -name 'transbagages-*.sql.gz' -mtime +30 -delete

#!/usr/bin/env bash
# Démarrage (Render) : la base PostgreSQL est joignable, on prépare puis on lance le serveur
set -o errexit
python manage.py migrate --no-input
python manage.py creer_admin
if [ "$CHARGER_DEMO" = "true" ]; then
  python manage.py donnees_demo || true
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60

#!/usr/bin/env bash
# Script de construction exécuté par Render à chaque déploiement
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py creer_admin
if [ "$CHARGER_DEMO" = "true" ]; then
  python manage.py donnees_demo || true
fi

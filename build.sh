#!/usr/bin/env bash
# Construction (Render) : pas d'accès à la base ici, le réseau privé n'existe qu'au démarrage
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input

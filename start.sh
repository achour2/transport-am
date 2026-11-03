#!/usr/bin/env bash
# Démarrage (Render) : la base PostgreSQL est joignable, on prépare puis on lance le serveur
set -o errexit

# Au premier déploiement, la base peut mettre un moment à accepter les connexions : on réessaie ~2 min
for i in $(seq 1 24); do
  if python manage.py migrate --no-input; then
    break
  fi
  if [ "$i" = "24" ]; then
    echo "La base de données reste injoignable : vérifiez DATABASE_URL dans Environment." >&2
    exit 1
  fi
  echo "Base pas encore prête, nouvel essai dans 5 s ($i/24)…"
  sleep 5
done

python manage.py creer_admin
if [ "$SUPPRIMER_DEMO" = "true" ]; then
  python manage.py supprimer_demo
elif [ "$CHARGER_DEMO" = "true" ]; then
  python manage.py donnees_demo || true
fi
exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60

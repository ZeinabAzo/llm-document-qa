#!/bin/sh
# Prepares the database, then starts the command given in the Dockerfile's CMD.
set -e

python manage.py migrate --noinput

# Creates the admin user from DJANGO_SUPERUSER_USERNAME / DJANGO_SUPERUSER_PASSWORD
# (read by Django itself) on first start only.
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
    python manage.py createsuperuser --noinput \
        --email "${DJANGO_SUPERUSER_EMAIL:-admin@example.com}" 2>/dev/null \
        || echo "Superuser '$DJANGO_SUPERUSER_USERNAME' already exists."
fi

if [ "${LOAD_SAMPLE_DATA:-0}" = "1" ]; then
    python manage.py load_sample_data
fi

exec "$@"

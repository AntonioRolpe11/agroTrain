#!/bin/sh
set -e

echo "Running migrations..."
python manage.py migrate --noinput

echo "Seeding initial users..."
python manage.py seed_users

exec "$@"

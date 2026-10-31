#!/bin/sh
set -eu

python manage.py check
python manage.py migrate --noinput
python manage.py collectstatic --no-input --clear

exec "$@"

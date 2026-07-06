#!/usr/bin/env bash
# Render build script
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py seed_brock_trip
if [ "$CLEAR_EXPENSES_ONCE" = "1" ]; then
  python manage.py clear_expenses
fi
python manage.py check_media

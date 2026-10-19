#!/bin/sh
set -eu
# Application migrations are committed and applied once per release, before publish.
# Repeated container starts must never reseed or overwrite user data.
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-3000}" --workers "${WEB_CONCURRENCY:-2}" --threads 2 --timeout 60 --access-logfile - --access-logformat '%(h)s %(m)s %(s)s %(L)s'

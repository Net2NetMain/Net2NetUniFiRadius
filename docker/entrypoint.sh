#!/bin/sh
set -eu
umask 077
python -m app.configure
exec uvicorn app.main:app --host 0.0.0.0 --port 8080

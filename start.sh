#!/usr/bin/env bash

# Terminate background processes on exit
trap 'kill $(jobs -p)' EXIT

echo "=========================================================="
echo "Starting Scaleezy CRM Boutique MVP"
echo "=========================================================="

# This is the local development script, so it talks to the local Postgres unless
# told otherwise. Without this it inherited the Supabase pooler defaults from
# settings.py, and with no DB_PASSWORD in the environment every request -- login
# first among them -- died on "password authentication failed for user postgres".
# Run with USE_LOCAL_DB=False ./start.sh to point at the hosted database.
export USE_LOCAL_DB="${USE_LOCAL_DB:-True}"
echo "-> Database: $([ "$USE_LOCAL_DB" = "True" ] && echo 'local postgres (boutique_crm)' || echo 'remote')"

# Activate virtual environment and start Django
echo "-> Starting Django Backend on http://localhost:8000..."
source .venv/bin/activate
python3 manage.py runserver 0.0.0.0:8000 &

# Start Vite React dev server
echo "-> Starting Vite React Frontend on http://localhost:5173..."
cd frontend
npm run dev &

# Wait for background jobs
wait

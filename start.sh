#!/usr/bin/env bash

# Terminate background processes on exit
trap 'kill $(jobs -p)' EXIT

echo "=========================================================="
echo "Starting TryOn2Buy CRM Boutique MVP"
echo "=========================================================="

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

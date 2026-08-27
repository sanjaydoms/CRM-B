
trap 'kill $(jobs -p)' EXIT

echo "=========================================================="
echo "Starting Scaleezy CRM Boutique MVP"
echo "=========================================================="

export USE_LOCAL_DB="${USE_LOCAL_DB:-True}"
echo "-> Database: $([ "$USE_LOCAL_DB" = "True" ] && echo 'local postgres (boutique_crm)' || echo 'remote')"

echo "-> Starting Django Backend on http://localhost:8000..."
source .venv/bin/activate
python3 manage.py runserver 0.0.0.0:8000 &

echo "-> Starting Vite React Frontend on http://localhost:5173..."
cd frontend
npm run dev &

wait

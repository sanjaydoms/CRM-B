import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

# Get credentials from environment variables or use default fallback
username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@boutiquecrm.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'AdminSecure2026!')

if not User.objects.filter(username=username).exists():
    print(f"Creating superuser '{username}' for the public schema...")
    User.objects.create_superuser(username=username, email=email, password=password)
    print("Superuser created successfully.")
else:
    print(f"Superuser '{username}' already exists.")


import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@boutiquecrm.com')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not password:
    sys.exit(
        'DJANGO_SUPERUSER_PASSWORD is not set. Set it in the environment '
        '(Render > Environment) and redeploy; no superuser was created.'
    )

user, created = User.objects.get_or_create(
    username=username, defaults={'email': email},
)
user.set_password(password)
user.is_superuser = True
user.is_staff = True
user.is_active = True
user.save()
print(f"Superuser '{username}' {'created' if created else 'password rotated'}.")

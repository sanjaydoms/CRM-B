"""Create the platform superadmin in the public schema, idempotently.

Run from the Render build command (see README). Not `manage.py createsuperuser
--noinput`, which is otherwise exactly this: that command exits non-zero when
the account already exists, so it would fail the build on every redeploy after
the first.

The account it creates is the product-wide administrator -- the one that signs
in at /admin/ and sees every boutique (tenants/admin.py). It is deliberately
NOT a boutique login: it lives in the public schema, while every boutique's
users live in that boutique's own schema.
"""

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

# No fallback password. This used to default to a literal in this file, which
# is a public repository: the credential to the account that administers every
# boutique on the platform was readable by anyone, on a login page reachable
# from the internet, and a deploy that simply never set the variable was
# indistinguishable from one that did. Refusing to create the account is the
# safe failure -- the deploy stops with a message naming the fix, instead of
# succeeding with a known password.
if not password:
    sys.exit(
        'DJANGO_SUPERUSER_PASSWORD is not set. Set it in the environment '
        '(Render > Environment) and redeploy; no superuser was created.'
    )

# Rotate unconditionally rather than skipping when the account already exists.
#
# The early-out this replaces printed "already exists" and exited 0, so
# DJANGO_SUPERUSER_PASSWORD was silently ignored on every redeploy after the
# first -- and the account it left in place was the one seed_data.py creates
# with the literal password 'admin123'. That row is in the committed dump
# (boutique_crm.sql), so the credential to the console that lists, browses and
# suspends every boutique on the platform was published, and the one mechanism
# meant to replace it reported success while changing nothing.
#
# Making the environment variable authoritative on every deploy is also what
# makes this the rotation procedure: set a new value, redeploy, done. The flags
# are re-asserted for the same reason -- an account demoted by hand (or created
# by a seed script as a plain user) is put back into the state the platform
# console requires, rather than silently failing to sign in.
user, created = User.objects.get_or_create(
    username=username, defaults={'email': email},
)
user.set_password(password)
user.is_superuser = True
user.is_staff = True
user.is_active = True
user.save()
print(f"Superuser '{username}' {'created' if created else 'password rotated'}.")

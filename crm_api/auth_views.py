import logging
import uuid

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.text import slugify
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework.throttling import AnonRateThrottle
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import connection, transaction
from tenants.models import BoutiqueTenant, Domain
from tenants.provision import provision_tenant
from django_tenants.utils import schema_context
from core.roles import OWNER, resolve_user_role

logger = logging.getLogger(__name__)


def find_tenants_for_account(email_or_username):
    """Every boutique this email or username has an account in, best first.

    The owner match from the public registry is yielded first because it is
    exact and cheap; the schema scan follows.

    A generator, and that is the point. This used to return the FIRST match and
    stop, so a freelance tailor who works at two boutiques -- the same person,
    the same address, an account in each -- could only ever sign in to whichever
    schema the scan happened to reach first, with correct credentials for both.
    Which one that was depended on row order in the tenant table, so it was not
    even predictable. Yielding candidates lets the caller try each password
    against each account and stop at the one that authenticates.

    ponytail: the scan is O(number of boutiques) schema switches and runs on
    every staff login. Fine at tens. Past a hundred or so, carry a lowercased
    email -> schema map in a public-schema table and write to it wherever a User
    is created (SignupView here, TailorViewSet._ensure_user_account and
    DesignerViewSet.create_login).
    """
    with schema_context('public'):
        owner_tenant = BoutiqueTenant.objects.filter(
            owner_email=email_or_username).first()
        others = list(BoutiqueTenant.objects.exclude(schema_name='public'))

    if owner_tenant:
        yield owner_tenant

    for t in others:
        if owner_tenant and t.pk == owner_tenant.pk:
            continue
        with schema_context(t.schema_name):
            # iexact, not exact: the caller's input is lowercased, and staff
            # accounts predating that normalization still carry whatever casing
            # the owner typed.
            if (User.objects.filter(email__iexact=email_or_username).exists()
                    or User.objects.filter(
                        username__iexact=email_or_username).exists()):
                yield t


def find_tenant_for_account(email_or_username):
    """The first boutique this account belongs to, or None.

    Kept for password reset, which genuinely wants one answer: a reset link has
    to name a single schema, and sending someone two links for two boutiques
    would be worse than sending one. Login uses the generator above instead,
    because it can try each candidate.
    """
    return next(find_tenants_for_account(email_or_username), None)


class LoginThrottle(AnonRateThrottle):
    """A ceiling on password guessing, on both of the product's login doors.

    Neither LoginView nor superadmin's PlatformLoginView had any limit, and
    LoginView in particular resolves an account by searching every boutique's
    schema for a matching username -- so a single guessed username was tried
    against the whole platform at once, not against one boutique. That is what
    turned a shared staff password into unauthenticated access to any boutique
    that happened to have such an account.

    **Only failed attempts count.** A boutique is one shop on one IP address,
    and this throttles by address, so counting every login would have made a
    busy morning -- eight staff signing in, a couple of them twice -- indis-
    tinguishable from an attack, and locked the whole shop out of the only door
    the product has for an hour. Counting successes buys nothing anyway: an
    attacker who is guessing is, by definition, failing.

    That is the difference between this and DRF's own SimpleRateThrottle, which
    records in allow_request -- before the view knows whether the credentials
    were any good. So allow_request here still *checks* the history and refuses
    once it is full, but recording moves to record_failure(), which the two
    login views call only when authentication has actually failed.

    ponytail: LocMemCache, so this is per gunicorn worker -- the real ceiling
    is WEB_CONCURRENCY times the rate. Same caveat as _PasswordResetThrottle,
    and the same remedy if it ever needs to be exact: a shared cache.
    """

    scope = 'login'

    def throttle_success(self):
        """Let the request through without spending budget.

        SimpleRateThrottle appends to the history here and writes it back. This
        override is what makes the limit apply to failures alone; the entry is
        written by record_failure() instead.
        """
        return True

    @classmethod
    def record_failure(cls, request):
        """Charge one wrong password to this address.

        Safe to call for an unknown username as well as a wrong password -- both
        are guesses. Silently does nothing when the throttle is not configured
        or the caller has no usable identifier, matching allow_request's own
        behaviour rather than raising inside a login handler.
        """
        throttle = cls()
        if throttle.rate is None:
            return
        key = throttle.get_cache_key(request, None)
        if key is None:
            return
        now = throttle.timer()
        history = throttle.cache.get(key, [])
        while history and history[-1] <= now - throttle.duration:
            history.pop()
        history.insert(0, now)
        throttle.cache.set(key, history, throttle.duration)


class SignupView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        # Normalized once, here, because this is where a boutique's identity is
        # established. Nothing lowercased it before, and the duplicate check on
        # owner_email is case-sensitive, so Owner@x.com and owner@x.com were two
        # boutiques -- while django_tenants compares schema names case-
        # insensitively, so the second one's CREATE SCHEMA silently returned
        # instead of raising and left an orphan tenant row with no schema
        # behind it.
        email = (request.data.get('email_address') or '').strip().lower()
        mobile = request.data.get('mobile_number')
        password = request.data.get('password')

        # create_user() does not run AUTH_PASSWORD_VALIDATORS, so signup
        # accepted a one-character password while the form promised "min 6
        # characters", and took "not-an-email" as an address -- which then
        # became the boutique's only route back into its own account.
        if email:
            try:
                validate_email(email)
            except DjangoValidationError:
                return Response({"error": "Enter a valid email address."},
                                status=status.HTTP_400_BAD_REQUEST)
        if password:
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                return Response({"error": " ".join(exc.messages)},
                                status=status.HTTP_400_BAD_REQUEST)

        if not email or not password or not first_name or not last_name:
            return Response(
                {"error": "Please provide first_name, last_name, email_address and password"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if tenant with this email already exists in public registry
        if BoutiqueTenant.objects.filter(owner_email=email).exists():
            return Response(
                {"error": "A user with this email address already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # One transaction for the whole build-out: the tenant row, CREATE
            # SCHEMA, every tenant migration, the domain, the settings row and
            # the owner account commit together or not at all.
            #
            # This is what test2gmailcom_7159be05 proved was missing: signup
            # died mid-migrate_schemas (each migration used to commit on its
            # own), leaving a registry row whose schema stopped before 0020 --
            # unreadable by the console, unrepairable by retrying, and holding
            # the email hostage via the duplicate check above. Under one
            # transaction the same death rolls everything back, so the person
            # can simply sign up again.
            with transaction.atomic():
                # A schema name is a Postgres identifier, not a display value, and
                # making the email do both jobs caused three separate faults at
                # once. The old `email.replace('@','_').replace('.','_')
                # .replace('-','_')` flattened '@', '.', '-' and '_' onto the same
                # character, so a.b@x.com and a-b@x.com collided on one schema;
                # TenantMixin.schema_name is varchar(63) while an email can be far
                # longer; and casing forked tenants (handled above). A slug plus a
                # short random suffix fixes all three, because all three were the
                # same mistake. Nothing derives the schema name from the address --
                # login looks the tenant up by owner_email -- so this is free.
                base = slugify(email).replace('-', '_')[:50].strip('_') or 'boutique'
                if not base[0].isalpha():
                    base = f"b_{base}"[:50]
                schema_name = f"{base}_{uuid.uuid4().hex[:8]}"
            
                # Clones the pre-migrated template schema in seconds when it
                # has been provisioned (manage.py ensure_base_schema); replays
                # every migration otherwise. See tenants/provision.py.
                tenant = provision_tenant(
                    schema_name=schema_name,
                    owner_email=email,
                    name=(request.data.get('business_name') or '').strip()
                         or f"{first_name}'s Boutique"
                )
            
                # Create domain
                Domain.objects.create(
                    domain=f"{schema_name}.localhost",
                    tenant=tenant,
                    is_primary=True
                )
            
                # The tenant middleware caches schema lookups, so a schema name that
                # was probed before this boutique existed would keep resolving to
                # "unknown tenant" until the cache expired.
                from tenants.middleware import clear_tenant_cache
                clear_tenant_cache()

                # Switch connection to the tenant's new schema context
                connection.set_tenant(tenant)

                # demo=False: a real boutique starts empty.
                #
                # This used to seed four invented employees, five fabrics at another
                # business's prices and eleven priced catalogue designs into every
                # new boutique. The fabric prices are the part that matters: the
                # order wizard computes fabric_price = price_per_meter * 3, so a
                # day-one order could be assigned to a person who does not work
                # there, priced at a rate the owner never set, and printed on an
                # invoice for a customer.
                #
                # Still called rather than dropped: keeping one entry point means a
                # future addition that a real tenant DOES need lands here without
                # anyone having to remember this call site exists.
                from crm_api.utils import seed_tenant_defaults
                seed_tenant_defaults(demo=False)

                # Give the boutique its own identity from what the owner just
                # typed. Signup collected a mobile number and never used it, and no
                # BoutiqueSettings row was created at all -- so the row was
                # conjured later by get_or_create(id=1) carrying its defaults, and
                # every boutique's printed invoice showed "+91 9999999999" and
                # contact@scaleezy.com as its own contact details.
                from crm_api.models import BoutiqueSettings
                business_name = (request.data.get('business_name') or '').strip()
                business_address = (request.data.get('business_address') or '').strip()
                BoutiqueSettings.objects.update_or_create(
                    id=1,
                    defaults={
                        'name': business_name or f"{first_name}'s Boutique",
                        'email': email,
                        **({'phone': mobile} if mobile else {}),
                        **({'address': business_address} if business_address else {}),
                    },
                )

                # Create the tenant-specific user
                user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )
            
                # Create token
                token, created = Token.objects.get_or_create(user=user)
            
                return Response({
                    "token": token.key,
                    "tenant_id": tenant.schema_name,
                    "user": {
                        "id": user.id,
                        "first_name": user.first_name,
                        "last_name": user.last_name,
                        "email": user.email,
                        "username": user.username,
                        # Signup is the one payload of the three that omitted this,
                        # and App.jsx sets currentUser straight from it without
                        # re-fetching. A brand-new owner therefore had
                        # currentUser.role undefined until their first reload,
                        # which the strict owner gate at App.jsx:2677 read as
                        # "not the owner" -- so they could not assign a production
                        # stage for their whole first session. The signing-up user
                        # is always the boutique owner, by construction.
                        "role": OWNER,
                        "tailor_id": None,
                        "designer_id": None,
                    }
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            # The exception text is LOGGED, never returned. It used to be sent
            # to the caller verbatim, so an unauthenticated request could be
            # made to print database internals -- a ghost tenant schema turned
            # this into `relation "crm_api_tailor" does not exist`, naming a
            # real table and column to anyone who asked. core/exceptions.py
            # already files the traceback for an operator to read.
            logger.exception('%s failed', self.__class__.__name__)
            connection.set_schema_to_public()
            return Response({"error": "Something went wrong. Please try again."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(views.APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        # Same normalization as signup, or an owner who capitalises their email
        # in the login box cannot sign in to the boutique they created.
        username_or_email = (request.data.get('username') or '').strip().lower()
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response(
                {"error": "Please provide email/username and password"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Every boutique this address has an account in, tried in turn.
        #
        # This used to take the FIRST match and stop, so a freelance tailor who
        # works at two boutiques could only ever sign in to whichever schema the
        # scan reached first -- with valid credentials for both, and no way to
        # say which one they meant. Trying each candidate and stopping at the
        # one whose password matches is what makes the second account reachable.
        suspended = None
        authenticated = None
        for candidate in find_tenants_for_account(username_or_email):
            # Login resolves its own tenant and never sends an X-Tenant-ID, so
            # TenantHeaderMiddleware's suspension check has nothing to act on
            # and this request would otherwise walk past it -- handing out a
            # token every subsequent call then refuses. Remembered rather than
            # returned immediately: a suspended boutique must not stop the
            # person signing in to a different one that is fine.
            if not candidate.is_active:
                suspended = candidate
                continue

            connection.set_tenant(candidate)
            user_obj = (User.objects.filter(email__iexact=username_or_email).first()
                        or User.objects.filter(username__iexact=username_or_email).first())
            # authenticate() matches username exactly, so hand it the stored
            # spelling rather than the lowercased input.
            username_to_auth = user_obj.username if user_obj else username_or_email
            user = authenticate(username=username_to_auth, password=password)
            if user:
                authenticated = (candidate, user)
                break
            connection.set_schema_to_public()

        if authenticated is None:
            connection.set_schema_to_public()
            # Said plainly rather than as a generic credential error: if the
            # only boutique this address belongs to is suspended, the password
            # was probably right, and "invalid credentials" would send the owner
            # to the reset form instead of to support.
            if suspended is not None:
                return Response(
                    {"error": "This boutique's access has been suspended. "
                              "Please contact support."},
                    status=status.HTTP_403_FORBIDDEN
                )
            LoginThrottle.record_failure(request)
            return Response(
                {"error": "Invalid login credentials. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        tenant, user = authenticated
        # Re-assert the schema, because breaking out of the loop above closed
        # the generator -- and find_tenants_for_account yields from INSIDE a
        # schema_context, whose __exit__ then restored the connection to public.
        # So by the time control reaches here the tenant has been unset, and the
        # very next ORM call (resolve_user_role reading tailor_profile) fails
        # with `relation "crm_api_tailor" does not exist`. `user` was already
        # loaded, so it survives the switch; nothing else has been read yet.
        connection.set_tenant(tenant)

        try:
            role = resolve_user_role(user)
            tailor_id = user.tailor_profile.id if getattr(user, 'tailor_profile', None) else None
            designer_id = user.designer_profile.id if getattr(user, 'designer_profile', None) else None

            token, created = Token.objects.get_or_create(user=user)
            return Response({
                "token": token.key,
                "tenant_id": tenant.schema_name,
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "username": user.username,
                    "role": role,
                    "tailor_id": tailor_id,
                    "designer_id": designer_id
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            # The exception text is LOGGED, never returned. It used to be sent
            # to the caller verbatim, so an unauthenticated request could be
            # made to print database internals -- a ghost tenant schema turned
            # this into `relation "crm_api_tailor" does not exist`, naming a
            # real table and column to anyone who asked. core/exceptions.py
            # already files the traceback for an operator to read.
            logger.exception('%s failed', self.__class__.__name__)
            connection.set_schema_to_public()
            return Response({"error": "Something went wrong. Please try again."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LogoutView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Token will be deleted within the active tenant schema
            try:
                request.user.auth_token.delete()
            except Exception:
                pass
            return Response({"success": "Successfully logged out"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = resolve_user_role(user)
        tailor_id = None
        designer_id = None
        if connection.schema_name != 'public':
            try:
                if getattr(user, 'tailor_profile', None):
                    tailor_id = user.tailor_profile.id
            except Exception:
                pass
            try:
                if getattr(user, 'designer_profile', None):
                    designer_id = user.designer_profile.id
            except Exception:
                pass

        return Response({
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "username": user.username,
            "role": role,
            "tailor_id": tailor_id,
            "designer_id": designer_id,
            "tenant_id": connection.schema_name
        }, status=status.HTTP_200_OK)

class _PasswordResetThrottle(AnonRateThrottle):
    """Speed bump on the one endpoint that sends mail on a stranger's say-so.

    ponytail: DRF throttling counts in the cache, and no CACHES is configured,
    so this is LocMemCache -- per gunicorn worker. With WEB_CONCURRENCY=2 the
    real ceiling is twice the number below. That is a speed bump, not a
    guarantee, and it is the right size for the risk: the endpoint reveals
    nothing and the worst case is a mailbox filling up. Give it a shared cache
    (or count rows the way tenants/views.py does) if it ever needs to be exact.
    """

    scope = 'password_reset'


def make_reset_link(tenant, user):
    """A signed set-your-password link for one account.

    The payload carries the schema because every step of validating the token --
    loading the user, reading the password hash it is derived from -- happens
    inside the boutique's own schema, and the browser following this link has no
    session and no X-Tenant-ID yet. The schema name is not a secret: it is
    already in localStorage and on every API call as a header.

    The token is Django's own `default_token_generator`, which derives from the
    user's password hash and last_login. That gives two properties this flow
    depends on and neither of which is written here: the link stops working the
    moment it is used (the hash it was derived from has changed), and it expires
    after PASSWORD_RESET_TIMEOUT.

    Extracted so the console can *obtain* a link rather than only cause one to be
    emailed. With no SMTP configured -- which is production's current state --
    emailing was the same as discarding, and an administrator had no way to give
    a boutique owner access at all.

    Caller must already know the tenant. Resolving it from the address instead is
    what the console cannot do safely: staff emails are unique inside a schema
    and nothing makes them unique across schemas.
    """
    with schema_context(tenant.schema_name):
        payload = '.'.join([
            tenant.schema_name,
            urlsafe_base64_encode(force_bytes(user.pk)),
            default_token_generator.make_token(user),
        ])
    return f"{settings.PASSWORD_RESET_BASE_URL}?reset={payload}"


def send_reset_email(tenant, user, link, address):
    """Mail `link` to `address`. Returns True if it was accepted for delivery.

    Never raises. A mail failure must not change what a caller tells the world:
    for the public endpoint, which addresses bounce is the same directory the
    generic answer exists to withhold; for the console, the link is returned to
    the administrator anyway and is useful without the email.

    The link is logged on failure because with no SMTP configured the log is the
    only place an operator could otherwise recover it from.
    """
    boutique = tenant.name or 'your boutique'
    try:
        send_mail(
            subject=f"Set your {boutique} password",
            message=(
                f"An administrator has issued a sign-in link for {address} on "
                f"{boutique}.\n\n"
                f"Open it to choose your password:\n\n{link}\n\n"
                f"The link stops working in "
                f"{settings.PASSWORD_RESET_TIMEOUT // 60} minutes, and once you "
                f"use it every device signed in to this account is signed out.\n\n"
                f"If you were not expecting this, ignore it -- nothing has "
                f"changed until the link is used."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[address],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception('reset email failed for %s (link: %s)', address, link)
        return False


class PasswordResetRequestView(views.APIView):
    """Start a reset. Answers the same way whether or not the account exists.

    A different answer for a known address turns this into a directory of every
    boutique owner and staff member on the platform, which is worth more to an
    attacker than the reset itself.
    """

    permission_classes = [AllowAny]
    throttle_classes = [_PasswordResetThrottle]

    # Said once, so the two exits below cannot drift into telling the caller
    # apart by wording.
    ANSWER = {"detail": "If that account exists, a reset link is on its way."}

    def post(self, request):
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response({"error": "Enter your email address."},
                            status=status.HTTP_400_BAD_REQUEST)

        tenant = find_tenant_for_account(email)
        if not tenant:
            return Response(self.ANSWER, status=status.HTTP_200_OK)

        with schema_context(tenant.schema_name):
            user = (User.objects.filter(email__iexact=email).first()
                    or User.objects.filter(username__iexact=email).first())
            if not user or not user.is_active:
                return Response(self.ANSWER, status=status.HTTP_200_OK)

            address = user.email or email

        link = make_reset_link(tenant, user)
        send_reset_email(tenant, user, link, address)

        return Response(self.ANSWER, status=status.HTTP_200_OK)


class PasswordResetConfirmView(views.APIView):
    """Finish a reset: swap the password and sign every device out."""

    permission_classes = [AllowAny]
    throttle_classes = [_PasswordResetThrottle]

    INVALID = {"error": "This reset link is no longer valid. "
                        "Please request a new one."}

    def post(self, request):
        payload = (request.data.get('token') or '').strip()
        password = request.data.get('password') or ''

        parts = payload.split('.')
        if len(parts) != 3:
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)
        schema_name, uidb64, token = parts

        with schema_context('public'):
            tenant = BoutiqueTenant.objects.filter(
                schema_name=schema_name).first()
        if not tenant:
            return Response(self.INVALID, status=status.HTTP_400_BAD_REQUEST)
        # A suspended boutique is refused at login; letting it set a password
        # here would be a way back in through the side door.
        if not tenant.is_active:
            return Response(
                {"error": "This boutique's access has been suspended. "
                          "Please contact support."},
                status=status.HTTP_403_FORBIDDEN)

        with schema_context(tenant.schema_name):
            try:
                user = User.objects.get(
                    pk=force_str(urlsafe_base64_decode(uidb64)))
            except (User.DoesNotExist, ValueError, TypeError, OverflowError):
                return Response(self.INVALID,
                                status=status.HTTP_400_BAD_REQUEST)

            # Checked before the password rules, so a bad link is never told
            # apart from a good one by which complaint comes back.
            if not default_token_generator.check_token(user, token):
                return Response(self.INVALID,
                                status=status.HTTP_400_BAD_REQUEST)

            try:
                validate_password(password, user)
            except DjangoValidationError as exc:
                return Response({"error": " ".join(exc.messages)},
                                status=status.HTTP_400_BAD_REQUEST)

            user.set_password(password)
            user.save(update_fields=['password'])

            # Both of these are the point of a reset rather than housekeeping.
            # Deleting the auth token signs out whoever was holding it -- which
            # is the thief, in the case this feature exists for. Changing the
            # hash also invalidates the reset token itself, since the generator
            # derives it from the hash, so the link cannot be replayed.
            Token.objects.filter(user=user).delete()

        return Response({"detail": "Your password has been changed. "
                                   "Please sign in."},
                        status=status.HTTP_200_OK)


class SeedDataView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Owner-only. This re-creates the default staff, fabrics and designs, so
        # signed in as any tailor it resurrected rows the owner had deliberately
        # deleted -- and IsAuthenticated alone let them.
        if resolve_user_role(request.user) != OWNER:
            return Response({"error": "Only the boutique owner can seed data."},
                            status=status.HTTP_403_FORBIDDEN)

        from crm_api.utils import seed_tenant_defaults
        try:
            seed_tenant_defaults()
            return Response({"success": "Tenant data seeded successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

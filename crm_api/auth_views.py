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
from django.db import connection
from tenants.models import BoutiqueTenant, Domain
from django_tenants.utils import schema_context
from core.roles import OWNER, resolve_user_role

logger = logging.getLogger(__name__)


def find_tenants_for_account(email_or_username):
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
            if (User.objects.filter(email__iexact=email_or_username).exists()
                    or User.objects.filter(
                        username__iexact=email_or_username).exists()):
                yield t


def find_tenant_for_account(email_or_username):
    return next(find_tenants_for_account(email_or_username), None)


class LoginThrottle(AnonRateThrottle):

    scope = 'login'

    def throttle_success(self):
        return True

    @classmethod
    def record_failure(cls, request):
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
        email = (request.data.get('email_address') or '').strip().lower()
        mobile = request.data.get('mobile_number')
        password = request.data.get('password')

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

        
        if BoutiqueTenant.objects.filter(owner_email=email).exists():
            return Response(
                {"error": "A user with this email address already exists"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            base = slugify(email).replace('-', '_')[:50].strip('_') or 'boutique'
            if not base[0].isalpha():
                base = f"b_{base}"[:50]
            schema_name = f"{base}_{uuid.uuid4().hex[:8]}"
            
            tenant = BoutiqueTenant.objects.create(
                schema_name=schema_name,
                owner_email=email,
                name=(request.data.get('business_name') or '').strip()
                     or f"{first_name}'s Boutique"
            )
            
            Domain.objects.create(
                domain=f"{schema_name}.localhost",
                tenant=tenant,
                is_primary=True
            )

            
            from tenants.middleware import clear_tenant_cache
            clear_tenant_cache()

            
            connection.set_tenant(tenant)

            from crm_api.utils import seed_tenant_defaults
            seed_tenant_defaults(demo=False)

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

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            

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
                    "role": OWNER,
                    "tailor_id": None,
                    "designer_id": None,
                }
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.exception('%s failed', self.__class__.__name__)
            connection.set_schema_to_public()
            return Response({"error": "Something went wrong. Please try again."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(views.APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
    
        username_or_email = (request.data.get('username') or '').strip().lower()
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response(
                {"error": "Please provide email/username and password"},
                status=status.HTTP_400_BAD_REQUEST
            )

        suspended = None
        authenticated = None
        for candidate in find_tenants_for_account(username_or_email):
            if not candidate.is_active:
                suspended = candidate
                continue

            connection.set_tenant(candidate)
            user_obj = (User.objects.filter(email__iexact=username_or_email).first()
                        or User.objects.filter(username__iexact=username_or_email).first())
            username_to_auth = user_obj.username if user_obj else username_or_email
            user = authenticate(username=username_to_auth, password=password)
            if user:
                authenticated = (candidate, user)
                break
            connection.set_schema_to_public()

        if authenticated is None:
            connection.set_schema_to_public()
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
            logger.exception('%s failed', self.__class__.__name__)
            connection.set_schema_to_public()
            return Response({"error": "Something went wrong. Please try again."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LogoutView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
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
    scope = 'password_reset'


class PasswordResetRequestView(views.APIView):

    permission_classes = [AllowAny]
    throttle_classes = [_PasswordResetThrottle]
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

            payload = '.'.join([
                tenant.schema_name,
                urlsafe_base64_encode(force_bytes(user.pk)),
                default_token_generator.make_token(user),
            ])

        link = f"{settings.PASSWORD_RESET_BASE_URL}?reset={payload}"
        boutique = tenant.name or 'your boutique'
        try:
            send_mail(
                subject=f"Reset your {boutique} password",
                message=(
                    f"Someone asked to reset the password for {email} on "
                    f"{boutique}.\n\n"
                    f"Open this link to choose a new one:\n\n{link}\n\n"
                    f"The link stops working in "
                    f"{settings.PASSWORD_RESET_TIMEOUT // 60} minutes, and "
                    f"once you use it every device signed in to this account "
                    f"is signed out.\n\n"
                    f"If this was not you, ignore this email -- nothing has "
                    f"changed."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email or email],
                fail_silently=False,
            )
        except Exception:
            logger.exception('password reset email failed for %s (link: %s)',
                             email, link)

        return Response(self.ANSWER, status=status.HTTP_200_OK)


class PasswordResetConfirmView(views.APIView):

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

            Token.objects.filter(user=user).delete()

        return Response({"detail": "Your password has been changed. "
                                   "Please sign in."},
                        status=status.HTTP_200_OK)


class SeedDataView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
    
        if resolve_user_role(request.user) != OWNER:
            return Response({"error": "Only the boutique owner can seed data."},
                            status=status.HTTP_403_FORBIDDEN)

        from crm_api.utils import seed_tenant_defaults
        try:
            seed_tenant_defaults()
            return Response({"success": "Tenant data seeded successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

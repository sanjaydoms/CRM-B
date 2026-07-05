from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import connection
from tenants.models import BoutiqueTenant, Domain
from django_tenants.utils import schema_context

class SignupView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        email = request.data.get('email_address')
        mobile = request.data.get('mobile_number')
        password = request.data.get('password')

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
            # Create a clean schema name from email
            schema_name = email.replace('@', '_').replace('.', '_').replace('-', '_')
            
            # Create tenant (triggers migrations automatically)
            tenant = BoutiqueTenant.objects.create(
                schema_name=schema_name,
                owner_email=email,
                name=f"{first_name}'s Boutique"
            )
            
            # Create domain
            Domain.objects.create(
                domain=f"{schema_name}.localhost",
                tenant=tenant,
                is_primary=True
            )
            
            # Switch connection to the tenant's new schema context
            connection.set_tenant(tenant)

            # Seed default catalog and tailors for the new schema
            from crm_api.utils import seed_tenant_defaults
            seed_tenant_defaults()

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
                    "username": user.username
                }
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            # Fallback to public connection on error
            connection.set_schema_to_public()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LoginView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username_or_email = request.data.get('username')
        password = request.data.get('password')

        if not username_or_email or not password:
            return Response(
                {"error": "Please provide email/username and password"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Lookup tenant in public registry
        tenant = BoutiqueTenant.objects.filter(owner_email=username_or_email).first()
        if not tenant:
            # Search other schemas for a user with this email/username
            for t in BoutiqueTenant.objects.exclude(schema_name='public'):
                with schema_context(t.schema_name):
                    if User.objects.filter(email=username_or_email).exists() or User.objects.filter(username=username_or_email).exists():
                        tenant = t
                        break

        if not tenant:
            return Response(
                {"error": "Invalid login credentials. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Switch connection to the tenant's schema
            connection.set_tenant(tenant)

            username_to_auth = username_or_email
            if '@' in username_or_email:
                user_obj = User.objects.filter(email=username_or_email).first()
                if user_obj:
                    username_to_auth = user_obj.username

            user = authenticate(username=username_to_auth, password=password)
            if not user:
                # Revert schema context on failure
                connection.set_schema_to_public()
                return Response(
                    {"error": "Invalid login credentials. Please try again."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Check if they have a tailor profile
            role = 'Owner'
            tailor_id = None
            if hasattr(user, 'tailor_profile') and user.tailor_profile:
                role = user.tailor_profile.role
                tailor_id = user.tailor_profile.id

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
                    "tailor_id": tailor_id
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            connection.set_schema_to_public()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class LogoutView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Token will be deleted within the active tenant schema
            request.user.auth_token.delete()
            return Response({"success": "Successfully logged out"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MeView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = 'Owner'
        tailor_id = None
        if hasattr(user, 'tailor_profile') and user.tailor_profile:
            role = user.tailor_profile.role
            tailor_id = user.tailor_profile.id

        return Response({
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "username": user.username,
            "role": role,
            "tailor_id": tailor_id
        }, status=status.HTTP_200_OK)

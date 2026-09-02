"""Registering and forgetting a device.

Two endpoints, and the interesting decisions are in what they refuse.

They are IsAuthenticated rather than the project default RolePermission, and
that is deliberate: RolePermission answers False for a Designer on everything
outside the Design Studio, so the default would have let a designer sign in to
the Android app and never receive a notification -- silently, because
registration is something the app does in the background and nobody watches it
succeed. Every signed-in staff member may register the device they are holding.

The token is not a secret in the sense a password is, but it is a capability:
whoever holds it can be sent notifications addressed to this boutique's staff.
So a device is always bound to the caller's own account -- never to a user id in
the request body.
"""

from rest_framework import status, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from crm_api.models import DeviceToken


class DeviceRegisterView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = (request.data.get('token') or '').strip()
        platform = (request.data.get('platform') or 'android').strip().lower()
        if not token:
            return Response({'error': 'A device token is required.'},
                            status=status.HTTP_400_BAD_REQUEST)
        if platform not in dict(DeviceToken.PLATFORM_CHOICES):
            return Response({'error': 'Unknown platform.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # update_or_create on the token, not (user, token): Firebase reissues a
        # token to the same installation, and hands a RECYCLED one to a
        # different install often enough that it is documented. Keying on the
        # token means the row follows the device, and a phone handed from one
        # member of staff to another stops receiving the previous holder's
        # notifications the moment the new one signs in.
        device, created = DeviceToken.objects.update_or_create(
            token=token,
            defaults={'user': request.user, 'platform': platform, 'is_active': True},
        )
        return Response({'registered': True, 'created': created},
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        """Stop sending to this device. Called on sign-out.

        Deactivates rather than deletes, and only the caller's own device: a
        token belonging to someone else is answered 204 all the same, because
        the alternative tells a caller whether a token they guessed is real.
        """
        token = (request.data.get('token') or request.query_params.get('token') or '').strip()
        if token:
            DeviceToken.objects.filter(token=token, user=request.user).update(is_active=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

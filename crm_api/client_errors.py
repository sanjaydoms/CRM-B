"""
The one way a browser can tell this server that it crashed.

`frontend/src/App.jsx` -- the boutique workspace, and the largest single file in
the product -- had no error boundary at all. A render crash there is a white
screen: React unmounts the tree, the user sees nothing, and the server, which
answered every request correctly, has no idea. The Super Admin console's own
shell has had a boundary since it was written; the app the customers actually
use did not.

This endpoint is the server half of fixing that. It is deliberately small, and
deliberately suspicious of its input:

* **Unauthenticated is allowed.** The crash this most needs to catch is the one
  on the login screen, where there is no token yet. Refusing anonymous reports
  would blind it to exactly that.
* **Which makes it a public write endpoint**, so it is throttled per client and
  every field is length-capped before it reaches the database. A report cannot
  grow a row without bound and cannot be sent faster than the throttle.
* **Nothing here is trusted as a fact about the server.** The payload names a
  JavaScript error and a frontend route; it never sets severity, boutique or
  user, all of which are taken from the request the server can see.
"""

from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from core.exceptions import record_frontend

#: Caps applied before anything is stored. The stack is the only field allowed
#: to be large, because one line of it is useless for finding the component that
#: threw; core.exceptions caps it again at its own limit.
LIMITS = {'name': 200, 'message': 2000, 'stack': 4000, 'route': 300}


class ClientErrorThrottle(AnonRateThrottle):
    scope = 'client_error'


class ClientErrorView(views.APIView):
    """POST a browser crash. Always answers 204 -- see below."""

    permission_classes = [AllowAny]
    throttle_classes = [ClientErrorThrottle]
    authentication_classes = []

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}

        def field(key):
            value = payload.get(key)
            return ('' if value is None else str(value))[:LIMITS[key]]

        message = field('message')
        name = field('name')
        if not message and not name:
            return Response({'error': 'Nothing to report.'},
                            status=status.HTTP_400_BAD_REQUEST)

        record_frontend(request, name=name or 'Error', message=message,
                        stack=field('stack'), route=field('route'))

        # 204 whatever happens inside record_frontend, which swallows its own
        # failures. The caller is an error boundary that has already failed
        # once; handing it a 500 to deal with would turn a broken screen into a
        # broken screen with an unhandled promise rejection behind it.
        return Response(status=status.HTTP_204_NO_CONTENT)

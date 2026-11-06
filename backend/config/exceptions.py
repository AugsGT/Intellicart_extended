"""Errors that never leak internals: an unexpected failure is logged in full on the
server and the client only ever sees a short, generic JSON message."""
import logging

from django.core.exceptions import RequestDataTooBig, SuspiciousOperation
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger("intellicart.errors")

GENERIC = {"detail": "Something went wrong on our side. Please try again."}


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)   # DRF's own handling for validation, auth, permission, 404...
    if response is not None:
        return response

    # The client sent something it should not have (an over-size body, a malformed request): that is the
    # client's error, not ours.
    if isinstance(exc, RequestDataTooBig):
        return Response({"detail": "The request body is too large."}, status=413)
    if isinstance(exc, SuspiciousOperation):
        return Response({"detail": "Bad request."}, status=400)

    request = context.get("request")
    logger.exception("Unhandled error in %s %s", getattr(request, "method", "?"), getattr(request, "path", "?"))
    return Response(GENERIC, status=500)


def not_found(request, exception=None):
    return JsonResponse({"detail": "Not found."}, status=404)


def server_error(request):
    return JsonResponse(GENERIC, status=500)

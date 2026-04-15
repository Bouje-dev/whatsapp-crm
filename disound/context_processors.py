import os


def sentry_config(request):
    return {
        "SENTRY_DSN_FRONTEND": os.environ.get("SENTRY_DSN_FRONTEND", ""),
    }

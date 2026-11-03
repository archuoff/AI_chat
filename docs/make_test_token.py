"""Prints an access token for a user of YOUR test database (local testing only).

The template's own /auth/login cannot be used on a test machine (its router is wrapped by track_module_usage, which asks for a token
before the login itself). On the real platform the token comes from the platform's login. For local tests make one here:

    uv run python docs/engismart/make_test_token.py dev_user          (user names: see docs/engismart/seed_local_test.py)

Use it in the header  access-token: <token>  (Swagger: /docs, the lock or the header field of each call). Valid 8 hours.
It uses the SECRET_KEY of your .env file, so it only works against that same app. Never use it on a real environment."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.getcwd())

from jose import jwt  # noqa: E402

from utility.settings import settings  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("usage: make_test_token.py <username>")
payload = {"username": sys.argv[1], "token_version": 1, "exp": datetime.utcnow() + timedelta(hours=8)}
print(jwt.encode(payload, settings.SECRET_KEY, settings.ALGORITHM))

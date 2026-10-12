"""Verify a Google Identity Services ID token. The raw token is never logged or stored."""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token


ALLOWED_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class GoogleAuthError(Exception):
    def __init__(self, code, status):
        self.code = code
        self.status = status
        super().__init__(code)


def verify_google_id_token(token, client_id):
    if not isinstance(token, str) or not token.strip() or len(token) > 8192 or any(char.isspace() for char in token):
        raise GoogleAuthError("malformed", 401)
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
    except GoogleAuthError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "expired" in message:
            raise GoogleAuthError("expired", 401) from None
        if "audience" in message:
            raise GoogleAuthError("audience", 401) from None
        raise GoogleAuthError("invalid", 401) from None
    if not isinstance(claims, dict):
        raise GoogleAuthError("invalid", 401)
    if claims.get("aud") != client_id:
        raise GoogleAuthError("audience", 401)
    if claims.get("iss") not in ALLOWED_ISSUERS:
        raise GoogleAuthError("issuer", 401)
    subject = str(claims.get("sub") or "").strip()
    if not subject or len(subject) > 255:
        raise GoogleAuthError("invalid", 401)
    if claims.get("email_verified") not in (True, "true"):
        raise GoogleAuthError("unverified_email", 401)
    email = str(claims.get("email") or "").strip().lower()
    if "@" not in email or len(email) > 254:
        raise GoogleAuthError("unverified_email", 401)
    name = str(claims.get("name") or "").strip()
    return {"sub": subject, "email": email, "name": name[:160]}

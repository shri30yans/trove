"""Same-origin sign-in and explicit consent pages for Supabase OAuth clients."""

from __future__ import annotations

import re
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from starlette.responses import RedirectResponse, Response
from starlette.templating import Jinja2Templates

from app import supabase_auth
from app.config import get_config
from app.errors import ApiError

router = APIRouter()
_SESSION_COOKIE = "trove_oauth_session"
_CSRF_COOKIE = "trove_oauth_csrf"
_COOKIE_PATH = "/oauth/consent"
# Supabase documents authorization_id as an opaque query parameter. Accept a bounded URL-safe
# identifier instead of assuming a particular provider-side UUID encoding.
_AUTHORIZATION_ID = re.compile(r"^[A-Za-z0-9._~-]{1,128}$")
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates" / "mcp_oauth"))


def _valid_authorization_id(value: str | None) -> str | None:
    return value if value is not None and _AUTHORIZATION_ID.fullmatch(value) else None


def _page(request: Request, template: str, status_code: int = 200, **context: Any) -> Response:
    response = _TEMPLATES.TemplateResponse(request, template, context, status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _secure_cookie(request: Request) -> bool:
    return get_config().RUN_ENV != "local" or request.url.scheme == "https"


def _set_csrf(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        _CSRF_COOKIE,
        token,
        max_age=600,
        path=_COOKIE_PATH,
        secure=_secure_cookie(request),
        httponly=True,
        samesite="strict",
    )


def _login_page(request: Request, authorization_id: str, message: str = "") -> Response:
    csrf_token = secrets.token_urlsafe(32)
    response = _page(
        request,
        "login.html",
        title="Connect an AI app to Trove",
        authorization_id=authorization_id,
        csrf_token=csrf_token,
        message=message,
    )
    _set_csrf(response, request, csrf_token)
    return response


def _valid_csrf(request: Request, submitted: Any) -> bool:
    saved = request.cookies.get(_CSRF_COOKIE)
    return isinstance(submitted, str) and saved is not None and secrets.compare_digest(saved, submitted)


def _clear_session(response: Response, request: Request) -> None:
    response.delete_cookie(
        _SESSION_COOKIE, path=_COOKIE_PATH, secure=_secure_cookie(request), httponly=True, samesite="lax"
    )
    response.delete_cookie(
        _CSRF_COOKIE, path=_COOKIE_PATH, secure=_secure_cookie(request), httponly=True, samesite="strict"
    )
    response.headers["Cache-Control"] = "no-store"


def _origin_matches(request: Request) -> bool:
    origin = request.headers.get("origin")
    return origin is None or origin == f"{request.url.scheme}://{request.url.netloc}"


@router.get("/oauth/consent")
async def oauth_consent(request: Request) -> Response:
    authorization_id = _valid_authorization_id(request.query_params.get("authorization_id"))
    if authorization_id is None:
        return _page(
            request,
            "error.html",
            400,
            title="Invalid request",
            message="This account connection request is invalid or expired. Start again from the connected app.",
        )

    access_token = request.cookies.get(_SESSION_COOKIE)
    if not access_token:
        return _login_page(request, authorization_id)
    try:
        details = await supabase_auth.oauth_authorization_details(access_token, authorization_id)
    except ApiError as error:
        if error.status_code == 401:
            response = _login_page(request, authorization_id, "Your Trove session expired. Sign in again to continue.")
            response.delete_cookie(
                _SESSION_COOKIE,
                path=_COOKIE_PATH,
                secure=_secure_cookie(request),
                httponly=True,
                samesite="lax",
            )
            return response
        return _page(
            request,
            "error.html",
            error.status_code,
            title="Trove is unavailable",
            message=f"{error.message} Retry this page in a moment.",
        )

    redirect_url = details.get("redirect_url")
    if isinstance(redirect_url, str) and redirect_url:
        response = RedirectResponse(redirect_url, status_code=303)
        _clear_session(response, request)
        return response

    client = details.get("client")
    if not isinstance(client, dict) or not isinstance(client.get("name"), str):
        return _page(
            request,
            "error.html",
            502,
            title="Invalid request",
            message="The authorization service returned incomplete client details.",
        )

    client_uri = client.get("uri")
    redirect_uri = details.get("redirect_uri")
    user = details.get("user")
    scopes = details.get("scope")
    csrf_token = request.cookies.get(_CSRF_COOKIE) or secrets.token_urlsafe(32)
    response = _page(
        request,
        "consent.html",
        title="Review Trove access",
        account_email=user.get("email") if isinstance(user, dict) and isinstance(user.get("email"), str) else None,
        client_name=client["name"][:120],
        client_uri=client_uri[:300] if isinstance(client_uri, str) else None,
        redirect_uri=redirect_uri[:300] if isinstance(redirect_uri, str) else None,
        scopes=scopes[:500] if isinstance(scopes, str) and scopes else "No profile scopes requested",
        authorization_id=authorization_id,
        csrf_token=csrf_token,
    )
    if not request.cookies.get(_CSRF_COOKIE):
        _set_csrf(response, request, csrf_token)
    return response


@router.post("/oauth/consent/login")
async def oauth_consent_login(request: Request) -> Response:
    form = await request.form()
    authorization_id = _valid_authorization_id(str(form.get("authorization_id", "")))
    if authorization_id is None:
        return _page(
            request, "error.html", 400, title="Invalid request", message="This account connection request is invalid."
        )
    if not _valid_csrf(request, form.get("csrf_token")):
        return _login_page(request, authorization_id, "Reload this page and try signing in again.")
    if not _origin_matches(request):
        return _page(
            request,
            "error.html",
            403,
            title="Request rejected",
            message="The sign-in request origin did not match Trove.",
        )

    email = form.get("email")
    password = form.get("password")
    if not isinstance(email, str) or len(email) > 320 or not isinstance(password, str) or not 1 <= len(password) <= 256:
        return _login_page(request, authorization_id, "Enter your Trove email and password.")
    try:
        session = (await supabase_auth.sign_in(email, password))["session"]
    except ApiError as error:
        csrf_token = secrets.token_urlsafe(32)
        response = _page(
            request,
            "login.html",
            error.status_code,
            title="Connect an AI app to Trove",
            authorization_id=authorization_id,
            csrf_token=csrf_token,
            message=error.message,
        )
        _set_csrf(response, request, csrf_token)
        return response

    response = RedirectResponse(
        f"/oauth/consent?{urlencode({'authorization_id': authorization_id})}",
        status_code=303,
    )
    response.set_cookie(
        _SESSION_COOKIE,
        session["accessToken"],
        max_age=min(session["expiresIn"], 3600),
        path=_COOKIE_PATH,
        secure=_secure_cookie(request),
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        _CSRF_COOKIE, path=_COOKIE_PATH, secure=_secure_cookie(request), httponly=True, samesite="strict"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/oauth/consent/decision")
async def oauth_consent_decision(request: Request) -> Response:
    form = await request.form()
    authorization_id = _valid_authorization_id(str(form.get("authorization_id", "")))
    if authorization_id is None:
        return _page(
            request, "error.html", 400, title="Invalid request", message="This authorization request is invalid."
        )
    if not _valid_csrf(request, form.get("csrf_token")):
        return _page(
            request, "error.html", 403, title="Request rejected", message="Reload the authorization page and try again."
        )
    if not _origin_matches(request):
        return _page(
            request,
            "error.html",
            403,
            title="Request rejected",
            message="The authorization request origin did not match Trove.",
        )

    access_token = request.cookies.get(_SESSION_COOKIE)
    if not access_token:
        return _login_page(request, authorization_id, "Sign in to review this request.")
    action = form.get("action")
    if action not in {"approve", "deny"}:
        return _page(request, "error.html", 400, title="Invalid choice", message="Choose Allow or Deny to continue.")
    try:
        result = await supabase_auth.oauth_authorization_consent(access_token, authorization_id, str(action))
    except ApiError as error:
        if error.status_code == 401:
            response = _login_page(request, authorization_id, "Your Trove session expired. Sign in again to continue.")
            response.delete_cookie(
                _SESSION_COOKIE,
                path=_COOKIE_PATH,
                secure=_secure_cookie(request),
                httponly=True,
                samesite="lax",
            )
            return response
        return _page(
            request, "error.html", error.status_code, title="Could not save your choice", message=error.message
        )
    response = RedirectResponse(result["redirect_url"], status_code=303)
    _clear_session(response, request)
    return response

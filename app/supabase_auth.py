"""Server-side proxy for Supabase Auth. Provider credentials never reach the mobile client."""

from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

import httpx

from app.config import get_config
from app.errors import ApiError


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), follow_redirects=False)


def _headers(access_token: str | None = None) -> dict[str, str]:
    config = get_config()
    headers = {"apikey": config.SUPABASE_AUTH_API_KEY, "Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _provider_url(path: str) -> str:
    return f"{get_config().SUPABASE_URL.rstrip('/')}/auth/v1/{path}"


async def _post(path: str, body: dict[str, str], *, access_token: str | None = None) -> httpx.Response:
    try:
        async with _client() as client:
            return await client.post(_provider_url(path), headers=_headers(access_token), json=body)
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The sign-in service took too long to respond. Try again.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The sign-in service is unavailable. Try again.") from error


def _email_failure(response: httpx.Response) -> bool:
    """Whether this provider failure is about sending an email rather than the credentials.

    GoTrue reports both an exhausted e-mail send budget and a rejected SMTP message as
    `unexpected_failure`, so a sign-up that never produced its confirmation link is indistinguishable
    from an outage unless the provider text is read. Sign-in and refresh send no mail, so they keep
    the credential-facing mapping.
    """
    if response.status_code == 429:
        return True
    if response.status_code < 500:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    text = " ".join(str(body.get(key, "")) for key in ("error_code", "msg", "message")).lower()
    return "email" in text and any(needle in text for needle in ("rate limit", "sending", "send"))


def confirmation_redirect_url() -> str:
    """Return the public Trove landing page used after Supabase verifies signup email."""
    api_base = get_config().MCP_PUBLIC_URL.rstrip("/").removesuffix("/mcp")
    return f"{api_base}/v1/auth/confirm-email"


def _provider_error(response: httpx.Response, *, operation: str) -> ApiError:
    if response.status_code == 429 and operation not in ("sign_up", "password_reset"):
        if operation == "resend_confirmation":
            return ApiError(
                429,
                "confirmation_rate_limited",
                "Too many confirmation emails. Wait a minute and try again.",
            )
        return ApiError(429, "auth_rate_limited", "Too many sign-in attempts. Wait a moment and try again.")
    if operation in ("sign_up", "password_reset", "resend_confirmation") and _email_failure(response):
        return ApiError(
            503,
            "auth_email_unavailable",
            "Trove could not send the confirmation email. Try again in a few minutes.",
        )
    if operation == "sign_in" and response.status_code in (400, 401):
        return ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if operation == "refresh" and response.status_code in (400, 401):
        return ApiError(401, "session_expired", "Your session has expired. Sign in again.")
    if operation == "password_update" and response.status_code in (400, 422):
        return ApiError(400, "password_update_rejected", "Choose a different password and try again.")
    if 400 <= response.status_code < 500:
        return ApiError(400, "auth_request_rejected", "Check your email and password, then try again.")
    return ApiError(503, "auth_unavailable", "The sign-in service is unavailable. Try again.")


def _session(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiError(503, "auth_provider_error", "The sign-in service returned an invalid response.")
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    token_type = payload.get("token_type")
    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(refresh_token, str)
        or not refresh_token
        or not isinstance(expires_in, int)
        or expires_in <= 0
        or token_type != "bearer"
    ):
        raise ApiError(503, "auth_provider_error", "The sign-in service returned an invalid session.")
    return {"accessToken": access_token, "refreshToken": refresh_token, "expiresIn": expires_in, "tokenType": "Bearer"}


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as error:
        raise ApiError(503, "auth_provider_error", "The sign-in service returned an invalid response.") from error


async def sign_in(email: str, password: str) -> dict[str, Any]:
    response = await _post("token?grant_type=password", {"email": email, "password": password})
    if not response.is_success:
        raise _provider_error(response, operation="sign_in")
    return {"status": "authenticated", "session": _session(_json(response))}


async def sign_up(email: str, password: str) -> dict[str, Any]:
    """Create an email/password account; Supabase may require email confirmation first.

    Supabase verifies the link, then returns to the Trove HTTPS landing page.
    That page hands a validated session to the app or explains how to sign in.
    """
    redirect_to = quote(confirmation_redirect_url(), safe="")
    response = await _post(f"signup?redirect_to={redirect_to}", {"email": email, "password": password})
    if not response.is_success:
        raise _provider_error(response, operation="sign_up")
    payload = _json(response)
    if not isinstance(payload, dict):
        raise ApiError(503, "auth_provider_error", "The sign-in service returned an invalid response.")
    if payload.get("access_token") is None and payload.get("refresh_token") is None:
        return {"status": "email_confirmation_required"}
    return {"status": "authenticated", "session": _session(payload)}


async def resend_confirmation(email: str) -> None:
    """Resend the signup confirmation email to an existing unconfirmed account.

    Raises `email_not_pending` when the address has nothing to resend (unknown,
    already confirmed, or otherwise rejected) so the route can answer neutrally
    instead of leaking which addresses are registered.
    """
    redirect_to = quote(confirmation_redirect_url(), safe="")
    response = await _post(f"resend?redirect_to={redirect_to}", {"type": "signup", "email": email})
    if response.is_success:
        return
    if response.status_code in (400, 404, 422):
        raise ApiError(404, "email_not_pending", "If an unconfirmed account exists, a new email is on its way.")
    raise _provider_error(response, operation="resend_confirmation")


async def confirm_email(token_hash: str) -> dict[str, Any]:
    """Exchange a signup token hash; return a session when Supabase issues one."""
    response = await _post("verify", {"type": "signup", "token_hash": token_hash})
    if response.is_success:
        payload = _json(response)
        if not isinstance(payload, dict):
            raise ApiError(503, "auth_provider_error", "The sign-in service returned an invalid response.")
        if payload.get("access_token") is not None or payload.get("refresh_token") is not None:
            return {"status": "authenticated", "session": _session(payload)}
        return {"status": "email_confirmed"}
    if response.status_code in (400, 401, 403, 422):
        try:
            body = response.json()
        except ValueError:
            body = None
        text = ""
        if isinstance(body, dict):
            text = " ".join(str(body.get(key, "")) for key in ("error_code", "msg", "message")).lower()
        if "expir" in text:
            raise ApiError(400, "email_link_expired", "This confirmation link has expired. Request a new one.")
        raise ApiError(400, "email_link_invalid", "This confirmation link is invalid. Request a new one.")
    raise _provider_error(response, operation="confirm_email")


async def request_password_reset(email: str) -> None:
    redirect_to = quote("trove://reset-password", safe="")
    response = await _post(f"recover?redirect_to={redirect_to}", {"email": email})
    if not response.is_success:
        raise _provider_error(response, operation="password_reset")


async def update_password(access_token: str, password: str) -> None:
    try:
        async with _client() as client:
            response = await client.put(
                _provider_url("user"),
                headers=_headers(access_token),
                json={"password": password},
            )
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The sign-in service took too long to respond. Try again.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The sign-in service is unavailable. Try again.") from error
    if not response.is_success:
        if response.status_code == 401:
            raise ApiError(
                401, "password_reset_session_expired", "This password reset link has expired. Request a new one."
            )
        raise _provider_error(response, operation="password_update")


async def refresh(refresh_token: str) -> dict[str, Any]:
    response = await _post("token?grant_type=refresh_token", {"refresh_token": refresh_token})
    if not response.is_success:
        raise _provider_error(response, operation="refresh")
    return {"status": "authenticated", "session": _session(_json(response))}


async def sign_out(access_token: str) -> None:
    response = await _post("logout?scope=local", {}, access_token=access_token)
    if not response.is_success:
        if response.status_code in (400, 401):
            raise ApiError(401, "session_expired", "Your session has expired. Sign in again.")
        raise _provider_error(response, operation="sign_out")


async def oauth_authorization_details(access_token: str, authorization_id: str) -> dict[str, Any]:
    """Get Supabase OAuth request details without exposing Auth endpoints to the browser."""
    try:
        async with _client() as client:
            response = await client.get(
                _provider_url(f"oauth/authorizations/{quote(authorization_id, safe='')}"),
                headers=_headers(access_token),
            )
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The authorization service took too long to respond.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The authorization service is unavailable.") from error
    if not response.is_success:
        if response.status_code in (400, 404):
            raise ApiError(400, "oauth_request_expired", "This authorization request expired. Start linking again.")
        if response.status_code == 401:
            raise ApiError(401, "session_expired", "Your Trove session expired. Sign in again.")
        raise ApiError(503, "auth_unavailable", "The authorization service could not load this request.")
    result = _json(response)
    if not isinstance(result, dict):
        raise ApiError(503, "auth_provider_error", "The authorization service returned an invalid response.")
    return result


async def oauth_validate_session(access_token: str, expected_subject: str) -> bool:
    """Ask Supabase Auth whether an OAuth session is still active, including after revocation."""
    try:
        async with _client() as client:
            response = await client.get(_provider_url("user"), headers=_headers(access_token))
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The authorization service took too long to respond.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The authorization service is unavailable.") from error
    if response.status_code in (401, 403):
        return False
    if not response.is_success:
        raise ApiError(503, "auth_unavailable", "The authorization service could not verify this session.")
    user = _json(response)
    return isinstance(user, dict) and user.get("id") == expected_subject


async def oauth_authorization_consent(access_token: str, authorization_id: str, action: str) -> dict[str, Any]:
    """Approve or deny one pending Supabase OAuth authorization."""
    if action not in {"approve", "deny"}:
        raise ApiError(400, "invalid_oauth_decision", "Choose whether to allow or deny this connection.")
    try:
        async with _client() as client:
            response = await client.post(
                _provider_url(f"oauth/authorizations/{quote(authorization_id, safe='')}/consent"),
                headers=_headers(access_token),
                json={"action": action},
            )
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The authorization service took too long to respond.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The authorization service is unavailable.") from error
    if not response.is_success:
        if response.status_code in (400, 404):
            raise ApiError(400, "oauth_request_expired", "This authorization request expired. Start linking again.")
        if response.status_code == 401:
            raise ApiError(401, "session_expired", "Your Trove session expired. Sign in again.")
        raise ApiError(503, "auth_unavailable", "The authorization service could not save your decision.")
    result = _json(response)
    if not isinstance(result, dict) or not isinstance(result.get("redirect_url"), str):
        raise ApiError(503, "auth_provider_error", "The authorization service returned an invalid response.")
    return result


async def oauth_revoke_grant(access_token: str, client_id: str) -> None:
    """Revoke this user's OAuth grant and sessions for one registered client."""
    try:
        async with _client() as client:
            response = await client.delete(
                _provider_url("user/oauth/grants"),
                headers=_headers(access_token),
                params={"client_id": client_id},
            )
    except httpx.TimeoutException as error:
        raise ApiError(503, "auth_unavailable", "The authorization service took too long to respond.") from error
    except httpx.HTTPError as error:
        raise ApiError(503, "auth_unavailable", "The authorization service is unavailable.") from error
    if response.status_code == 404:
        return
    if response.status_code == 401:
        raise ApiError(401, "session_expired", "Your Trove session expired before access could be revoked.")
    if not response.is_success:
        raise ApiError(503, "auth_unavailable", "The authorization service could not revoke this connection.")


async def delete_user(subject: str) -> None:
    """Delete a Supabase Auth user through the server-only admin API."""
    try:
        auth_user_id = str(uuid.UUID(subject))
    except ValueError as error:
        raise ApiError(
            503, "account_deletion_unavailable", "This account cannot be deleted automatically. Contact support."
        ) from error
    try:
        async with _client() as client:
            response = await client.delete(
                _provider_url(f"admin/users/{auth_user_id}"),
                headers={
                    "apikey": get_config().SUPABASE_SECRET_KEY,
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException as error:
        raise ApiError(
            503, "account_deletion_incomplete", "Deletion is still in progress. Try again shortly."
        ) from error
    except httpx.HTTPError as error:
        raise ApiError(
            503, "account_deletion_incomplete", "Deletion is still in progress. Try again shortly."
        ) from error
    if response.status_code == 404:
        return
    if not response.is_success:
        raise ApiError(503, "account_deletion_incomplete", "Deletion is still in progress. Try again shortly.")

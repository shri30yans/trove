"""Trove API endpoints for Supabase email and password authentication."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response
from starlette.templating import Jinja2Templates

from app import supabase_auth
from app.account_deletion import account_deletion_status, cancel_account_deletion, request_account_deletion
from app.auth import Principal, require_account_deletion_auth, require_auth
from app.errors import ApiError, ApiJSONResponse
from app.schemas import (
    ConfirmEmailRequest,
    PasswordAuthRequest,
    PasswordResetRequest,
    PasswordUpdateRequest,
    RefreshAuthRequest,
    ResendConfirmationRequest,
    parse_body,
)

router = APIRouter(prefix="/auth")
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates" / "auth"))


@router.get("/confirm-email", include_in_schema=False)
async def confirm_email_landing(request: Request) -> Response:
    """Show a browser fallback after Supabase verifies an email confirmation link."""
    nonce = secrets.token_urlsafe(24)
    response = _TEMPLATES.TemplateResponse(request, "confirm_email.html", {"script_nonce": nonce})
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; img-src 'self'; connect-src 'self'; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@router.post("/sign-in")
async def sign_in(request: Request) -> ApiJSONResponse:
    payload = await parse_body(
        PasswordAuthRequest, request, "invalid_auth_request", "Enter a valid email and password."
    )
    result = await supabase_auth.sign_in(str(payload.email), payload.password)
    return ApiJSONResponse(content=result)


@router.post("/sign-up")
async def sign_up(request: Request) -> ApiJSONResponse:
    payload = await parse_body(
        PasswordAuthRequest, request, "invalid_auth_request", "Enter a valid email and password."
    )
    result = await supabase_auth.sign_up(str(payload.email), payload.password)
    return ApiJSONResponse(content=result)


@router.post("/resend-confirmation")
async def resend_confirmation(request: Request) -> ApiJSONResponse:
    payload = await parse_body(
        ResendConfirmationRequest, request, "invalid_auth_request", "Enter a valid email address."
    )
    try:
        await supabase_auth.resend_confirmation(str(payload.email))
    except ApiError as error:
        if error.code != "email_not_pending":
            raise
    return ApiJSONResponse(content={"status": "confirmation_email_requested"})


@router.post("/confirm-email")
async def confirm_email(request: Request) -> ApiJSONResponse:
    payload = await parse_body(
        ConfirmEmailRequest, request, "invalid_auth_request", "This confirmation link is invalid. Request a new one."
    )
    response = ApiJSONResponse(content=await supabase_auth.confirm_email(payload.token_hash))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@router.post("/password-reset")
async def request_password_reset(request: Request) -> ApiJSONResponse:
    payload = await parse_body(PasswordResetRequest, request, "invalid_auth_request", "Enter a valid email address.")
    await supabase_auth.request_password_reset(str(payload.email))
    return ApiJSONResponse(content={"status": "reset_email_requested"})


@router.put("/password")
async def update_own_password(request: Request, _principal: Principal = Depends(require_auth)) -> ApiJSONResponse:
    payload = await parse_body(PasswordUpdateRequest, request, "invalid_auth_request", "Enter a valid new password.")
    authorization = request.headers.get("authorization", "")
    access_token = authorization.removeprefix("Bearer ").strip()
    await supabase_auth.update_password(access_token, payload.password)
    return ApiJSONResponse(content={"status": "password_updated"})


@router.post("/refresh")
async def refresh(request: Request) -> ApiJSONResponse:
    payload = await parse_body(RefreshAuthRequest, request, "invalid_auth_request", "The saved session is invalid.")
    result = await supabase_auth.refresh(payload.refresh_token)
    return ApiJSONResponse(content=result)


@router.post("/sign-out")
async def sign_out(request: Request) -> Response:
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not authorization.removeprefix("Bearer ").strip():
        raise ApiError(401, "unauthorized", "A bearer token is required.")
    await supabase_auth.sign_out(authorization.removeprefix("Bearer ").strip())
    return Response(status_code=204)


@router.get("/account/deletion")
async def get_account_deletion(principal: Principal = Depends(require_account_deletion_auth)) -> ApiJSONResponse:
    return ApiJSONResponse(content=await account_deletion_status(principal.subject))


@router.delete("/account", status_code=202)
async def delete_own_account(principal: Principal = Depends(require_account_deletion_auth)) -> ApiJSONResponse:
    return ApiJSONResponse(content=await request_account_deletion(principal), status_code=202)


@router.post("/account/deletion/cancel", status_code=204)
async def cancel_own_account_deletion(principal: Principal = Depends(require_account_deletion_auth)) -> Response:
    await cancel_account_deletion(principal.subject)
    return Response(status_code=204)

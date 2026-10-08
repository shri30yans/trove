"""Trove API endpoints for Supabase email and password authentication."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.responses import Response

from app import supabase_auth
from app.account_deletion import account_deletion_status, cancel_account_deletion, request_account_deletion
from app.auth import Principal, require_account_deletion_auth
from app.errors import ApiError, ApiJSONResponse
from app.schemas import PasswordAuthRequest, RefreshAuthRequest, parse_body

router = APIRouter(prefix="/auth")


@router.post("/sign-in")
async def sign_in(request: Request) -> ApiJSONResponse:
    payload = await parse_body(
        PasswordAuthRequest, request, "invalid_auth_request", "Enter a valid email and password."
    )
    result = await supabase_auth.sign_in(str(payload.email), payload.password)
    return ApiJSONResponse(content=result)


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

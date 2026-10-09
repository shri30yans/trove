from __future__ import annotations

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_brand_image_endpoint_serves_the_email_logo() -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://trove.test") as client:
        response = await client.get("/brand/trove.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")

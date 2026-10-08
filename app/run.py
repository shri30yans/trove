"""Start the single Trove process: API, memory queue, and Gemini embeddings together."""

from __future__ import annotations

import uvicorn

from app.config import get_config

# Heroku sends SIGTERM and force-stops shortly after, so finish draining inside that window.
GRACEFUL_SHUTDOWN_SECONDS = 25


def main() -> None:
    config = get_config()
    uvicorn.run(
        "app.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info" if config.RUN_ENV == "local" else "warning",
        proxy_headers=True,
        forwarded_allow_ips=config.PROXY_TRUSTED_IPS,
        server_header=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        reload=config.RUN_ENV == "local",
        reload_dirs=["app"] if config.RUN_ENV == "local" else None,
    )


if __name__ == "__main__":
    main()

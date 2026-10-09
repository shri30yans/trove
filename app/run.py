"""Start the single Trove process: API, memory queue, and Gemini embeddings together."""

from __future__ import annotations

import uvicorn

from app.config import get_config

# Heroku sends SIGTERM and force-stops shortly after, so finish draining inside that window.
GRACEFUL_SHUTDOWN_SECONDS = 25


def main() -> None:
    config = get_config()
    policy = config.policy
    # Under the reloader a failed boot prints its traceback and the parent keeps watching for the
    # edit that fixes it, so `local` does not exit on a startup error the way a dyno does.
    uvicorn.run(
        "app.main:app",
        host=config.API_HOST,
        port=config.API_PORT,
        log_level="info" if policy.verbose_logging else "warning",
        proxy_headers=True,
        forwarded_allow_ips=config.PROXY_TRUSTED_IPS,
        server_header=False,
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        reload=policy.dev_reloader,
        reload_dirs=["app"] if policy.dev_reloader else None,
    )


if __name__ == "__main__":
    main()

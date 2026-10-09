"""Run a one-request Vertex AI embedding connectivity check with synthetic input."""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time

from app.config import get_config
from app.embedding import EmbeddingError, embeddings


async def _check() -> int:
    if get_config().vertex is None:
        missing = ["VERTEX_PROJECT_ID and VERTEX_SERVICE_ACCOUNT_JSON_B64"]
        sys.stdout.write(json.dumps({"status": "not_configured", "missing": missing}) + "\n")
        return 2

    started_at = time.perf_counter()
    try:
        result = await embeddings.embed_text("Synthetic Trove Vertex AI connectivity check.")
    except EmbeddingError as error:
        sys.stdout.write(json.dumps({"status": "failed", "error": str(error)}) + "\n")
        return 1
    finally:
        await embeddings.stop()

    norm = math.sqrt(sum(value * value for value in result.vector))
    sys.stdout.write(
        json.dumps(
            {
                "status": "ok",
                "provider": "vertex_ai",
                "model": result.model_id,
                "dimensions": len(result.vector),
                "unit_norm": math.isclose(norm, 1.0, rel_tol=1e-6, abs_tol=1e-6),
                "elapsed_ms": round((time.perf_counter() - started_at) * 1000),
            }
        )
        + "\n"
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_check()))


if __name__ == "__main__":
    main()

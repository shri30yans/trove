from __future__ import annotations

import asyncio
import hmac
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException, Request
from huggingface_hub import hf_hub_download
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field
from transformers import BertTokenizerFast, CLIPImageProcessor


TEXT_MODEL = "nomic-ai/nomic-embed-text-v1.5"
TEXT_REVISION = "e9b6763023c676ca8431644204f50c2b100d9aab"
VISION_MODEL = "nomic-ai/nomic-embed-vision-v1.5"
VISION_REVISION = "e3a725bce72db07ca4adb1d83da08903f3ee02f8"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_SPACE_ID = f"nomic-embed-vision-v1.5@{TEXT_REVISION}+{VISION_REVISION}"
MAX_IMAGE_BYTES = 52_428_800
MAX_TEXT_CHARS = 24_000
QUERY_MAX_TOKENS = 512
DOCUMENT_MAX_TOKENS = 2_048


@dataclass
class ModelRuntime:
    text_session: ort.InferenceSession
    vision_session: ort.InferenceSession
    tokenizer: BertTokenizerFast
    image_processor: CLIPImageProcessor


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)
    purpose: Literal["query", "document"] = "query"


def _session(path: str) -> ort.InferenceSession:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    options.intra_op_num_threads = max(1, int(os.getenv("NOMIC_ONNX_THREADS", "2")))
    options.inter_op_num_threads = 1
    return ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])


def _load_models() -> ModelRuntime:
    cache_dir = os.getenv("NOMIC_MODEL_CACHE", "/models/hf")
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    vision_path = hf_hub_download(
        repo_id=VISION_MODEL,
        filename="onnx/model_int8.onnx",
        revision=VISION_REVISION,
        cache_dir=cache_dir,
    )
    text_path = hf_hub_download(
        repo_id=TEXT_MODEL,
        filename="onnx/model_int8.onnx",
        revision=TEXT_REVISION,
        cache_dir=cache_dir,
    )
    tokenizer = BertTokenizerFast.from_pretrained(
        TEXT_MODEL,
        revision=TEXT_REVISION,
        cache_dir=cache_dir,
        model_max_length=DOCUMENT_MAX_TOKENS,
    )
    image_processor = CLIPImageProcessor.from_pretrained(
        VISION_MODEL,
        revision=VISION_REVISION,
        cache_dir=cache_dir,
    )
    text_session = _session(text_path)
    vision_session = _session(vision_path)
    _validate_model_contract(text_session, vision_session)
    return ModelRuntime(text_session, vision_session, tokenizer, image_processor)


def _validate_model_contract(text_session: ort.InferenceSession, vision_session: ort.InferenceSession) -> None:
    text_input_names = {item.name for item in text_session.get_inputs()}
    if "input_ids" not in text_input_names or "attention_mask" not in text_input_names:
        raise RuntimeError(f"Unexpected Nomic text ONNX inputs: {sorted(text_input_names)}")
    if not text_input_names.issubset({"input_ids", "attention_mask", "token_type_ids"}):
        raise RuntimeError(f"Unsupported Nomic text ONNX inputs: {sorted(text_input_names)}")
    vision_input_names = {item.name for item in vision_session.get_inputs()}
    if vision_input_names != {"pixel_values"}:
        raise RuntimeError(f"Unexpected Nomic vision ONNX inputs: {sorted(vision_input_names)}")
    for session, label in ((text_session, "text"), (vision_session, "vision")):
        outputs = session.get_outputs()
        if not outputs:
            raise RuntimeError(f"The Nomic {label} ONNX model has no outputs")
        output_shape = outputs[0].shape
        if output_shape and isinstance(output_shape[-1], int) and output_shape[-1] != EMBEDDING_DIMENSIONS:
            raise RuntimeError(
                f"Unexpected Nomic {label} ONNX hidden size: {output_shape[-1]}"
            )


def _normalize(vector: np.ndarray) -> np.ndarray:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    if vector.size != EMBEDDING_DIMENSIONS or not np.isfinite(vector).all():
        raise RuntimeError(f"Expected a finite {EMBEDDING_DIMENSIONS}-dimensional embedding")
    norm = float(np.linalg.norm(vector))
    if not norm:
        raise RuntimeError("The Nomic model returned a zero vector")
    return vector / norm


def _first_output(session: ort.InferenceSession, feed: dict[str, np.ndarray]) -> np.ndarray:
    outputs = session.run(None, feed)
    if not outputs:
        raise RuntimeError("The Nomic ONNX model returned no outputs")
    return np.asarray(outputs[0], dtype=np.float32)


def _text_embedding(runtime: ModelRuntime, text: str, purpose: str) -> np.ndarray:
    prefix = "search_query: " if purpose == "query" else "search_document: "
    max_tokens = QUERY_MAX_TOKENS if purpose == "query" else DOCUMENT_MAX_TOKENS
    encoded = runtime.tokenizer(
        [prefix + text.strip()],
        padding=True,
        truncation=True,
        max_length=max_tokens,
        return_tensors="np",
    )
    input_specs = runtime.text_session.get_inputs()
    feed: dict[str, np.ndarray] = {}
    for spec in input_specs:
        if spec.name == "input_ids":
            feed[spec.name] = np.asarray(encoded["input_ids"], dtype=np.int64)
        elif spec.name == "attention_mask":
            feed[spec.name] = np.asarray(encoded["attention_mask"], dtype=np.int64)
        elif spec.name == "token_type_ids":
            feed[spec.name] = np.asarray(encoded.get("token_type_ids", np.zeros_like(encoded["input_ids"])), dtype=np.int64)
        else:
            raise RuntimeError(f"Unsupported Nomic text ONNX input: {spec.name}")

    hidden = _first_output(runtime.text_session, feed)
    if hidden.ndim == 2:
        pooled = hidden[0]
    elif hidden.ndim == 3:
        mask = np.asarray(encoded["attention_mask"], dtype=np.float32)[..., None]
        pooled = (hidden * mask).sum(axis=1)[0] / max(float(mask.sum(axis=1)[0, 0]), 1.0)
    else:
        raise RuntimeError(f"Unexpected Nomic text output shape: {hidden.shape}")

    pooled = pooled.astype(np.float32, copy=False)
    pooled -= pooled.mean()
    pooled /= np.sqrt(np.mean(np.square(pooled)) + 1e-5)
    return _normalize(pooled)


def _image_embedding(runtime: ModelRuntime, image_bytes: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            source.load()
            image = source.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("The uploaded image format or dimensions are not supported") from error

    pixel_values = runtime.image_processor(images=image, return_tensors="np")["pixel_values"].astype(np.float32)
    input_name = runtime.vision_session.get_inputs()[0].name
    hidden = _first_output(runtime.vision_session, {input_name: pixel_values})
    if hidden.ndim == 3:
        pooled = hidden[0, 0]
    elif hidden.ndim == 2:
        pooled = hidden[0]
    else:
        raise RuntimeError(f"Unexpected Nomic vision output shape: {hidden.shape}")
    return _normalize(pooled)


@asynccontextmanager
async def lifespan(application: FastAPI):
    if os.getenv("RUN_ENV") != "local" and not SERVICE_TOKEN:
        raise RuntimeError("NOMIC_SERVICE_TOKEN must be set outside RUN_ENV=local")
    application.state.models = await asyncio.to_thread(_load_models)
    yield
    application.state.models = None


app = FastAPI(title="Trove Nomic embedding service", version="1.0.0", lifespan=lifespan)
SERVICE_TOKEN = os.getenv("NOMIC_SERVICE_TOKEN", "")


def _require_service_token(request: Request) -> None:
    if SERVICE_TOKEN and not hmac.compare_digest(
        request.headers.get("authorization", ""), f"Bearer {SERVICE_TOKEN}"
    ):
        raise HTTPException(status_code=401, detail="Invalid service token")


@app.get("/health/ready")
async def ready(request: Request):
    if getattr(request.app.state, "models", None) is None:
        raise HTTPException(status_code=503, detail="Nomic models are still loading")
    return {"ready": True, "dimensions": EMBEDDING_DIMENSIONS, "spaceId": EMBEDDING_SPACE_ID,
            "textModel": TEXT_MODEL, "textRevision": TEXT_REVISION,
            "visionModel": VISION_MODEL, "visionRevision": VISION_REVISION}


@app.post("/v1/embeddings/text")
async def embed_text(payload: TextRequest, request: Request):
    _require_service_token(request)
    runtime: ModelRuntime | None = getattr(request.app.state, "models", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Nomic models are still loading")
    try:
        embedding = await asyncio.to_thread(_text_embedding, runtime, payload.text, payload.purpose)
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Nomic text embedding failed: {type(error).__name__}") from error
    return {"model": TEXT_MODEL, "revision": TEXT_REVISION, "spaceId": EMBEDDING_SPACE_ID,
            "embedding": embedding.tolist()}


@app.post("/v1/embeddings/image")
async def embed_image(request: Request):
    _require_service_token(request)
    runtime: ModelRuntime | None = getattr(request.app.state, "models", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Nomic models are still loading")
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 50 MiB processing limit")
    if not request.headers.get("content-type", "").startswith("image/"):
        raise HTTPException(status_code=415, detail="An image content type is required")
    image_bytes = await request.body()
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 50 MiB processing limit")
    try:
        embedding = await asyncio.to_thread(_image_embedding, runtime, image_bytes)
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Nomic image embedding failed: {type(error).__name__}") from error
    return {"model": VISION_MODEL, "revision": VISION_REVISION, "spaceId": EMBEDDING_SPACE_ID,
            "embedding": embedding.tolist()}

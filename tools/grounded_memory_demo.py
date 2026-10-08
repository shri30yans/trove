#!/usr/bin/env python3
"""Probe a Vertex AI Search answer engine with synthetic Trove-like questions.

This script only queries an already-created Agent Search (formerly Vertex AI
Search) engine. It does not create cloud resources or upload user data.

Example:
  gcloud auth application-default login
  python tools/grounded_memory_demo.py --project PROJECT_ID --engine ENGINE_ID

Before running, create a disposable Agent Search engine and import two synthetic
notes through the console (for example: "Quiet work cafe: Paper Lantern Cafe
in Pune" and "Weekend trip checklist: hiking shoes, power bank, rain jacket").
The third question deliberately asks for absent sensitive data. Never point the
demo at personal memories.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


CASES = (
    ("single-note lookup", "Which cafe did I save as a quiet place to work?"),
    ("cross-note synthesis", "What do I need to bring for my weekend trip?"),
    ("unsupported question", "What is my passport number?"),
)


def access_token() -> str:
    """Get a short-lived OAuth token without printing or persisting it."""
    supplied = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
    if supplied:
        return supplied
    try:
        result = subprocess.run(
            ["gcloud", "auth", "application-default", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "No token available. Install gcloud and run `gcloud auth application-default login`, "
            "or set GOOGLE_OAUTH_ACCESS_TOKEN to a short-lived OAuth token."
        ) from error
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty OAuth token.")
    return token


def ask(
    *, project: str, engine: str, location: str, question: str,
    preamble: str, model_version: str, include_citations: bool,
    query_rephrasing: bool, ignore_adversarial: bool, ignore_non_answer_seeking: bool,
) -> dict[str, Any]:
    endpoint = (
        f"https://{location}-discoveryengine.googleapis.com/v1/projects/{project}"
        f"/locations/{location}/collections/default_collection/engines/{engine}"
        "/servingConfigs/default_search:answer"
    )
    body = {
        "query": {"text": question},
        "answerGenerationSpec": {
            "includeCitations": include_citations,
            "answerLanguageCode": "en",
            "modelSpec": {"modelVersion": model_version},
            "promptSpec": {"preamble": preamble},
            "ignoreAdversarialQuery": ignore_adversarial,
            "ignoreNonAnswerSeekingQuery": ignore_non_answer_seeking,
            "ignoreLowRelevantContent": True,
        },
        "queryUnderstandingSpec": {
            "queryRephraserSpec": {"disable": not query_rephrasing},
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Return only the status and bounded provider error text, never request headers.
        details = error.read(1200).decode("utf-8", "replace")
        raise RuntimeError(f"Agent Search returned HTTP {error.code}: {details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Agent Search: {error.reason}") from error


def print_result(label: str, response: dict[str, Any]) -> None:
    answer = response.get("answer") or {}
    print(f"\n[{label}] state={answer.get('state', 'unknown')}")
    print(answer.get("answerText") or "(no answer text)")
    for step in answer.get("steps") or []:
        description = step.get("description")
        if description:
            print(f"  step: {description} ({step.get('state', 'unknown')})")
        for action in step.get("actions") or []:
            search = action.get("searchAction") or {}
            if search.get("query"):
                print(f"  retrieved query: {search['query']}")
    for reference in answer.get("references") or []:
        chunk = reference.get("chunkInfo") or {}
        document = chunk.get("documentMetadata") or {}
        title = document.get("title") or document.get("uri") or "source"
        snippet = chunk.get("content") or ""
        print(f"  citation: {title}" + (f" — {snippet[:240]}" if snippet else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Google Cloud project ID")
    parser.add_argument("--engine", required=True, help="Agent Search engine/app ID")
    parser.add_argument("--location", default="global", help="Engine location (default: global)")
    parser.add_argument(
        "--model-version", default="gemini-2.5-flash/answer_gen/stable",
        help="Answer generation model version supported by the engine",
    )
    parser.add_argument(
        "--preamble", default="Answer only from the retrieved notes. If they do not contain the answer, say so. Cite sources.",
        help="Grounding instructions passed to answer generation",
    )
    parser.add_argument("--no-query-rephrasing", action="store_true", help="Disable query decomposition/rephrasing")
    parser.add_argument("--ignore-adversarial", action="store_true", help="Reject adversarial-looking queries")
    parser.add_argument("--ignore-non-questions", action="store_true", help="Skip queries that do not seek an answer")
    parser.add_argument("--question", action="append", help="Ask a custom question; may be repeated")
    args = parser.parse_args()
    questions = [("custom", question) for question in args.question] if args.question else list(CASES)

    try:
        for label, question in questions:
            response = ask(
                project=args.project,
                engine=args.engine,
                location=args.location,
                question=question,
                preamble=args.preamble,
                model_version=args.model_version,
                include_citations=True,
                query_rephrasing=not args.no_query_rephrasing,
                ignore_adversarial=args.ignore_adversarial,
                ignore_non_answer_seeking=args.ignore_non_questions,
            )
            print_result(label, response)
    except RuntimeError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Knowledge-base search over Amazon S3 Vectors.

Each TRORBOT knowledge base is one index in an S3 Vectors bucket. A search embeds the
question with Amazon Titan Text Embeddings V2 (the same model the stored chunks were
embedded with), queries the index, and returns the closest chunks with their source.

Enabled when TRORBOT_KB_BUCKET is set; AWS credentials come from TRORBOT_KB_AWS_PROFILE
or the standard AWS credential chain.
"""

from __future__ import annotations

import asyncio
import json
import logging

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, ProfileNotFound

from trorbot_mcp.config import settings

logger = logging.getLogger(__name__)

# KB name -> S3 Vectors index name
KB_INDEXES: dict[str, str] = {
    "context-events": "context-events",
    "program-documentation": "program-documentation",
    "annual-tror-reports": "annual-tror-reports",
}

EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024

_clients: tuple | None = None


def _get_clients() -> tuple:
    """(bedrock-runtime, s3vectors) clients, created once and reused."""
    global _clients
    if _clients is None:
        session = boto3.Session(
            profile_name=settings.trorbot_kb_aws_profile or None,
            region_name=settings.trorbot_kb_region,
        )
        config = Config(
            connect_timeout=10,
            read_timeout=settings.http_timeout,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        _clients = (session.client("bedrock-runtime", config=config), session.client("s3vectors", config=config))
    return _clients


def _search(index: str, query: str, max_results: int) -> dict:
    runtime, s3vectors = _get_clients()
    body = json.dumps({"inputText": query, "dimensions": EMBEDDING_DIMENSIONS, "normalize": True})
    embedding = json.loads(runtime.invoke_model(modelId=EMBEDDING_MODEL, body=body)["body"].read())["embedding"]
    resp = s3vectors.query_vectors(
        vectorBucketName=settings.trorbot_kb_bucket,
        indexName=index,
        queryVector={"float32": embedding},
        topK=max_results,
        returnMetadata=True,
        returnDistance=True,
    )
    passages = []
    for match in resp.get("vectors", []):
        md = match.get("metadata", {})
        passage = {
            "text": md.get("text", ""),
            "source": md.get("title", ""),
            "source_uri": md.get("source_uri", ""),
            # Cosine distance -> similarity (1.0 = identical)
            "relevance_score": round(1 - match.get("distance", 1.0), 4),
        }
        if "fiscal_year" in md:
            passage["fiscal_year"] = int(md["fiscal_year"])
        passages.append(passage)
    return {"passages": passages}


async def search_kb(kb: str, query: str, max_results: int) -> dict:
    """Search one knowledge base. Returns {passages: [...]} or an {error, hint} dict."""
    if not settings.kb_enabled:
        return {
            "error": "KB tools unavailable",
            "hint": "Set TRORBOT_KB_BUCKET (and AWS credentials) to enable knowledge base tools.",
        }
    try:
        return await asyncio.to_thread(_search, KB_INDEXES[kb], query, max_results)
    except (NoCredentialsError, ProfileNotFound):
        return {
            "error": "AWS credentials not found for KB search",
            "hint": "Set TRORBOT_KB_AWS_PROFILE to a configured AWS profile, or provide AWS credentials.",
        }
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        logger.warning("KB search failed: %s", code)
        return {
            "error": f"KB search failed ({code})",
            "hint": "Check TRORBOT_KB_BUCKET, TRORBOT_KB_REGION, and IAM access to S3 Vectors and Bedrock.",
        }
    except (BotoCoreError, Exception) as e:
        logger.warning("KB search failed: %s", type(e).__name__)
        return {"error": "KB search failed", "hint": "Try again shortly."}

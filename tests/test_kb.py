"""Knowledge-base search over S3 Vectors, with the AWS clients stubbed out."""

from __future__ import annotations

import io
import json

import pytest
from botocore.exceptions import ClientError, NoCredentialsError

from tests.conftest import call
from trorbot_mcp import kb
from trorbot_mcp.config import settings


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def invoke_model(self, modelId, body):
        self.calls.append((modelId, json.loads(body)))
        return {"body": io.BytesIO(json.dumps({"embedding": [0.1] * 1024}).encode())}


class FakeS3Vectors:
    def __init__(self, error=None):
        self.calls, self.error = [], error

    def query_vectors(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {"vectors": [
            {"key": "a", "distance": 0.25, "metadata": {
                "text": "SBA referred 562,000 loans.", "title": "sba refers loans",
                "source_uri": "s3://bucket/context-events/sba.md"}},
            {"key": "b", "distance": 0.3, "metadata": {
                "text": "FY2020 totals.", "title": "Treasury Report on Receivables FY2020",
                "source_uri": "s3://bucket/debt20.txt", "fiscal_year": 2020.0}},
        ]}


@pytest.fixture
def aws(monkeypatch):
    runtime, s3v = FakeRuntime(), FakeS3Vectors()
    monkeypatch.setattr(settings, "trorbot_kb_bucket", "trorbot-kb")
    monkeypatch.setattr(kb, "_get_clients", lambda: (runtime, s3v))
    return runtime, s3v


@pytest.mark.parametrize(("tool", "index"), [
    ("search_program_context", "context-events"),
    ("search_program_guidance", "program-documentation"),
    ("get_annual_report_insights", "annual-tror-reports"),
])
async def test_tools_query_their_own_index(client, aws, tool, index):
    runtime, s3v = aws
    out = await call(client, tool, {"query": "Why did SBA referrals drop?", "max_results": 2})

    assert s3v.calls[0]["indexName"] == index
    assert s3v.calls[0]["vectorBucketName"] == "trorbot-kb"
    assert s3v.calls[0]["topK"] == 2
    assert runtime.calls[0] == (kb.EMBEDDING_MODEL, {
        "inputText": "Why did SBA referrals drop?", "dimensions": 1024, "normalize": True})
    assert out["query"] == "Why did SBA referrals drop?"
    assert len(out["passages"]) == 2


async def test_passages_carry_text_source_and_similarity(aws):
    out = await kb.search_kb("annual-tror-reports", "FY2020 delinquent debt", 2)
    first, second = out["passages"]
    assert first == {
        "text": "SBA referred 562,000 loans.", "source": "sba refers loans",
        "source_uri": "s3://bucket/context-events/sba.md", "relevance_score": 0.75,
    }
    assert second["fiscal_year"] == 2020


async def test_disabled_without_bucket(monkeypatch):
    monkeypatch.setattr(settings, "trorbot_kb_bucket", "")
    out = await kb.search_kb("context-events", "anything at all", 3)
    assert out["error"] == "KB tools unavailable"
    assert "TRORBOT_KB_BUCKET" in out["hint"]


async def test_aws_errors_are_sanitized(monkeypatch):
    s3v = FakeS3Vectors(error=ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "arn:aws:iam::123:user/secret is not authorized"}},
        "QueryVectors"))
    monkeypatch.setattr(settings, "trorbot_kb_bucket", "trorbot-kb")
    monkeypatch.setattr(kb, "_get_clients", lambda: (FakeRuntime(), s3v))

    out = await kb.search_kb("context-events", "anything at all", 3)
    assert out["error"] == "KB search failed (AccessDeniedException)"
    assert "arn:" not in json.dumps(out)


async def test_missing_credentials_gives_actionable_hint(monkeypatch):
    def no_creds():
        raise NoCredentialsError()

    monkeypatch.setattr(settings, "trorbot_kb_bucket", "trorbot-kb")
    monkeypatch.setattr(kb, "_get_clients", no_creds)
    out = await kb.search_kb("context-events", "anything at all", 3)
    assert out["error"] == "AWS credentials not found for KB search"
    assert "TRORBOT_KB_AWS_PROFILE" in out["hint"]

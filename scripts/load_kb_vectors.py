"""Load the exported TRORBOT knowledge bases into Amazon S3 Vectors.

Input is the export of the original Bedrock knowledge bases: one JSONL file per KB
(context-events, program-documentation, annual-tror-reports), each line holding a
chunk's text, source URI, and its Titan Text Embeddings V2 vector (1,024 dims,
normalized). The vectors are reused as-is — the server embeds queries with the same
model, so no re-embedding is needed.

    uv run python scripts/load_kb_vectors.py <export-dir> --bucket trorbot-kb --profile personal

Creates the vector bucket and one index per KB if they don't exist, then upserts every
chunk (keyed by its original chunk id, so re-running is safe).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import boto3

from trorbot_mcp.kb import KB_INDEXES

DIMENSION = 1024
BATCH = 100

# Program Documentation was ingested twice; keep the September 2026 refresh and the
# TROR workbooks, drop the older duplicate copies.
_PROGRAM_DOC_KEEP = ("/documents/refreshed-faqs-sept-2026/", "/documents/tror-workbooks/")


def _title_from_uri(uri: str) -> str:
    name = uri.rsplit("/", 1)[-1]
    for suffix in (".html.md", ".md", ".txt"):
        name = name.removesuffix(suffix)
    return name.replace("-", " ").replace("_", " ")


def _annual_report_metadata(export_dir: Path) -> dict[str, dict]:
    """fiscal_year and title for each annual report, from the original S3 metadata files."""
    out = {}
    src = export_dir / "s3-originals" / "daab-lab-tror-bedrock-knowledgedb2"
    for meta_file in src.glob("*.metadata.json"):
        attrs = json.loads(meta_file.read_text())["metadataAttributes"]
        doc = meta_file.name.removesuffix(".metadata.json")
        out[f"s3://daab-lab-tror-bedrock-knowledgedb2/{doc}"] = {
            "fiscal_year": int(attrs["fiscal_year"]),
            "title": attrs["document_title"],
        }
    return out


def _vectors(kb: str, export_dir: Path, annual_meta: dict[str, dict]) -> list[dict]:
    vectors = []
    for line in (export_dir / f"{kb}.jsonl").read_text().splitlines():
        row = json.loads(line)
        uri = row["source_uri"]
        if kb == "program-documentation" and not any(k in uri for k in _PROGRAM_DOC_KEEP):
            continue
        metadata = {"text": row["text"], "source_uri": uri, "title": _title_from_uri(uri)}
        metadata.update(annual_meta.get(uri, {}))
        vectors.append({"key": row["chunk_id"], "data": {"float32": row["embedding"]}, "metadata": metadata})
    return vectors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("export_dir", type=Path)
    parser.add_argument("--bucket", default="trorbot-kb")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    s3v = boto3.Session(profile_name=args.profile, region_name=args.region).client("s3vectors")
    if args.bucket not in {b["vectorBucketName"] for b in s3v.list_vector_buckets()["vectorBuckets"]}:
        s3v.create_vector_bucket(vectorBucketName=args.bucket)
        print(f"created vector bucket {args.bucket}")

    existing = {i["indexName"] for i in s3v.list_indexes(vectorBucketName=args.bucket)["indexes"]}
    annual_meta = _annual_report_metadata(args.export_dir)
    for kb, index in KB_INDEXES.items():
        if index not in existing:
            s3v.create_index(
                vectorBucketName=args.bucket, indexName=index, dataType="float32",
                dimension=DIMENSION, distanceMetric="cosine",
                # Chunk text and full URI are returned with results but never filtered on.
                metadataConfiguration={"nonFilterableMetadataKeys": ["text", "source_uri"]},
            )
            print(f"created index {index}")
        vectors = _vectors(kb, args.export_dir, annual_meta)
        for i in range(0, len(vectors), BATCH):
            s3v.put_vectors(vectorBucketName=args.bucket, indexName=index, vectors=vectors[i:i + BATCH])
        print(f"{index}: loaded {len(vectors)} vectors")


if __name__ == "__main__":
    main()

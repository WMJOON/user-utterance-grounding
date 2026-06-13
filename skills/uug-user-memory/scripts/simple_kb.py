#!/usr/bin/env python3
# ── VENDORED (uug-user-memory) ──────────────────────────────────────
# 출처: simple-knowledge-zvec/scripts/simple_kb.py (zvec search 백엔드).
# wm_node 가 subprocess 로 호출. 상류 갱신 시 재동기화 필요.
"""Simple local knowledge-base CLI powered by zvec."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import zvec

DEFAULT_COLLECTION_PATH = "/tmp/simple-knowledge-zvec"
DEFAULT_COLLECTION_NAME = "simple_knowledge"
DEFAULT_VECTOR_FIELD = "dense_embedding"
DEFAULT_DIMENSION = 384
DEFAULT_CHUNK_SIZE = 700
DEFAULT_CHUNK_OVERLAP = 120
DEFAULT_BATCH_SIZE = 64
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".json", ".jsonl"}
TEXT_KEYS = ("text", "content", "body", "chunk", "message", "summary")
TITLE_KEYS = ("title", "name", "heading", "subject")


@dataclass
class RawRecord:
    source_path: str
    source_type: str
    text: str
    title: str | None
    tags: list[str]


@dataclass
class ChunkRecord:
    doc_id: str
    source_path: str
    source_type: str
    text: str
    title: str | None
    tags: list[str]
    chunk_index: int


def _init_runtime() -> None:
    zvec.init(log_level=zvec.LogLevel.WARN)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _quote_sql(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "''")
    return f"'{escaped}'"


def _shorten(value: str, max_chars: int) -> str:
    if max_chars <= 0 or len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _ensure_no_space_path(path: Path) -> None:
    if " " in str(path):
        raise ValueError(
            "zvec collection path contains spaces and may fail path validation. "
            "Use a no-space path (for example /tmp/simple-knowledge-zvec)."
        )


def _l2_normalize(values: Sequence[float]) -> list[float]:
    norm = sum(v * v for v in values) ** 0.5
    if norm == 0:
        return [0.0 for _ in values]
    return [float(v / norm) for v in values]


def _hash_embed(text: str, dimension: int) -> list[float]:
    if dimension <= 0:
        raise ValueError(f"Invalid vector dimension: {dimension}")
    normalized = _normalize_text(text).lower()
    tokens = re.findall(r"[a-z0-9_]+", normalized) or [normalized or "empty"]
    vector = [0.0] * dimension
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for i, byte_value in enumerate(digest):
            index = (byte_value + (i * 17)) % dimension
            sign = 1.0 if digest[(i + 11) % 32] % 2 == 0 else -1.0
            magnitude = 0.25 + (digest[(i + 3) % 32] / 255.0)
            vector[index] += sign * magnitude
    return _l2_normalize(vector)


def _safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _coerce_tags(raw_tags: Any) -> list[str]:
    if raw_tags is None:
        return []
    if isinstance(raw_tags, str):
        parts = [part.strip() for part in raw_tags.split(",")]
        return [part for part in parts if part]
    if isinstance(raw_tags, list):
        tags: list[str] = []
        for item in raw_tags:
            text = str(item).strip()
            if text:
                tags.append(text)
        return tags
    return []


def _pick_first_text(data: dict[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def _records_from_json_value(value: Any, source_path: str, source_type: str) -> list[RawRecord]:
    records: list[RawRecord] = []
    if isinstance(value, str):
        text = _normalize_text(value)
        if text:
            records.append(
                RawRecord(
                    source_path=source_path,
                    source_type=source_type,
                    text=text,
                    title=None,
                    tags=[],
                )
            )
        return records

    if isinstance(value, dict):
        text = _pick_first_text(value, TEXT_KEYS)
        title = _pick_first_text(value, TITLE_KEYS)
        tags = _coerce_tags(value.get("tags"))
        if text:
            records.append(
                RawRecord(
                    source_path=source_path,
                    source_type=source_type,
                    text=_normalize_text(text),
                    title=title,
                    tags=tags,
                )
            )
            return records

        for list_key in ("items", "documents", "records", "chunks", "data"):
            nested = value.get(list_key)
            if isinstance(nested, list):
                for nested_value in nested:
                    records.extend(_records_from_json_value(nested_value, source_path, source_type))
        return records

    if isinstance(value, list):
        for item in value:
            records.extend(_records_from_json_value(item, source_path, source_type))
    return records


def _load_records(path: Path) -> list[RawRecord]:
    suffix = path.suffix.lower()
    source_path = str(path.resolve())
    source_type = suffix.lstrip(".")
    if suffix in {".md", ".markdown", ".txt"}:
        text = _normalize_text(_safe_read_text(path))
        if not text:
            return []
        return [
            RawRecord(
                source_path=source_path,
                source_type=source_type,
                text=text,
                title=path.stem,
                tags=[],
            )
        ]

    if suffix == ".jsonl":
        records: list[RawRecord] = []
        for lineno, line in enumerate(_safe_read_text(path).splitlines(), 1):
            payload = line.strip()
            if not payload:
                continue
            try:
                value = json.loads(payload)
            except json.JSONDecodeError:
                print(
                    f"[WARN] skip invalid jsonl line: {path}:{lineno}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            records.extend(_records_from_json_value(value, source_path, source_type))
        return records

    if suffix == ".json":
        try:
            value = json.loads(_safe_read_text(path))
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON file: {path} ({exc})") from exc
        return _records_from_json_value(value, source_path, source_type)

    return []


def _chunk_text(text: str, chunk_size: int, overlap: int) -> Iterator[tuple[int, str]]:
    if chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("--chunk-overlap must be >= 0 and < chunk-size")
    cursor = 0
    chunk_index = 0
    while cursor < len(text):
        end = min(cursor + chunk_size, len(text))
        chunk = text[cursor:end].strip()
        if chunk:
            yield chunk_index, chunk
            chunk_index += 1
        if end >= len(text):
            break
        cursor = end - overlap


def _batched(items: Sequence[ChunkRecord], batch_size: int) -> Iterator[list[ChunkRecord]]:
    for start in range(0, len(items), batch_size):
        yield list(items[start : start + batch_size])


def _collect_files(raw_inputs: Sequence[str], recursive: bool) -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for raw in raw_inputs:
        candidate = Path(raw).expanduser()
        if not candidate.exists():
            print(f"[WARN] input path does not exist: {candidate}", file=sys.stderr, flush=True)
            continue
        discovered: Iterable[Path]
        if candidate.is_file():
            discovered = [candidate]
        elif recursive:
            discovered = [path for path in candidate.rglob("*") if path.is_file()]
        else:
            discovered = [path for path in candidate.glob("*") if path.is_file()]
        for path in discovered:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(path)
    files.sort(key=lambda p: str(p))
    return files


def _collection_option(read_only: bool, disable_mmap: bool) -> Any:
    return zvec.CollectionOption(read_only=read_only, enable_mmap=not disable_mmap)


def _open_collection(path: Path, *, read_only: bool, disable_mmap: bool) -> Any:
    _ensure_no_space_path(path)
    if not path.exists():
        raise FileNotFoundError(f"collection path does not exist: {path}")
    option = _collection_option(read_only=read_only, disable_mmap=disable_mmap)
    return zvec.open(path=str(path), option=option)


def _metric_type(metric: str) -> Any:
    mapping = {
        "cosine": zvec.MetricType.COSINE,
        "l2": zvec.MetricType.L2,
        "ip": zvec.MetricType.IP,
    }
    return mapping[metric]


def _create_schema(name: str, vector_field: str, dimension: int, metric: str) -> Any:
    vector = zvec.VectorSchema(
        vector_field,
        zvec.DataType.VECTOR_FP32,
        dimension,
        zvec.HnswIndexParam(metric_type=_metric_type(metric)),
    )
    fields = [
        zvec.FieldSchema("title", zvec.DataType.STRING, nullable=True),
        zvec.FieldSchema("text", zvec.DataType.STRING),
        zvec.FieldSchema("source_path", zvec.DataType.STRING, nullable=True),
        zvec.FieldSchema("source_type", zvec.DataType.STRING, nullable=True),
        zvec.FieldSchema("chunk_index", zvec.DataType.INT32, nullable=True),
        zvec.FieldSchema("tags", zvec.DataType.ARRAY_STRING, nullable=True),
        zvec.FieldSchema("created_at", zvec.DataType.STRING, nullable=True),
    ]
    return zvec.CollectionSchema(name=name, fields=fields, vectors=[vector])


def _pick_vector(collection: Any, requested: str | None) -> tuple[str, int]:
    schema = collection.schema
    vector_schemas = list(schema.vectors or [])
    if not vector_schemas:
        raise ValueError("collection schema has no vector field")
    if requested:
        for vector_schema in vector_schemas:
            if vector_schema.name == requested:
                return vector_schema.name, int(vector_schema.dimension)
        raise ValueError(f"vector field not found in schema: {requested}")
    first = vector_schemas[0]
    return first.name, int(first.dimension)


def _resolve_extension_class(module: Any, candidates: Sequence[str]) -> Any | None:
    embedded_mod = getattr(module, "embedding", None)
    for class_name in candidates:
        cls = getattr(module, class_name, None)
        if cls is None and embedded_mod is not None:
            cls = getattr(embedded_mod, class_name, None)
        if cls is not None:
            return cls
    return None


def _prepare_embedder(kind: str, dimension: int) -> tuple[Any | None, str]:
    if kind == "hash":
        return None, "hash"

    import zvec.extension as zext  # type: ignore

    if kind == "local":
        cls = _resolve_extension_class(zext, ["DefaultLocalDenseEmbedding"])
        if cls is None:
            raise RuntimeError("DefaultLocalDenseEmbedding not available in zvec.extension")
        return cls(), cls.__name__

    if kind == "openai":
        cls = _resolve_extension_class(zext, ["OpenAIDenseEmbedding"])
        if cls is None:
            raise RuntimeError("OpenAIDenseEmbedding not available in zvec.extension")
        try:
            return cls(dimension=dimension), cls.__name__
        except TypeError:
            return cls(), cls.__name__

    if kind == "qwen":
        cls = _resolve_extension_class(zext, ["QwenDenseEmbedding", "QwenEmbeddingFunction"])
        if cls is None:
            raise RuntimeError("QwenDenseEmbedding not available in zvec.extension")
        try:
            return cls(dimension), cls.__name__
        except TypeError:
            return cls(dimension=dimension), cls.__name__

    raise ValueError(f"unsupported embedder: {kind}")


def _parse_query_vector(raw: str, dimension: int) -> list[float]:
    values = [value for value in raw.replace(",", " ").split() if value]
    if not values:
        raise ValueError("--query-vector is empty")
    vector = [float(value) for value in values]
    if len(vector) != dimension:
        raise ValueError(f"query vector dimension mismatch: expected {dimension}, got {len(vector)}")
    return vector


def _coerce_vector(raw_vector: Any, dimension: int) -> list[float]:
    if hasattr(raw_vector, "tolist"):
        raw_vector = raw_vector.tolist()
    if isinstance(raw_vector, list) and raw_vector and isinstance(raw_vector[0], (list, tuple)):
        if len(raw_vector) != 1:
            raise ValueError("embedder returned nested vectors; expected a single vector")
        raw_vector = raw_vector[0]
    if not isinstance(raw_vector, (list, tuple)):
        raise ValueError(f"embedder output type is not a vector: {type(raw_vector).__name__}")
    vector = [float(value) for value in raw_vector]
    if len(vector) != dimension:
        raise ValueError(f"embedding dimension mismatch: expected {dimension}, got {len(vector)}")
    return vector


def _embed_text(text: str, *, kind: str, embedder: Any | None, dimension: int) -> list[float]:
    if kind == "hash":
        return _hash_embed(text, dimension)
    if embedder is None:
        raise RuntimeError("embedder is not initialized")
    return _coerce_vector(embedder.embed(text), dimension)


def _result_code(entry: Any) -> int:
    if hasattr(entry, "code"):
        code = entry.code
        if callable(code):
            code = code()
        return int(code)
    if isinstance(entry, dict):
        return int(entry.get("code", -1))
    return -1


def _count_failures(results: Any) -> int:
    if results is None:
        return 0
    if isinstance(results, (list, tuple)):
        return sum(1 for item in results if _result_code(item) != 0)
    return 0 if _result_code(results) == 0 else 1


def _build_filter(args: argparse.Namespace) -> str | None:
    clauses: list[str] = []
    for source_like in args.source_like or []:
        pattern = source_like if "%" in source_like else f"%{source_like}%"
        clauses.append(f"source_path LIKE {_quote_sql(pattern)}")
    if args.tag:
        quoted = ", ".join(_quote_sql(tag) for tag in args.tag)
        clauses.append(f"tags CONTAIN_ANY ({quoted})")
    if args.where:
        clauses.append(f"({args.where})")
    if not clauses:
        return None
    return " AND ".join(clauses)


def _field_value(doc: Any, key: str) -> Any:
    if hasattr(doc, "has_field") and doc.has_field(key):
        return doc.field(key)
    fields = getattr(doc, "fields", None) or {}
    return fields.get(key)


def _schema_summary(collection: Any, vector_name: str | None = None) -> str:
    schema = collection.schema
    fields = ", ".join(field.name for field in schema.fields)
    vectors: list[str] = []
    for vector in schema.vectors:
        name = vector.name
        if vector_name and name != vector_name:
            continue
        vectors.append(f"{name}:{vector.dimension}")
    vector_text = ", ".join(vectors) if vectors else "(none)"
    return (
        f"name={schema.name}\n"
        f"fields={fields}\n"
        f"vectors={vector_text}\n"
        f"doc_count={collection.stats.doc_count}\n"
        f"index_completeness={dict(collection.stats.index_completeness)}"
    )


def cmd_init(args: argparse.Namespace) -> int:
    _init_runtime()
    path = Path(args.path).expanduser()
    _ensure_no_space_path(path)
    if args.dimension <= 0:
        raise ValueError("--dimension must be > 0")

    if path.exists():
        collection = _open_collection(path, read_only=True, disable_mmap=args.disable_mmap)
        print(f"[init] collection already exists: {path}", flush=True)
        print(_schema_summary(collection), flush=True)
        return 0

    path.parent.mkdir(parents=True, exist_ok=True)
    schema = _create_schema(
        name=args.name,
        vector_field=args.vector_field,
        dimension=args.dimension,
        metric=args.metric,
    )
    option = _collection_option(read_only=False, disable_mmap=args.disable_mmap)
    collection = zvec.create_and_open(path=str(path), schema=schema, option=option)
    collection.flush()
    print(f"[init] created collection: {path}", flush=True)
    print(_schema_summary(collection), flush=True)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    _init_runtime()
    path = Path(args.path).expanduser()
    collection = _open_collection(path, read_only=False, disable_mmap=args.disable_mmap)
    vector_field, dimension = _pick_vector(collection, args.vector_field)
    embedder, embedder_name = _prepare_embedder(args.embedder, dimension)

    files = _collect_files(args.input, recursive=args.recursive)
    if not files:
        print("[add] no supported input files found (.md/.markdown/.txt/.json/.jsonl)", flush=True)
        return 2

    records: list[RawRecord] = []
    for file_path in files:
        records.extend(_load_records(file_path))

    if not records:
        print("[add] input files were readable, but no text records were extracted", flush=True)
        return 2

    shared_tags = [tag.strip() for tag in args.tag if tag and tag.strip()]
    chunks: list[ChunkRecord] = []
    for record in records:
        for chunk_index, chunk_text in _chunk_text(
            record.text, chunk_size=args.chunk_size, overlap=args.chunk_overlap
        ):
            digest = hashlib.sha1(
                f"{record.source_path}:{chunk_index}:{chunk_text}".encode("utf-8")
            ).hexdigest()[:20]
            doc_id = f"{args.id_prefix}-{digest}" if args.id_prefix else digest
            merged_tags = sorted({*record.tags, *shared_tags})
            chunks.append(
                ChunkRecord(
                    doc_id=doc_id,
                    source_path=record.source_path,
                    source_type=record.source_type,
                    text=chunk_text,
                    title=record.title,
                    tags=merged_tags,
                    chunk_index=chunk_index,
                )
            )

    if not chunks:
        print("[add] no chunks generated from extracted records", flush=True)
        return 2

    failures = 0
    inserted = 0
    for batch in _batched(chunks, max(args.batch_size, 1)):
        docs: list[Any] = []
        for chunk in batch:
            vector = _embed_text(
                chunk.text,
                kind=args.embedder,
                embedder=embedder,
                dimension=dimension,
            )
            fields: dict[str, Any] = {
                "text": chunk.text,
                "source_path": chunk.source_path,
                "source_type": chunk.source_type,
                "chunk_index": chunk.chunk_index,
                "created_at": _utc_now_iso(),
            }
            if chunk.title:
                fields["title"] = chunk.title
            if chunk.tags:
                fields["tags"] = chunk.tags
            docs.append(
                zvec.Doc(
                    id=chunk.doc_id,
                    fields=fields,
                    vectors={vector_field: vector},
                )
            )
        result = collection.insert(docs) if args.insert_only else collection.upsert(docs)
        failures += _count_failures(result)
        inserted += len(docs)

    if not args.skip_optimize:
        collection.optimize()
    collection.flush()
    print(f"[add] collection={path}", flush=True)
    print(f"[add] files={len(files)} records={len(records)} chunks={len(chunks)}", flush=True)
    print(f"[add] mode={'insert' if args.insert_only else 'upsert'} failures={failures}", flush=True)
    print(f"[add] optimized={not args.skip_optimize}", flush=True)
    print(f"[add] vector_field={vector_field} dimension={dimension} embedder={embedder_name}", flush=True)
    if failures > 0:
        print("[add] completed with failures", file=sys.stderr, flush=True)
        return 1
    if inserted == 0:
        return 2
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    _init_runtime()
    path = Path(args.path).expanduser()
    collection = _open_collection(path, read_only=True, disable_mmap=args.disable_mmap)
    vector_field, dimension = _pick_vector(collection, args.vector_field)

    if args.query_vector:
        query_vector = _parse_query_vector(args.query_vector, dimension)
        embedder_name = "manual-vector"
    else:
        if not args.query:
            raise ValueError("query text is required unless --query-vector is set")
        query_text = " ".join(args.query).strip()
        embedder, embedder_name = _prepare_embedder(args.embedder, dimension)
        query_vector = _embed_text(
            query_text,
            kind=args.embedder,
            embedder=embedder,
            dimension=dimension,
        )

    filter_expr = _build_filter(args)
    results = collection.query(
        vectors=zvec.VectorQuery(vector_field, vector=query_vector),
        topk=args.limit,
        filter=filter_expr,
        output_fields=None,
        include_vector=False,
    )

    print(f"[search] collection={path}", flush=True)
    print(f"[search] vector_field={vector_field} dimension={dimension}", flush=True)
    print(f"[search] embedder={embedder_name}", flush=True)
    if filter_expr:
        print(f"[search] filter={filter_expr}", flush=True)

    if not results:
        print("[search] no results", flush=True)
        return 0

    for idx, doc in enumerate(results, 1):
        score = getattr(doc, "score", None)
        score_text = f"{score:.6f}" if isinstance(score, (int, float)) else str(score)
        source_path = _field_value(doc, "source_path")
        title = _field_value(doc, "title")
        tags = _field_value(doc, "tags")
        text = _field_value(doc, args.text_field)
        print(f"[{idx}] id={getattr(doc, 'id', '<unknown>')} score={score_text}", flush=True)
        if title:
            print(f"    title: {title}", flush=True)
        if source_path:
            print(f"    source: {source_path}", flush=True)
        if tags:
            print(f"    tags: {tags}", flush=True)
        if isinstance(text, str) and text.strip():
            print(f"    text: {_shorten(text.strip(), args.snippet_chars)}", flush=True)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    _init_runtime()
    path = Path(args.path).expanduser()
    collection = _open_collection(path, read_only=True, disable_mmap=args.disable_mmap)
    print(f"[stats] collection={path}", flush=True)
    print(_schema_summary(collection, args.vector_field), flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simple_kb.py",
        description="Create and query a simple local knowledge base on zvec.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_init = subparsers.add_parser("init", help="Create or open zvec collection.")
    p_init.add_argument("--path", default=DEFAULT_COLLECTION_PATH, help="Collection path.")
    p_init.add_argument("--name", default=DEFAULT_COLLECTION_NAME, help="Collection schema name.")
    p_init.add_argument("--vector-field", default=DEFAULT_VECTOR_FIELD, help="Vector field name.")
    p_init.add_argument("--dimension", type=int, default=DEFAULT_DIMENSION, help="Embedding dimension.")
    p_init.add_argument(
        "--metric",
        choices=["cosine", "l2", "ip"],
        default="cosine",
        help="Vector metric type.",
    )
    p_init.add_argument(
        "--disable-mmap",
        action="store_true",
        help="Disable mmap when opening/creating collection.",
    )
    p_init.set_defaults(func=cmd_init)

    p_add = subparsers.add_parser("add", help="Ingest files and upsert chunks.")
    p_add.add_argument("--path", default=DEFAULT_COLLECTION_PATH, help="Collection path.")
    p_add.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input file or directory. Repeatable.",
    )
    p_add.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan directory inputs.",
    )
    p_add.add_argument("--vector-field", help="Target vector field. Defaults to first vector schema.")
    p_add.add_argument(
        "--embedder",
        choices=["hash", "local", "openai", "qwen"],
        default="hash",
        help="Embedding backend. hash is offline-safe baseline.",
    )
    p_add.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help="Chunk size in characters.",
    )
    p_add.add_argument(
        "--chunk-overlap",
        type=int,
        default=DEFAULT_CHUNK_OVERLAP,
        help="Chunk overlap in characters.",
    )
    p_add.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Write batch size.",
    )
    p_add.add_argument(
        "--id-prefix",
        default="kb",
        help="Document ID prefix. Empty string disables prefix.",
    )
    p_add.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Additional tag attached to every chunk. Repeatable.",
    )
    p_add.add_argument(
        "--insert-only",
        action="store_true",
        help="Use insert (fail on duplicate IDs) instead of upsert.",
    )
    p_add.add_argument(
        "--skip-optimize",
        action="store_true",
        help="Skip post-ingest optimize (search may miss unindexed docs).",
    )
    p_add.add_argument(
        "--disable-mmap",
        action="store_true",
        help="Disable mmap when opening collection.",
    )
    p_add.set_defaults(func=cmd_add)

    p_search = subparsers.add_parser("search", help="Vector search on indexed chunks.")
    p_search.add_argument("query", nargs="*", help="Search query text.")
    p_search.add_argument("--path", default=DEFAULT_COLLECTION_PATH, help="Collection path.")
    p_search.add_argument("--vector-field", help="Target vector field. Defaults to first vector schema.")
    p_search.add_argument(
        "--embedder",
        choices=["hash", "local", "openai", "qwen"],
        default="hash",
        help="Embedder used to encode query text.",
    )
    p_search.add_argument(
        "--query-vector",
        help="Raw vector values (comma/space separated). Overrides query text embedding.",
    )
    p_search.add_argument("--limit", type=int, default=5, help="Top-K results.")
    p_search.add_argument(
        "--source-like",
        action="append",
        default=[],
        help="source_path LIKE filter value. Repeatable.",
    )
    p_search.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Tag filter. Repeatable (CONTAIN_ANY).",
    )
    p_search.add_argument("--where", help="Raw filter expression appended with AND.")
    p_search.add_argument(
        "--text-field",
        default="text",
        help="Field used for snippet rendering.",
    )
    p_search.add_argument(
        "--snippet-chars",
        type=int,
        default=220,
        help="Max snippet length per result.",
    )
    p_search.add_argument(
        "--disable-mmap",
        action="store_true",
        help="Disable mmap when opening collection.",
    )
    p_search.set_defaults(func=cmd_search)

    p_stats = subparsers.add_parser("stats", help="Show collection schema and counters.")
    p_stats.add_argument("--path", default=DEFAULT_COLLECTION_PATH, help="Collection path.")
    p_stats.add_argument("--vector-field", help="Optional vector field filter in output.")
    p_stats.add_argument(
        "--disable-mmap",
        action="store_true",
        help="Disable mmap when opening collection.",
    )
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr, flush=True)
        return 130
    except Exception as exc:  # pylint: disable=broad-except
        print(f"Error: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    sys.exit(main())

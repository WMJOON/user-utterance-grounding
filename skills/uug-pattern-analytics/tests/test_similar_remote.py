"""Remote bge-m3 outage must not load weights or damage the existing index."""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import similar  # noqa: E402


def test_machine_local_url_and_environment_override(tmp_path, monkeypatch):
    config = tmp_path / "embedding-url"
    config.write_text("https://macbook.example.ts.net/v1/embeddings\n")
    monkeypatch.setattr(similar, "EMBED_URL_FILE", config)
    monkeypatch.delenv("UUG_EMBED_URL", raising=False)
    assert similar._embedding_url() == "https://macbook.example.ts.net/v1/embeddings"
    monkeypatch.setenv("UUG_EMBED_URL", "http://127.0.0.1:9999/v1/embeddings")
    assert similar._embedding_url() == "http://127.0.0.1:9999/v1/embeddings"
    monkeypatch.delenv("UUG_EMBED_URL")
    config.write_text("\n")
    with pytest.raises(similar.EmbeddingUnavailable):
        similar._embedding_url()


def test_query_returns_no_ranking_without_local_model(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "zvec", types.ModuleType("zvec"))
    monkeypatch.setattr(similar, "INDEX", tmp_path)

    def unavailable(*args, **kwargs):
        raise similar.EmbeddingUnavailable("endpoint down")

    monkeypatch.setattr(similar, "embed", unavailable)
    assert similar.query("테스트") == {"status": "embedding-unavailable", "ranking": []}


def test_rebuild_keeps_index_when_remote_embedding_fails(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "zvec", types.ModuleType("zvec"))
    index = tmp_path / "index"
    index.mkdir()
    sentinel = index / "existing-data"
    sentinel.write_text("keep")
    seen = tmp_path / "seen.json"
    seen.write_text('["old-id"]')
    tags = tmp_path / "tags.jsonl"
    tags.write_text(json.dumps({"target": "uug", "ref": {"file": "file", "id": "ref", "source": "codex"}}) + "\n")
    monkeypatch.setattr(similar, "INDEX", index)
    monkeypatch.setattr(similar, "SEEN", seen)
    monkeypatch.setattr(similar.tag_targets, "OUT", tags)
    monkeypatch.setattr(similar.tag_targets, "iter_turns", lambda: iter([{"file": "file", "ref": "ref", "text": "샘플"}]))

    def unavailable(*args, **kwargs):
        raise similar.EmbeddingUnavailable("endpoint down")

    monkeypatch.setattr(similar, "embed", unavailable)
    with pytest.raises(similar.EmbeddingUnavailable):
        similar.cmd_index(types.SimpleNamespace(rebuild=True))
    assert sentinel.read_text() == "keep"
    assert seen.read_text() == '["old-id"]'

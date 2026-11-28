"""어휘 유형 이름(v0.6.1): RepositoryLexical/TaskLexical 선언이 기존 어휘 로딩과 SHACL 을 건드리지 않는다."""
from pathlib import Path

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import SKOS

UUG = Namespace("https://uug.dev/ontology/")
TAX = Path(__file__).resolve().parent.parent / "taxonomy"


def _g():
    g = Graph()
    g.parse(TAX / "lexical_types.ttl", format="turtle")
    return g


def test_two_lexical_types_declared_with_legacy_names():
    g = _g()
    for iri, old in ((UUG.RepositoryLexical, "ProjectName"), (UUG.TaskLexical, "WorkTerm")):
        assert (iri, RDF.type, SKOS.Concept) in g
        assert any(str(o) == old for o in g.objects(iri, SKOS.altLabel))


def test_not_in_any_work_term_scheme():
    """skos:inScheme 를 쓰면 vocab_shapes 가 facet 4개를 요구한다 — topConceptOf 만 써야 한다."""
    g = _g()
    assert not list(g.subjects(SKOS.inScheme, None))


def test_work_term_vocabulary_is_unchanged():
    from src import vocab  # noqa: PLC0415
    assert len(vocab.list_concepts("WorkTermScheme")) > 0
    labels = vocab.work_term_labels() if hasattr(vocab, "work_term_labels") else set()
    assert "repository lexical" not in {l.lower() for l in labels}

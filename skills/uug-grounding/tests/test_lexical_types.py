"""어휘 유형 이름(v0.6.2): RepositoryLexical/TaskLexical 선언이 기존 어휘 로딩과 SHACL 을 건드리지 않는다."""
import sys
from pathlib import Path

from rdflib import Graph, Namespace, RDF
from rdflib.namespace import SKOS

UUG = Namespace("https://uug.dev/ontology/")
SKILL = Path(__file__).resolve().parent.parent
TAX = SKILL / "taxonomy"
sys.path.insert(0, str(SKILL / "src"))


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
    import vocab  # noqa: PLC0415
    concepts = vocab.list_concepts("WorkTermScheme")
    assert len(concepts) > 0
    all_labels = {l.lower() for c in concepts for l in c["labels"]}
    assert "repository lexical" not in all_labels and "task lexical" not in all_labels

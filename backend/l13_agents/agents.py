"""L13 multi-agent retrieval — vector + graph + SQL agents (image gated).

Thin but real: vector = dense Qdrant; graph = Kuzu entity→doc resolution with
chunk fetch; SQL = documents-meta matches. Fused by RRF in the graph.
Image agent activates with a VL model (Phase 3-full hardware).
"""
import re

from backend.l07_storage import qdrant as store
from backend.l15_security.acl import groups_filter

_WORD = re.compile(r"[a-zA-Z]{4,}")


def vector_agent(query: str, groups: list[str], n: int) -> list[dict]:
    return store.search(query, n, groups_filter(groups))


def graph_agent(query: str, groups: list[str], n: int) -> list[dict]:
    """Kuzu: entities mentioned in query → docs containing them → top chunks."""
    try:
        import kuzu

        db = kuzu.Database("data/kuzu/kuzu.db")
        con = kuzu.Connection(db)
    except Exception:
        return []
    keywords = {w.lower() for w in _WORD.findall(query)}
    docs: list[str] = []
    try:
        rows = con.execute("MATCH (e:Ent)-[:IN]->(d:Doc) RETURN e.name, d.name LIMIT 500")
        while rows.has_next():
            ename, dname = rows.get_next()
            if any(k in str(ename).lower() for k in keywords) and dname not in docs:
                docs.append(str(dname))
    except Exception:
        return []
    hits: list[dict] = []
    per = max(1, n // max(1, len(docs)))
    for d in docs[:5]:
        hits.extend(store.fetch_by_doc(d, groups, per))
    return hits[:n]


def sql_agent(query: str, groups: list[str], n: int) -> list[dict]:
    """documents-meta: filenames mentioned in the query become doc hits."""
    from backend.l08_freshness.store import jload, meta_conn

    con = meta_conn("data/meta.db")
    try:
        rows = con.execute("SELECT filename, allowed_groups_json FROM documents").fetchall()
    finally:
        con.close()
    ql = query.lower()
    hits = []
    for filename, agroups in rows:
        stem = filename.rsplit(".", 1)[0].lower()
        if stem and stem in ql and set(groups) & set(jload(agroups)):
            for c in store.fetch_by_doc(filename.rsplit(".", 1)[0], groups, 2):
                hits.append(c)
    return hits[:n]


def image_agent(query: str, groups: list[str], n: int) -> list[dict]:
    return []  # gated: needs Qwen2-VL-2B (Phase 3-full hardware)

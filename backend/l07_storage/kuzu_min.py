"""L7: Kuzu Doc/Ent graph — Doc nodes, Ent nodes, Ent-[:IN]->Doc edges."""

import kuzu


def _db(path: str = "data/kuzu/kuzu.db"):
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    return kuzu.Database(path)


def record(doc: str, n_chunks: int, path: str = "data/kuzu/kuzu.db") -> None:
    _db(path).execute("MERGE (d:Doc {name: $n}) SET d.chunks=$c", {"n": doc, "c": n_chunks})


def record_ent(doc: str, ent: str, label: str, path: str = "data/kuzu/kuzu.db") -> None:
    db = _db(path)
    db.execute("MERGE (d:Doc {name: $doc})", {"doc": doc})
    db.execute("MERGE (e:Ent {name: $ent, label: $label})", {"ent": ent[:80], "label": label})
    db.execute(
        "MATCH (e:Ent {name: $ent}), (d:Doc {name: $doc}) "
        "MERGE (e)-[:IN]->(d)", {"ent": ent[:80], "doc": doc})

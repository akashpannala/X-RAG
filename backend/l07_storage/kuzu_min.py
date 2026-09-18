"""L7: Kuzu Doc/Ent graph — Doc nodes, Ent nodes, Ent-[:IN]->Doc edges."""

import kuzu


_db_singleton = None
_conn_singleton = None


def _get_conn(path: str = "data/kuzu/kuzu.db"):
    global _db_singleton, _conn_singleton
    if _conn_singleton is None:
        import pathlib

        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        _db_singleton = kuzu.Database(path)
        _conn_singleton = kuzu.Connection(_db_singleton)
        _ensure_schema(_conn_singleton)
    return _conn_singleton


def _ensure_schema(conn) -> None:
    for ddl in (
        "CREATE NODE TABLE IF NOT EXISTS Doc(name STRING PRIMARY KEY, chunks INT64)",
        "CREATE NODE TABLE IF NOT EXISTS Ent(name STRING PRIMARY KEY, label STRING)",
        "CREATE REL TABLE IF NOT EXISTS `IN`(FROM Ent TO Doc)",
    ):
        try:
            conn.execute(ddl)
        except Exception:
            pass


def record(doc: str, n_chunks: int, path: str = "data/kuzu/kuzu.db") -> None:
    _get_conn(path).execute("MERGE (d:Doc {name: $n}) SET d.chunks=$c", {"n": doc, "c": n_chunks})


def record_ent(doc: str, ent: str, label: str, path: str = "data/kuzu/kuzu.db") -> None:
    conn = _get_conn(path)
    conn.execute("MERGE (d:Doc {name: $doc})", {"doc": doc})
    conn.execute("MERGE (e:Ent {name: $ent, label: $label})", {"ent": ent[:80], "label": label})
    conn.execute(
        "MATCH (e:Ent {name: $ent}) MATCH (d:Doc {name: $doc}) "
        "MERGE (e)-[:`IN`]->(d)", {"ent": ent[:80], "doc": doc})

"""L7-min: Kuzu Doc->Chunk bookkeeping only. Full graph = Phase 3."""
import kuzu


def record(doc: str, n_chunks: int, path: str = "data/kuzu/kuzu.db") -> None:
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    kuzu.Database(path).execute(
        "MERGE (d:Doc {name: $n}) SET d.chunks=$c", {"n": doc, "c": n_chunks})

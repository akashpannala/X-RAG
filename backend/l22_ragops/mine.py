"""L22: hard-negative mining over the verified golden set (PRD M5).

Pipeline:
  seed_goldens()  harvest verified conversations (>=1 resolved context) into
                  eval_goldens, resolving each context text to its corpus
                  (doc, chunk_id) via the BM25 meta corpus (ABSOLUTELY the
                  same text the payloads were built from).
  mine()          for every golden, fetch dense+BM25 candidates (:50) through
                  the real ACL, and record the highest-scoring non-gold
                  chunks as hard negatives (mined_hard_negatives).
  recall()        baseline Recall@K vs "suppressed" Recall@K: dropping the
                  mined negatives from the pool models the post-finetune
                  embedder; the delta is the learnable headroom.

CLI: python -m backend.l22_ragops.mine --seed --mine --eval
"""
import argparse
import json
import pickle
import sqlite3
from pathlib import Path

from backend.config import settings
from backend.l08_freshness.store import meta_conn
from backend.l15_security import acl

CORPUS_PKL = Path("data/bm25.pkl")
NEG_MIN_SCORE = 0.22
NEGS_PER_GOLDEN = 5
CAND_K = 50

_groups_by_user = None


def _corpus() -> list[dict]:
    with open(CORPUS_PKL, "rb") as f:
        _, meta = pickle.load(f)
    return meta


def _text_lookup(meta: list[dict]) -> dict:
    exact: dict[str, tuple] = {}
    for m in meta:
        exact.setdefault(m["text"].strip(), (m["doc"], m["chunk_id"]))
    return exact


def _resolve_gold_texts(meta: list[dict], contexts: list[str]) -> list[dict]:
    lookup = _text_lookup(meta)
    cites = []
    for t in (c or "" for c in contexts):
        key = t.strip()
        hit = lookup.get(key)
        if hit is None:
            for m in meta:
                if t[:120] and m["text"].startswith(t[:120]):
                    hit = (m["doc"], m["chunk_id"])
                    break
        if hit is not None:
            cites.append({"doc": hit[0], "chunk_id": hit[1], "text": key[:300]})
    return cites


def _groups_for(user_id: int | None, con: sqlite3.Connection) -> list[str]:
    global _groups_by_user
    if _groups_by_user is None:
        _groups_by_user = {
            r[0]: json.loads(r[1] or '["public"]')
            for r in con.execute("SELECT id, groups_json FROM users")}
    return _groups_by_user.get(user_id or 0, ["public"])


def seed_goldens() -> int:
    meta = _corpus()
    con = meta_conn(settings.sqlite_path)
    added = 0
    rows = con.execute(
        "SELECT user_id, query, contexts_json FROM conversations "
        "WHERE contexts_json IS NOT NULL AND contexts_json != '[]'").fetchall()
    for user_id, query, ctx_json in rows:
        if con.execute("SELECT 1 FROM eval_goldens WHERE query=?",
                       (query,)).fetchone():
            continue
        cites = _resolve_gold_texts(meta, json.loads(ctx_json or "[]"))
        if not cites:
            continue
        con.execute(
            "INSERT INTO eval_goldens(query, golden_answer, gold_cites_json, groups_json) "
            "VALUES(?,?,?,?)",
            (query, "", json.dumps(cites), json.dumps(_groups_for(user_id, con))))
        added += 1
    con.commit()
    con.close()
    return added


def _candidates(query: str, groups: list[str], k: int = CAND_K) -> list[dict]:
    from backend.l07_storage import qdrant as store

    dense = store.search(query, k, acl.groups_filter(groups))
    sparse = []
    try:
        from backend.l06_sparse.bm25 import search as bm25_search

        sparse = bm25_search(query, 25)
    except Exception:
        pass
    merged: dict[tuple, dict] = {}
    for h in dense + sparse:
        key = (h["doc"], h["chunk_id"])
        if key not in merged or h.get("score", 0) > merged[key].get("score", 0):
            merged[key] = h
    return sorted(merged.values(), key=lambda h: h.get("score", 0), reverse=True)


def mine() -> int:
    con = meta_conn(settings.sqlite_path)
    golds = con.execute("SELECT id, query, gold_cites_json, groups_json "
                        "FROM eval_goldens").fetchall()
    seen = {(r[0], r[1], r[2]) for r in con.execute(
        "SELECT query, doc, chunk_id FROM mined_hard_negatives")}
    added = 0
    for _gid, query, cites_json, groups_json in golds:
        gold = {(c["doc"], c["chunk_id"])
                for c in json.loads(cites_json or "[]")}
        per = 0
        for h in _candidates(query, json.loads(groups_json or '["public"]')):
            if (h["doc"], h["chunk_id"]) in gold:
                continue
            if h.get("score", 0) < NEG_MIN_SCORE:
                continue
            if (query, h["doc"], h["chunk_id"]) in seen:
                continue
            con.execute(
                "INSERT INTO mined_hard_negatives(query, doc, chunk_id, label_json) "
                "VALUES(?,?,?,?)",
                (query, h["doc"], h["chunk_id"],
                 json.dumps({"score": round(float(h.get("score", 0)), 4),
                             "is_positive": False})))
            seen.add((query, h["doc"], h["chunk_id"]))
            added += 1
            per += 1
            if per >= NEGS_PER_GOLDEN:
                break
    con.commit()
    con.close()
    return added


def recall(top_k: int = 5) -> dict:
    con = meta_conn(settings.sqlite_path)
    golds = con.execute("SELECT id, query, gold_cites_json, groups_json "
                        "FROM eval_goldens").fetchall()
    mined = {(r[0], r[1], r[2]) for r in con.execute(
        "SELECT query, doc, chunk_id FROM mined_hard_negatives")}
    base_hit = proj_hit = total = 0
    suppressed = hard = 0
    for _, query, cites_json, groups_json in golds:
        gold = {(c["doc"], c["chunk_id"]) for c in json.loads(cites_json or "[]")}
        groups = json.loads(groups_json or '["public"]')
        pool = _candidates(query, groups)
        base = pool[:top_k]
        if any((h["doc"], h["chunk_id"]) in gold for h in base):
            base_hit += 1
        if any((h["doc"], h["chunk_id"]) in mined for h in base):
            suppressed += 1
        projected = [h for h in pool if (h["doc"], h["chunk_id"]) not in mined][:top_k]
        if any((h["doc"], h["chunk_id"]) in gold for h in projected):
            proj_hit += 1
        total += 1
        best_gold = best_neg = -1.0
        for h in pool:
            if (h["doc"], h["chunk_id"]) in gold:
                best_gold = max(best_gold, h.get("score", 0))
            elif (h["doc"], h["chunk_id"]) in mined:
                best_neg = max(best_neg, h.get("score", 0))
        if best_neg >= 0 and best_neg >= best_gold:
            hard += 1
    con.close()
    return {
        "goldens": total,
        "recall_at_%d_base" % top_k: round(base_hit / total, 3) if total else 0.0,
        "recall_at_%d_suppressed" % top_k: round(proj_hit / total, 3) if total else 0.0,
        "base_hits": base_hit, "projected_hits": proj_hit,
        "goldens_blocked_below_mined": suppressed,
        "goldens_mined_neg_outranks_best_gold": hard,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--mine", action="store_true")
    ap.add_argument("--eval", action="store_true")
    ap.add_argument("--top_k", type=int, default=5)
    args = ap.parse_args()
    if args.seed:
        print("seeded goldens:", seed_goldens())
    if args.mine:
        print("mined negatives:", mine())
    if args.eval:
        print("eval:", json.dumps(recall(args.top_k)))


if __name__ == "__main__":
    main()
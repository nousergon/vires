"""Hybrid exercise search + embedding dedup.

Fuses two retrievers over the catalog:
* **BM25** (SQLite FTS5) — wins known-item / abbreviation lookups ("RDL", "GHR").
* **Vector cosine** (FastEmbed bge-small) — wins description-without-name queries
  ("the hamstring curl where your feet are held down").

Results are combined with Reciprocal Rank Fusion (each covers the other's blind
spot). A *separate* name-only embedding index backs the add-exercise "similar
exercise" hint (``find_similar_hint``) — kept apart from the name+keywords
search index above, because that diluted signal clustered any shared word
~0.8+ and produced confident false positives (brief §5c/§5d).

Everything sits behind ``SearchService`` so the eventual pgvector + Postgres-FTS
swap (multi-tenant scale) is a contained change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api.config import Settings, get_settings
from api.db.fts import build_keywords
from api.db.models import Exercise
from api.services.embedder import embed, embed_batch, embed_query
from api.services.vecstore import VecStore


@dataclass
class SearchHit:
    exercise: Exercise
    score: float


def _fts_match_query(q: str) -> str | None:
    """Build a safe FTS5 MATCH expression: prefix-match each token, OR-joined.

    Tokenizing to alnum runs drops FTS5 special characters (``-``, ``"``, ``*``)
    so user input can't break the query or trigger operator semantics.
    """
    tokens = re.findall(r"[a-z0-9]+", q.lower())
    if not tokens:
        return None
    return " OR ".join(f'"{t}"*' for t in tokens)


def _embed_text(name: str, primary, secondary, equipment, category, mechanic) -> str:
    kw = build_keywords(
        primary_muscles=primary or [],
        secondary_muscles=secondary or [],
        equipment=equipment,
        category=category,
        mechanic=mechanic,
    )
    return f"{name} {kw}".strip()


class SearchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.vec = VecStore(settings.vector_store_path, dim=settings.embed_dim)
        self.name_vec = VecStore(settings.name_vector_store_path, dim=settings.embed_dim)

    # -- retrieval -------------------------------------------------------- #
    def _bm25(self, session: Session, query: str, limit: int) -> list[int]:
        mq = _fts_match_query(query)
        if not mq:
            return []
        rows = session.execute(
            text(
                "SELECT rowid FROM exercises_fts WHERE exercises_fts MATCH :q "
                "ORDER BY bm25(exercises_fts) LIMIT :lim"
            ),
            {"q": mq, "lim": limit},
        ).fetchall()
        return [r[0] for r in rows]

    def _vector(self, query: str, k: int) -> list[int]:
        hits = self.vec.search(embed_query(query), k=k)
        return [int(h["id"]) for h in hits]

    def _rrf(self, rank_lists: list[list[int]]) -> dict[int, float]:
        k = self.settings.rrf_k
        scores: dict[int, float] = {}
        for lst in rank_lists:
            for rank, id_ in enumerate(lst):
                scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank + 1)
        return scores

    def search(
        self, session: Session, query: str, *, tenant_id: str, limit: int | None = None
    ) -> list[SearchHit]:
        limit = limit or self.settings.search_limit
        pool = limit * 3
        fused = self._rrf([self._bm25(session, query, pool), self._vector(query, pool)])
        if not fused:
            return []
        ordered_ids = sorted(fused, key=lambda i: fused[i], reverse=True)
        by_id = {
            e.id: e
            for e in session.scalars(select(Exercise).where(Exercise.id.in_(ordered_ids)))
        }
        out: list[SearchHit] = []
        for id_ in ordered_ids:
            ex = by_id.get(id_)
            if ex is None or ex.canonical_exercise_id is not None:
                continue  # missing or an alias row -> skip (canonical shows instead)
            if ex.tenant_id is not None and ex.tenant_id != tenant_id:
                continue  # another tenant's private entry
            out.append(SearchHit(exercise=ex, score=fused[id_]))
            if len(out) >= limit:
                break
        return out

    # -- indexing --------------------------------------------------------- #
    def index_exercise(self, exercise: Exercise) -> None:
        txt = _embed_text(
            exercise.name,
            exercise.primary_muscles,
            exercise.secondary_muscles,
            exercise.equipment,
            exercise.category,
            exercise.mechanic,
        )
        self.vec.set(str(exercise.id), embed(txt))
        self.vec.save()
        self.name_vec.set(str(exercise.id), embed(exercise.name))
        self.name_vec.save()

    def remove_exercise(self, exercise_id: int) -> None:
        if self.vec.delete(str(exercise_id)):
            self.vec.save()
        if self.name_vec.delete(str(exercise_id)):
            self.name_vec.save()

    def reindex(self, session: Session) -> int:
        """Rebuild the entire vector index from the catalog (skips alias rows)."""
        self.vec.clear()
        self.name_vec.clear()
        exercises = list(
            session.scalars(select(Exercise).where(Exercise.canonical_exercise_id.is_(None)))
        )
        if not exercises:
            self.vec.save()
            self.name_vec.save()
            return 0
        texts = [
            _embed_text(
                e.name, e.primary_muscles, e.secondary_muscles, e.equipment, e.category, e.mechanic
            )
            for e in exercises
        ]
        for e, v in zip(exercises, embed_batch(texts), strict=True):
            self.vec.set(str(e.id), v)
        for e, v in zip(exercises, embed_batch([e.name for e in exercises]), strict=True):
            self.name_vec.set(str(e.id), v)
        self.vec.save()
        self.name_vec.save()
        return len(exercises)

    # -- dedup hint --------------------------------------------------------- #
    def find_similar_hint(
        self, name: str, *, threshold: float | None = None
    ) -> tuple[int, float] | None:
        """Return ``(exercise_id, similarity)`` of the nearest catalog entry above
        the dedup-hint threshold on the name-only index, else ``None``. Advisory
        only — callers must never use this to block a create; the exact
        normalized-name check is the only hard gate."""
        # Symmetric (name <-> indexed name): embed the candidate as a passage,
        # NOT with the asymmetric query prefix.
        threshold = self.settings.dedup_hint_threshold if threshold is None else threshold
        hits = self.name_vec.search(embed(name), k=5)
        for h in hits:
            if h["similarity"] >= threshold:
                return int(h["id"]), h["similarity"]
        return None


@lru_cache
def get_search_service() -> SearchService:
    return SearchService(get_settings())


def main() -> None:
    """`python -m api.services.search` — rebuild the vector index from the catalog."""
    from api.db.session import SessionLocal

    svc = get_search_service()
    with SessionLocal() as session:
        n = svc.reindex(session)
    print(
        f"Reindexed {n} exercises -> {svc.settings.vector_store_path} "
        f"+ {svc.settings.name_vector_store_path}"
    )


if __name__ == "__main__":
    main()

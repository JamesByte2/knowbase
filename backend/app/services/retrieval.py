"""检索服务：问题向量化 -> Qdrant 召回 -> 关联原文与来源文档。"""

from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Chunk, Document
from app.services.pipeline import collection_name, embed_texts, get_qdrant


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    filename: str
    page: int
    content: str
    score: float


def search(db: Session, client: QdrantClient, kb_id: int, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
    s = get_settings()
    k = top_k or s.top_k

    [vector] = embed_texts([question])
    hits = client.query_points(
        collection_name=collection_name(kb_id),
        query=vector,
        limit=k,
        query_filter=Filter(must=[FieldCondition(key="kb_id", match=MatchValue(value=kb_id))]),
        with_payload=True,
    ).points
    if not hits:
        return []

    chunk_ids = [h.payload["chunk_id"] for h in hits]
    rows = db.execute(
        select(Chunk, Document.filename)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    by_id = {chunk.id: (chunk, filename) for chunk, filename in rows}

    results: list[RetrievedChunk] = []
    for h in hits:
        found = by_id.get(h.payload.get("chunk_id"))
        if found is None:  # 向量残留但 MySQL 已删（理论上不应发生，防御性跳过）
            continue
        chunk, filename = found
        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                page=chunk.page,
                content=chunk.content,
                score=h.score,
            )
        )
    return results

"""入库流水线：解析 -> 切片 -> 向量化 -> Qdrant 入库，维护文档状态机。

状态机：pending -> parsing -> ready | failed（任一步异常落 failed 并记录原因）。
每个知识库一个 Qdrant collection（kb_{id}），point payload 冗余
kb_id/document_id/chunk_id 便于按文档过滤删除。
"""

import logging
import threading
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Chunk, Document
from app.services.parser import parse_file

logger = logging.getLogger("knowbase.pipeline")


def collection_name(kb_id: int) -> str:
    return f"kb_{kb_id}"


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url)


def ensure_collection(client: QdrantClient, kb_id: int) -> None:
    name = collection_name(kb_id)
    if not client.collection_exists(name):
        client.create_collection(name, vectors_config=VectorParams(size=get_settings().embedding_dim, distance=Distance.COSINE))


def drop_collection(client: QdrantClient, kb_id: int) -> None:
    name = collection_name(kb_id)
    if client.collection_exists(name):
        client.delete_collection(name)


def delete_document_vectors(client: QdrantClient, kb_id: int, document_id: int) -> None:
    name = collection_name(kb_id)
    if client.collection_exists(name):
        client.delete(
            collection_name=name,
            points_selector=Filter(must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]),
        )


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """固定长度滑窗切片。先按段落聚簇，超长再硬切，避免把语义切碎。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    # 先按换行聚簇成不超长的块
    clusters: list[str] = []
    buffer = ""
    for para in text.replace("\r\n", "\n").split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(buffer) + len(para) + 1 <= size:
            buffer = f"{buffer}\n{para}" if buffer else para
            continue
        if buffer:
            clusters.append(buffer)
            buffer = ""
        # 单段超长，硬切
        for i in range(0, len(para), size - overlap):
            piece = para[i : i + size]
            if len(piece) > overlap:  # 尾部过短的片段并回前一块
                clusters.append(piece)
            elif clusters:
                clusters[-1] = f"{clusters[-1]}\n{piece}"
    if buffer:
        clusters.append(buffer)

    # 相邻块拼接处保留少量重叠，维持上下文连续性
    chunks: list[str] = []
    for c in clusters:
        if chunks and overlap > 0 and len(chunks[-1]) >= overlap and len(c) + overlap <= size:
            c = f"{chunks[-1][-overlap:]}\n{c}"
        if chunks and len(chunks[-1]) + len(c) + 1 <= size:
            chunks[-1] = f"{chunks[-1]}\n{c}"
        else:
            chunks.append(c)
    return [c for c in chunks if c.strip()]


def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    s = get_settings()
    client = OpenAI(base_url=s.embedding_base_url, api_key=s.embedding_api_key)
    out: list[list[float]] = []
    batch = 32
    for i in range(0, len(texts), batch):
        resp = client.embeddings.create(model=s.embedding_model, input=texts[i : i + batch])
        out.extend([item.embedding for item in resp.data])
    return out


def process_document(document_id: int) -> None:
    """流水线主体，在后台线程中独立开 DB 会话运行。"""
    db: Session = SessionLocal()
    client = get_qdrant()
    s = get_settings()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = "parsing"
        db.commit()

        data = (Path(s.upload_dir) / doc.stored_name).read_bytes()
        segments = parse_file(doc.file_type, data)

        chunks: list[Chunk] = []
        seq = 0
        for seg in segments:
            for piece in chunk_text(seg.text, s.chunk_size, s.chunk_overlap):
                chunks.append(
                    Chunk(
                        document_id=doc.id,
                        kb_id=doc.kb_id,
                        seq=seq,
                        content=piece,
                        page=seg.page,
                        vector_id=uuid.uuid4().hex,
                    )
                )
                seq += 1

        if not chunks:
            raise ValueError("文档未解析出任何文本内容")

        vectors = embed_texts([c.content for c in chunks])

        # 先 flush 让 Chunk 拿到自增 id，payload 里的 chunk_id 才有效
        db.add_all(chunks)
        db.flush()

        ensure_collection(client, doc.kb_id)
        client.upsert(
            collection_name=collection_name(doc.kb_id),
            points=[
                PointStruct(
                    id=int(c.vector_id[:12], 16),
                    vector=v,
                    payload={"kb_id": doc.kb_id, "document_id": doc.id, "chunk_id": c.id, "seq": c.seq, "page": c.page},
                )
                for c, v in zip(chunks, vectors)
            ],
        )

        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error = ""
        db.commit()
        logger.info("document %s ready: %s chunks", doc.id, len(chunks))
    except Exception as exc:  # noqa: BLE001 - 状态机要求任何异常都落到 failed
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = str(exc)[:500]
            db.commit()
        logger.exception("document %s pipeline failed", document_id)
    finally:
        db.close()
        client.close()


def start_pipeline(document_id: int) -> None:
    threading.Thread(target=process_document, args=(document_id,), daemon=True).start()

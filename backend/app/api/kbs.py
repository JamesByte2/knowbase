import os
import time
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import current_user
from app.config import get_settings
from app.db import get_db
from app.models import Chunk, Document, KnowledgeBase, User

router = APIRouter(prefix="/api", tags=["knowledge-base"])

ALLOWED_TYPES = {"pdf": ".pdf", "docx": ".docx", "md": ".md", "txt": ".txt", "xlsx": ".xlsx"}


class KBIn(BaseModel):
    name: str
    description: str = ""


def _owned_kb(kb_id: int, user: User, db: Session) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.user_id != user.id:
        raise HTTPException(404, "知识库不存在")
    return kb


@router.get("/kbs")
def list_kbs(user: User = Depends(current_user), db: Session = Depends(get_db)):
    kbs = db.scalars(
        select(KnowledgeBase).where(KnowledgeBase.user_id == user.id).order_by(KnowledgeBase.id.desc())
    ).all()
    return [
        {
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "created_at": kb.created_at,
        }
        for kb in kbs
    ]


@router.post("/kbs")
def create_kb(body: KBIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kb = KnowledgeBase(user_id=user.id, name=body.name.strip(), description=body.description.strip())
    db.add(kb)
    db.commit()
    return {"id": kb.id}


@router.delete("/kbs/{kb_id}")
def delete_kb(kb_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    kb = _owned_kb(kb_id, user, db)
    doc_ids = db.scalars(select(Document.id).where(Document.kb_id == kb_id)).all()
    if doc_ids:
        db.query(Chunk).filter(Chunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(Chunk).filter(Chunk.kb_id == kb_id).delete(synchronize_session=False)
    # TODO(M2): 同步删除 Qdrant 中该知识库的 collection
    db.delete(kb)
    db.commit()
    return {"ok": True}


@router.post("/kbs/{kb_id}/documents")
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    _owned_kb(kb_id, user, db)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_TYPES.values():
        raise HTTPException(400, f"仅支持 {', '.join(ALLOWED_TYPES.values())}")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过 50MB")

    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    save_name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.upload_dir, save_name), "wb") as f:
        f.write(content)

    doc = Document(
        kb_id=kb_id,
        filename=file.filename or save_name,
        file_type=ext.lstrip("."),
        size=len(content),
        status="pending",
        created_at=int(time.time()),
    )
    db.add(doc)
    db.commit()
    # TODO(M2): 投递解析任务 -> 切片 -> 向量化 -> 状态机 pending/parsing/ready/failed
    return {"id": doc.id, "status": doc.status}


@router.get("/documents/{doc_id}/chunks")
def list_chunks(doc_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(404, "文档不存在")
    _owned_kb(doc.kb_id, user, db)
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.seq)).all()
    return [{"seq": c.seq, "page": c.page, "content": c.content} for c in chunks]

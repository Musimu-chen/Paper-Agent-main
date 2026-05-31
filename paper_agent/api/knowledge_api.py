"""知识库 API 路由"""

import os
import logging
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

from paper_agent.knowledge.kb_manager import KnowledgeManager, DatabaseInfo
from paper_agent.knowledge.kb_embedder import KbEmbedder

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# 全局实例（懒加载）
_kb_manager: Optional[KnowledgeManager] = None
_kb_embedder: Optional[KbEmbedder] = None
_selected_db_id: Optional[str] = None

# 上传文件存储目录
UPLOAD_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


def get_kb_manager() -> KnowledgeManager:
    """获取知识库管理器单例"""
    global _kb_manager
    if _kb_manager is None:
        _kb_manager = KnowledgeManager()
    return _kb_manager


def get_kb_embedder() -> KbEmbedder:
    """获取嵌入器单例"""
    global _kb_embedder
    if _kb_embedder is None:
        _kb_embedder = KbEmbedder()
    return _kb_embedder


@router.get("/databases")
async def list_databases():
    """列出所有知识库"""
    kb = get_kb_manager()
    databases = kb.list_databases()
    return {"databases": [db.to_dict() for db in databases]}


@router.post("/databases")
async def create_database(data: dict):
    """创建新知识库
    Body: {"name": "xxx", "description": "xxx"}
    """
    name = data.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="知识库名称不能为空")

    description = data.get("description", "")
    kb = get_kb_manager()
    db_info = kb.create_database(name, description)
    return {"database": db_info.to_dict()}


@router.get("/databases/{db_id}")
async def get_database(db_id: str):
    """获取知识库详情"""
    kb = get_kb_manager()
    db_info = kb.get_database(db_id)
    if db_info is None:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"database": db_info.to_dict()}


@router.put("/databases/{db_id}")
async def update_database(db_id: str, data: dict):
    """更新知识库信息"""
    kb = get_kb_manager()
    db_info = kb.get_database(db_id)
    if db_info is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    # ChromaDB 暂不支持直接更新元数据，先删除再添加
    name = data.get("name", db_info.name)
    description = data.get("description", db_info.description)
    kb.delete_database(db_id)
    new_db = kb.create_database(name, description)
    return {"database": new_db.to_dict()}


@router.delete("/databases/{db_id}")
async def delete_database(db_id: str):
    """删除知识库"""
    global _selected_db_id
    kb = get_kb_manager()
    db_info = kb.get_database(db_id)
    if db_info is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    kb.delete_database(db_id)
    if _selected_db_id == db_id:
        _selected_db_id = None
    return {"status": "ok", "message": f"知识库 {db_info.name} 已删除"}


@router.get("/databases/select")
async def select_database(db_id: str = Query("", description="知识库 ID，空字符串表示取消选择")):
    """选择/取消当前使用的知识库"""
    global _selected_db_id
    if db_id:
        kb = get_kb_manager()
        db_info = kb.get_database(db_id)
        if db_info is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        _selected_db_id = db_id
        return {"status": "ok", "selected_id": db_id, "name": db_info.name}
    else:
        _selected_db_id = None
        return {"status": "ok", "selected_id": None, "message": "已取消选择"}


@router.post("/databases/{db_id}/documents")
async def add_documents(db_id: str, data: dict):
    """向知识库添加文档
    Body: {"items": ["文本1", "文本2"], "params": {}}
    """
    kb = get_kb_manager()
    db_info = kb.get_database(db_id)
    if db_info is None:
        raise HTTPException(status_code=404, detail="知识库不存在")

    items = data.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="文档内容不能为空")

    count = kb.add_documents(db_id, documents=items)
    return {"status": "ok", "added_count": count, "total_count": kb.get_document_count(db_id)}


@router.get("/databases/{db_id}/documents/{doc_id}")
async def get_document_info(db_id: str, doc_id: str):
    """获取文档详细信息"""
    kb = get_kb_manager()
    try:
        coll = kb.get_collection(db_id)
        results = coll.get(ids=[doc_id])
        if not results["ids"]:
            raise HTTPException(status_code=404, detail="文档不存在")

        meta = results["metadatas"][0] if results["metadatas"] else {}
        content = results["documents"][0] if results["documents"] else ""

        return {
            "id": doc_id,
            "filename": meta.get("filename", doc_id),
            "content": content,
            "metadata": meta,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"获取文档失败: {str(e)}")


@router.get("/databases/{db_id}/documents/{doc_id}/basic")
async def get_document_basic_info(db_id: str, doc_id: str):
    """获取文档基本信息（不含内容）"""
    kb = get_kb_manager()
    try:
        coll = kb.get_collection(db_id)
        results = coll.get(ids=[doc_id])
        if not results["ids"]:
            raise HTTPException(status_code=404, detail="文档不存在")

        meta = results["metadatas"][0] if results["metadatas"] else {}
        return {
            "id": doc_id,
            "filename": meta.get("filename", doc_id),
            "file_type": meta.get("file_type", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "total_chunks": meta.get("total_chunks", 1),
            "metadata": meta,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"获取文档失败: {str(e)}")


@router.get("/databases/{db_id}/documents/{doc_id}/content")
async def get_document_content(db_id: str, doc_id: str):
    """获取文档内容"""
    kb = get_kb_manager()
    try:
        coll = kb.get_collection(db_id)
        results = coll.get(ids=[doc_id])
        if not results["ids"]:
            raise HTTPException(status_code=404, detail="文档不存在")

        return {
            "id": doc_id,
            "content": results["documents"][0] if results["documents"] else "",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"获取文档失败: {str(e)}")


@router.delete("/databases/{db_id}/documents/{doc_id}")
async def delete_document(db_id: str, doc_id: str):
    """删除文档"""
    kb = get_kb_manager()
    try:
        coll = kb.get_collection(db_id)
        results = coll.get(ids=[doc_id])
        if not results["ids"]:
            raise HTTPException(status_code=404, detail="文档不存在")

        coll.delete(ids=[doc_id])
        return {
            "status": "ok",
            "message": f"文档 {doc_id} 已删除",
            "total_count": coll.count(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"删除文档失败: {str(e)}")


@router.post("/databases/{db_id}/query-test")
async def query_database(db_id: str, data: dict):
    """在知识库中测试检索
    Body: {"query": "搜索文本", "meta": {}}
    """
    kb = get_kb_manager()
    query_text = data.get("query", "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="查询文本不能为空")

    try:
        results = kb.query_database(db_id, query_text, n_results=10)
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    db_id: Optional[str] = Form(None),
    allow_jsonl: bool = Form(False),
):
    """上传文件到知识库"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 检查文件类型
    suffix = Path(file.filename).suffix.lower()
    supported = KbEmbedder.get_supported_types()
    if suffix not in supported:
        allowed = ", ".join(supported.keys())
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix}。支持的类型: {allowed}",
        )

    # 检查 jsonl 权限
    if suffix == ".jsonl" and not allow_jsonl:
        raise HTTPException(
            status_code=400,
            detail="上传 jsonl 文件需要 allow_jsonl=true 参数",
        )

    # 保存文件
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path_obj = UPLOAD_DIR / file.filename
    content = await file.read()

    with open(file_path_obj, "wb") as f:
        f.write(content)

    try:
        # 处理文件
        embedder = get_kb_embedder()
        chunks, metadatas, chunk_ids = embedder.prepare_documents(
            str(file_path_obj), file.filename,
        )

        # 存入知识库
        kb = get_kb_manager()
        target_db = db_id

        # 如果没有指定知识库，创建或使用默认知识库
        if not target_db:
            global _selected_db_id
            if _selected_db_id:
                target_db = _selected_db_id
            else:
                # 自动创建一个默认知识库
                default_db = kb.create_database("默认知识库", "自动创建的知识库")
                _selected_db_id = default_db.id
                target_db = default_db.id

        # 确保知识库存在
        db_info = kb.get_database(target_db)
        if db_info is None:
            raise HTTPException(status_code=404, detail=f"目标知识库 {target_db} 不存在")

        kb.add_documents(target_db, documents=chunks, metadatas=metadatas, ids=chunk_ids)

        return {
            "status": "ok",
            "filename": file.filename,
            "file_size": len(content),
            "chunk_count": len(chunks),
            "database_id": target_db,
            "database_name": db_info.name,
        }

    except Exception as e:
        logger.error(f"文件处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件处理失败: {str(e)}")


@router.get("/files/supported-types")
async def get_supported_types():
    """获取支持上传的文件类型列表"""
    return {"types": KbEmbedder.get_supported_types()}


def get_selected_db_id() -> Optional[str]:
    """获取当前选中的知识库 ID（供其他模块使用）"""
    return _selected_db_id
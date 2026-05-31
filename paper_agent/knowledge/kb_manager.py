"""知识库管理器 - CRUD 操作 for ChromaDB"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from paper_agent.config import config

logger = logging.getLogger(__name__)

# 知识库元数据集合名（存储数据库列表信息）
META_COLLECTION = "kb_metadata"


class DatabaseInfo:
    """知识库信息"""
    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        created_at: str = "",
        document_count: int = 0,
        embedding_model: str = "",
    ):
        self.id = id
        self.name = name
        self.description = description
        self.created_at = created_at
        self.document_count = document_count
        self.embedding_model = embedding_model

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "document_count": self.document_count,
            "embedding_model": self.embedding_model,
        }


class DocumentInfo:
    """文档信息"""
    def __init__(
        self,
        id: str,
        filename: str,
        file_type: str = "",
        file_size: int = 0,
        chunk_count: int = 0,
        created_at: str = "",
        metadata: dict = None,
    ):
        self.id = id
        self.filename = filename
        self.file_type = file_type
        self.file_size = file_size
        self.chunk_count = chunk_count
        self.created_at = created_at
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


class KnowledgeManager:
    """知识库管理器"""

    def __init__(self, persist_dir: Optional[str] = None):
        if persist_dir is None:
            project_root = Path(__file__).parent.parent.parent
            persist_dir = str(project_root / "data" / "chromadb_kb")

        self.persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # 确保元数据集合存在
        self._init_meta_collection()

    def _init_meta_collection(self):
        """初始化元数据集合"""
        try:
            self._client.get_collection(META_COLLECTION)
        except Exception:
            self._client.create_collection(META_COLLECTION)
            logger.info("创建知识库元数据集合")

    def _get_meta_collection(self):
        """获取元数据集合"""
        return self._client.get_or_create_collection(META_COLLECTION)

    def list_databases(self) -> List[DatabaseInfo]:
        """列出所有知识库"""
        try:
            meta_coll = self._get_meta_collection()
            results = meta_coll.get()

            databases = []
            for i, doc_id in enumerate(results.get("ids", [])):
                meta = results.get("metadatas", [])[i] if i < len(results.get("metadatas", [])) else {}
                databases.append(DatabaseInfo(
                    id=doc_id,
                    name=meta.get("name", doc_id),
                    description=meta.get("description", ""),
                    created_at=meta.get("created_at", ""),
                    embedding_model=meta.get("embedding_model", ""),
                    document_count=meta.get("document_count", 0),
                ))
            return databases

        except Exception as e:
            logger.error(f"列出知识库失败: {e}")
            return []

    def create_database(self, name: str, description: str = "") -> DatabaseInfo:
        """创建新知识库"""
        db_id = f"kb_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now().isoformat()

        # 创建 ChromaDB collection
        try:
            self._client.create_collection(db_id)
        except Exception as e:
            logger.warning(f"创建 collection 失败（可能已存在）: {e}")

        # 保存元数据
        meta_coll = self._get_meta_collection()
        emb_model = config.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B")

        meta_coll.add(
            ids=[db_id],
            documents=[name],
            metadatas=[{
                "name": name,
                "description": description,
                "created_at": created_at,
                "document_count": 0,
                "embedding_model": emb_model,
            }],
        )

        logger.info(f"创建知识库: {name} (id={db_id})")
        return DatabaseInfo(
            id=db_id,
            name=name,
            description=description,
            created_at=created_at,
            embedding_model=emb_model,
        )

    def get_database(self, db_id: str) -> Optional[DatabaseInfo]:
        """获取知识库信息"""
        meta_coll = self._get_meta_collection()
        results = meta_coll.get(ids=[db_id])

        if results["ids"]:
            meta = results["metadatas"][0] if results["metadatas"] else {}
            return DatabaseInfo(
                id=db_id,
                name=meta.get("name", db_id),
                description=meta.get("description", ""),
                created_at=meta.get("created_at", ""),
                embedding_model=meta.get("embedding_model", ""),
                document_count=meta.get("document_count", 0),
            )
        return None

    def delete_database(self, db_id: str) -> bool:
        """删除知识库"""
        try:
            # 删除 collection
            self._client.delete_collection(db_id)
        except Exception as e:
            logger.warning(f"删除 collection 失败: {e}")

        # 删除元数据
        try:
            meta_coll = self._get_meta_collection()
            meta_coll.delete(ids=[db_id])
        except Exception as e:
            logger.warning(f"删除元数据失败: {e}")

        logger.info(f"删除知识库: {db_id}")
        return True

    def add_documents(
        self,
        db_id: str,
        documents: List[str],
        metadatas: List[dict] = None,
        ids: List[str] = None,
    ) -> int:
        """向知识库添加文档"""
        try:
            coll = self._client.get_or_create_collection(db_id)
        except Exception as e:
            raise ValueError(f"知识库 {db_id} 不存在: {e}")

        if not ids:
            ids = [f"doc_{uuid.uuid4().hex[:16]}" for _ in documents]

        if not metadatas:
            metadatas = [{"source": "manual"} for _ in documents]

        coll.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

        # 更新计数
        count = coll.count()
        self._update_doc_count(db_id, count)

        logger.info(f"添加 {len(documents)} 个文档到知识库 {db_id}，当前总数: {count}")
        return len(documents)

    def _update_doc_count(self, db_id: str, count: int):
        """更新知识库文档计数"""
        try:
            meta_coll = self._get_meta_collection()
            results = meta_coll.get(ids=[db_id])
            if results["ids"]:
                meta = results["metadatas"][0]
                meta["document_count"] = count
                meta_coll.update(ids=[db_id], metadatas=[meta])
        except Exception as e:
            logger.warning(f"更新文档计数失败: {e}")

    def query_database(
        self,
        db_id: str,
        query_text: str,
        n_results: int = 5,
    ) -> List[dict]:
        """在知识库中检索"""
        try:
            coll = self._client.get_collection(db_id)
        except Exception as e:
            raise ValueError(f"知识库 {db_id} 不存在: {e}")

        results = coll.query(
            query_texts=[query_text],
            n_results=n_results,
        )

        docs = []
        for i, doc_id in enumerate(results.get("ids", [[]])[0]):
            doc = {
                "id": doc_id,
                "content": results["documents"][0][i] if results.get("documents") else "",
                "distance": results["distances"][0][i] if results.get("distances") else None,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
            }
            docs.append(doc)

        return docs

    def get_collection(self, db_id: str):
        """直接获取 ChromaDB collection（供 Retriever 使用）"""
        return self._client.get_or_create_collection(db_id)

    def get_document_count(self, db_id: str) -> int:
        """获取文档数量"""
        try:
            coll = self._client.get_collection(db_id)
            return coll.count()
        except Exception:
            return 0

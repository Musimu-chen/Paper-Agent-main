"""ChromaDB 向量存储服务 - 简化版"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from paper_agent.models import ExtractedPapersData, PaperMetadata

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("chromadb 未安装，向量存储功能不可用")


class VectorStore:
    """ChromaDB 向量存储封装"""

    def __init__(self, collection_name: str = "paper_agent"):
        if not CHROMA_AVAILABLE:
            self._available = False
            return
        self._available = True

        from paper_agent.config import config

        self.client = chromadb.PersistentClient(
            path=str(Path(__file__).parent.parent.parent / "data" / "chromadb_simple")
        )

        # 获取嵌入模型配置
        embed_cfg = config.get("embedding-model", config.get("default-embedding-model", {}))

        # 统一从 .env 环境变量读取 API 配置（与 analysis_chain 一致）
        _api_key = config.get("SILICONFLOW_API_KEY", "")
        _base_url = config.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1")
        _model_name = embed_cfg.get("model", config.get("EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-8B"))

        os.environ.setdefault("CHROMA_OPENAI_API_KEY", _api_key)
        if _base_url:
            os.environ["CHROMA_OPENAI_BASE_URL"] = _base_url

        embed_func = OpenAIEmbeddingFunction(
            model_name=_model_name,
            api_key=_api_key,
            api_base=_base_url,
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=embed_func,
        )

    @property
    def available(self) -> bool:
        return self._available

    def add_papers(
        self,
        papers: List[PaperMetadata],
        extracted: ExtractedPapersData,
    ) -> None:
        """将论文提取数据存入向量数据库"""
        if not self._available:
            return

        documents = []
        metadatas = []
        ids = []

        for i, paper_data in enumerate(extracted.papers):
            doc = json.dumps(paper_data.model_dump(), ensure_ascii=False)
            documents.append(doc)

            # 构建安全的元数据
            meta = {}
            if i < len(papers):
                for k, v in papers[i].model_dump().items():
                    if v is None:
                        continue
                    if isinstance(v, list):
                        meta[k] = ", ".join(str(x) for x in v)
                    elif isinstance(v, dict):
                        meta[k] = json.dumps(v, ensure_ascii=False)
                    else:
                        meta[k] = v
            metadatas.append(meta)
            ids.append(str(i))

        if documents:
            self.collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(f"已存储 {len(documents)} 篇论文到向量数据库")

    def query(self, query_text: str, n_results: int = 5) -> dict:
        """
        查询相关文档（含元数据）

        Returns:
            {"ids": [[...]], "documents": [[...]], "metadatas": [[...]], "distances": [[...]]}
        """
        if not self._available:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        return results

    def clear(self):
        """清空集合"""
        if self._available:
            try:
                self.client.delete_collection(self.collection.name)
            except Exception:
                pass

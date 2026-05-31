"""知识库文档嵌入器 - 分块 + 嵌入"""

import logging
from typing import List, Optional
from pathlib import Path

from paper_agent.config import config

logger = logging.getLogger(__name__)

# 支持的文件类型
SUPPORTED_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".jsonl": "application/jsonl",
    ".csv": "text/csv",
    ".py": "text/x-python",
}

# 默认分块配置
DEFAULT_CHUNK_SIZE = 1000   # 字符数
DEFAULT_CHUNK_OVERLAP = 200  # 重叠字符数


class TextChunker:
    """文本分块器"""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(self, text: str) -> List[str]:
        """将文本切分为重叠块"""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            start += (self.chunk_size - self.chunk_overlap)

        return chunks

    def chunk_lines(self, lines: List[str]) -> List[str]:
        """按行分块（保持段落完整性）"""
        chunks = []
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line)
            if current_len + line_len > self.chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                # 保留最后几行作为重叠
                overlap_lines = []
                overlap_len = 0
                for l in reversed(current_chunk):
                    if overlap_len + len(l) <= self.chunk_overlap:
                        overlap_lines.insert(0, l)
                        overlap_len += len(l)
                    else:
                        break
                current_chunk = overlap_lines
                current_len = overlap_len

            current_chunk.append(line)
            current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks


class KbEmbedder:
    """知识库嵌入服务"""

    def __init__(self, chunk_size: int = DEFAULT_CHUNK_SIZE):
        self.chunker = TextChunker(chunk_size=chunk_size)

    def read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容"""
        path = Path(file_path)
        suffix = path.suffix.lower()

        try:
            if suffix == ".pdf":
                return self._read_pdf(file_path)
            else:
                # 尝试多种编码
                for encoding in ["utf-8", "gbk", "latin-1"]:
                    try:
                        with open(file_path, "r", encoding=encoding) as f:
                            return f.read()
                    except UnicodeDecodeError:
                        continue
                return None
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return None

    def _read_pdf(self, file_path: str) -> str:
        """读取 PDF 文件文本"""
        try:
            import PyPDF2
            text_parts = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
            return "\n".join(text_parts)
        except ImportError:
            logger.warning("PyPDF2 未安装，尝试使用 pdfplumber")
            try:
                import pdfplumber
                text_parts = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                return "\n".join(text_parts)
            except ImportError:
                raise RuntimeError("需要安装 PyPDF2 或 pdfplumber 来读取 PDF 文件")

    def prepare_documents(
        self,
        file_path: str,
        filename: str,
    ) -> tuple:
        """
        准备嵌入文档：读取文件 → 分块 → 返回 (documents, metadatas, ids)

        Returns:
            (chunks, metadatas, chunk_ids)
        """
        content = self.read_file(file_path)
        if not content:
            raise ValueError(f"无法读取文件内容: {filename}")

        # 分块
        lines = content.split("\n")
        if len(lines) > 1:
            chunks = self.chunker.chunk_lines(lines)
        else:
            chunks = self.chunker.chunk(content)

        # 生成元数据
        file_path_obj = Path(filename)
        metadatas = []
        chunk_ids = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{file_path_obj.stem}_{i}"
            chunk_ids.append(chunk_id)
            metadatas.append({
                "filename": filename,
                "file_type": file_path_obj.suffix.lower(),
                "chunk_index": i,
                "total_chunks": len(chunks),
                "source": "file_upload",
            })

        logger.info(f"文件 {filename} 分块完成: {len(chunks)} 块（原始长度 {len(content)} 字符）")
        return chunks, metadatas, chunk_ids

    @staticmethod
    def get_supported_types() -> dict:
        """获取支持的文件类型"""
        return SUPPORTED_TYPES.copy()

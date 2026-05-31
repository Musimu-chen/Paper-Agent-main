"""Semantic Scholar API 客户端 - 论文检索"""

import logging
import asyncio
from typing import List, Optional

import httpx

from paper_agent.models import PaperMetadata
from paper_agent.config import config

logger = logging.getLogger(__name__)

# 搜索返回字段
SEARCH_FIELDS = [
    "paperId",
    "title",
    "abstract",
    "authors",
    "authors.name",
    "year",
    "citationCount",
    "url",
    "fieldsOfStudy",
    "publicationVenue",
    "externalIds",
    "openAccessPdf",
]

DEFAULT_LIMIT = 20
MAX_RESULTS_PER_REQUEST = 100  # Semantic Scholar 单次最大返回数


class SemanticScholarClient:
    """Semantic Scholar API 异步客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 3,
        rate_limit: float = 2.0,  # 请求间隔（秒），官方限制 1 req/s，留 100% 余量
    ):
        # 从 config 读取配置，参数可覆盖
        self.api_key = api_key if api_key is not None else config.get("SEMANTIC_SCHOLAR_API_KEY", None)
        self.base_url = base_url if base_url is not None else config.get("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1")
        self.timeout = timeout if timeout is not None else float(config.get("SEMANTIC_SCHOLAR_TIMEOUT", "30"))
        self.max_retries = max_retries
        self.rate_limit = rate_limit
        import time
        self._last_request_time = time.monotonic()  # 初始化为当前时间，首次请求也会等待
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（懒加载）"""
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": "Paper-Agent/2.0",
            }
            if self.api_key:
                headers["x-api-key"] = self.api_key

            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _wait_for_rate_limit(self):
        """速率限制：确保两次请求间隔 >= rate_limit 秒"""
        import time
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit:
            wait = self.rate_limit - elapsed
            await asyncio.sleep(wait)
        self._last_request_time = time.monotonic()

    async def _request_with_retry(self, url: str, params: dict) -> dict:
        """带重试和速率限制的请求"""
        client = await self._get_client()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # ★ 速率限制：仅首次请求前等待（重试不叠加延迟）
                if attempt == 0:
                    await self._wait_for_rate_limit()

                response = await client.get(url, params=params)

                if response.status_code == 429:
                    # 速率限制，等待后重试
                    wait_time = min(2 ** attempt, 30)
                    logger.warning(
                        f"Semantic Scholar 速率限制，等待 {wait_time}s 后重试 (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code >= 500:
                    wait_time = min(2 ** attempt, 10)
                    logger.warning(f"服务器错误，等待 {wait_time}s 后重试: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                raise
            except httpx.RequestError as e:
                last_error = e
                wait_time = min(2 ** attempt, 10)
                logger.warning(f"网络错误，等待 {wait_time}s 后重试: {e}")
                await asyncio.sleep(wait_time)
                continue

        raise last_error or RuntimeError("请求失败，已达最大重试次数")

    def _paper_to_metadata(self, paper: dict) -> PaperMetadata:
        """将 Semantic Scholar 返回格式转为 PaperMetadata"""
        # 提取作者名列表
        authors = []
        for author in paper.get("authors", []):
            name = author.get("name", "")
            if name:
                authors.append(name)

        # 提取分类标签
        categories = paper.get("fieldsOfStudy", []) or []

        # 提取外部 ID
        external_ids = paper.get("externalIds", {}) or {}
        arxiv_id = external_ids.get("ArXiv", "")

        # 构建 paper_id（优先用 ArXiv ID，否则用 Semantic Scholar ID）
        paper_id = arxiv_id or paper.get("paperId", "")

        # 出版信息
        venue = paper.get("publicationVenue") or {}
        venue_name = venue.get("name", "") if venue else ""

        # PDF URL
        pdf_url = ""
        open_access = paper.get("openAccessPdf")
        if open_access and open_access.get("url"):
            pdf_url = open_access["url"]

        return PaperMetadata(
            paper_id=paper_id,
            title=paper.get("title", "") or "",
            authors=authors,
            summary=paper.get("abstract", "") or "",
            published=paper.get("year"),
            published_date=str(paper.get("year", "")) if paper.get("year") else None,
            url=paper.get("url", "") or f"https://semanticscholar.org/paper/{paper.get('paperId', '')}",
            pdf_url=pdf_url,
            primary_category=categories[0] if categories else "",
            categories=categories,
        )

    async def search(
        self,
        queries: List[str],
        max_results: int = DEFAULT_LIMIT,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        fields_of_study: Optional[List[str]] = None,
    ) -> List[PaperMetadata]:
        """
        搜索论文

        Args:
            queries: 搜索关键词列表
            max_results: 最大返回数量
            start_date: 开始年份 (如 "2020")
            end_date: 结束年份 (如 "2024")
            fields_of_study: 限定领域 (如 ["Computer Science"])

        Returns:
            论文元数据列表
        """
        all_papers: List[PaperMetadata] = []
        seen_ids = set()

        # 合并所有查询词
        query_str = " ".join(queries)
        logger.info(f"Semantic Scholar 搜索: '{query_str}', max_results={max_results}")

        try:
            # 分页获取（Semantic Scholar 默认每页最多 100 条）
            limit_per_request = min(max_results, MAX_RESULTS_PER_REQUEST)
            offset = 0

            while len(all_papers) < max_results:
                params = {
                    "query": query_str,
                    "limit": limit_per_request,
                    "offset": offset,
                    "fields": ",".join(SEARCH_FIELDS),
                }

                # 添加年份过滤（过滤掉无效值如 "null"、"None"）
                def _valid_year(v: str) -> bool:
                    if not v or v.lower() in ("null", "none"):
                        return False
                    try:
                        int(v[:4])
                        return True
                    except (ValueError, IndexError):
                        return False

                year_filter = ""
                valid_start = start_date and _valid_year(start_date)
                valid_end = end_date and _valid_year(end_date)
                if valid_start and valid_end:
                    year_filter = f"{start_date[:4]}-{end_date[:4]}"
                elif valid_start:
                    year_filter = f"{start_date[:4]}-"
                elif valid_end:
                    year_filter = f"-{end_date[:4]}"

                if year_filter:
                    params["year"] = year_filter

                # 添加领域过滤
                if fields_of_study:
                    params["fieldsOfStudy"] = ",".join(fields_of_study)

                data = await self._request_with_retry(
                    f"{self.base_url}/paper/search",
                    params=params,
                )

                papers_data = data.get("data", [])
                if not papers_data:
                    break

                for paper in papers_data:
                    paper_id = paper.get("paperId", "")
                    if paper_id and paper_id not in seen_ids:
                        seen_ids.add(paper_id)
                        try:
                            metadata = self._paper_to_metadata(paper)
                            all_papers.append(metadata)
                        except Exception as e:
                            logger.warning(f"解析论文 {paper_id} 元数据失败: {e}")

                # 检查是否还有更多结果
                next_offset = data.get("next")
                if next_offset is not None:
                    offset = next_offset
                else:
                    offset += len(papers_data)

                # 如果返回数量少于请求数，说明已经没有更多结果
                if len(papers_data) < limit_per_request:
                    break

                # 速率限制由 _wait_for_rate_limit 统一控制

            logger.info(f"Semantic Scholar 搜索完成，共找到 {len(all_papers)} 篇论文")
            return all_papers

        except Exception as e:
            logger.error(f"Semantic Scholar 搜索失败: {e}")
            raise

    async def get_paper_detail(
        self,
        paper_id: str,
        fields: Optional[List[str]] = None,
    ) -> dict:
        """
        获取单篇论文的详细信息

        Args:
            paper_id: 论文 ID (Semantic Scholar ID 或 ArXiv ID)
            fields: 需要返回的字段列表

        Returns:
            论文详细信息字典
        """
        if fields is None:
            fields = SEARCH_FIELDS + ["tldr", "citationStyles"]

        params = {"fields": ",".join(fields)}

        # 支持 ArXiv ID 查询
        if ":" not in paper_id and not paper_id.startswith("arxiv:"):
            url = f"{self.base_url}/paper/{paper_id}"
        else:
            url = f"{self.base_url}/paper/ArXiv:{paper_id}"

        data = await self._request_with_retry(url, params=params)
        return data

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> List[dict]:
        """获取论文的引用列表"""
        params = {
            "limit": min(limit, MAX_RESULTS_PER_REQUEST),
            "fields": ",".join(SEARCH_FIELDS),
        }

        data = await self._request_with_retry(
            f"{self.base_url}/paper/{paper_id}/citations",
            params=params,
        )
        return data.get("data", [])

    async def get_references(
        self,
        paper_id: str,
        limit: int = 20,
    ) -> List[dict]:
        """获取论文的参考文献列表"""
        params = {
            "limit": min(limit, MAX_RESULTS_PER_REQUEST),
            "fields": ",".join(SEARCH_FIELDS),
        }

        data = await self._request_with_retry(
            f"{self.base_url}/paper/{paper_id}/references",
            params=params,
        )
        return data.get("data", [])
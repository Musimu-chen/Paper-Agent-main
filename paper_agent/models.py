"""Pydantic 数据模型 - 简化版"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from enum import Enum


# =================== 前端通信模型 ===================

class StepName(str, Enum):
    """工作流步骤枚举"""
    SEARCHING = "searching"
    READING = "reading"
    ANALYZING = "analyzing"
    WRITING = "writing"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    FINISHED = "finished"
    USER_REVIEW = "user_review"  # 等待用户审核检索条件


class BackToFrontData(BaseModel):
    """SSE 推送给前端的状态数据"""
    step: str
    state: str  # initializing / thinking / generating / completed / error / user_review
    data: Any = None


# =================== 搜索模型 ===================

class SearchQuery(BaseModel):
    """LLM 生成的检索条件"""
    queries: List[str] = Field(description="英文检索关键词列表")
    start_date: Optional[str] = Field(default=None, description="开始时间, 格式: YYYY-MM-DD")
    end_date: Optional[str] = Field(default=None, description="结束时间, 格式: YYYY-MM-DD")
    source: str = Field(default="semantic_scholar", description="论文来源: semantic_scholar / arxiv")


class PaperMetadata(BaseModel):
    """单篇论文元数据"""
    paper_id: str
    title: str
    authors: List[str] = []
    summary: str = ""
    published: Optional[int] = None
    published_date: Optional[str] = None
    url: str = ""
    pdf_url: str = ""
    primary_category: str = ""
    categories: List[str] = []
    citation_count: Optional[int] = None  # Semantic Scholar 引用次数
    source: str = "semantic_scholar"  # 论文来源标识


# =================== 阅读模型 ===================

class KeyMethodology(BaseModel):
    name: Optional[str] = Field(default="", description="方法名称")
    principle: Optional[str] = Field(default="", description="核心原理")
    novelty: Optional[str] = Field(default="", description="创新点")

    @model_validator(mode='before')
    @classmethod
    def replace_null_with_default(cls, data: Any) -> Any:
        """LLM 可能返回 null，将其替换为字段默认值"""
        if isinstance(data, dict):
            for field_name, field_info in cls.model_fields.items():
                if field_name in data and data[field_name] is None:
                    if field_info.default is not None:
                        data[field_name] = field_info.default
                    elif field_info.default_factory is not None:
                        data[field_name] = field_info.default_factory()
        return data


class ExtractedPaperData(BaseModel):
    """从单篇论文中提取的结构化信息"""
    core_problem: str = Field(default="", description="核心问题")
    key_methodology: Optional[KeyMethodology] = Field(default_factory=KeyMethodology, description="关键方法")
    datasets_used: Optional[List[str]] = Field(default_factory=list, description="使用的数据集")
    evaluation_metrics: Optional[List[str]] = Field(default_factory=list, description="评估指标")
    main_results: Optional[str] = Field(default="", description="主要结果")
    limitations: Optional[str] = Field(default="", description="局限性")
    contributions: Optional[List[str]] = Field(default_factory=list, description="贡献")

    @model_validator(mode='before')
    @classmethod
    def replace_null_with_default(cls, data: Any) -> Any:
        """LLM 可能返回 null，将其替换为字段默认值"""
        if isinstance(data, dict):
            for field_name, field_info in cls.model_fields.items():
                if field_name in data and data[field_name] is None:
                    if field_info.default is not None:
                        data[field_name] = field_info.default
                    elif field_info.default_factory is not None:
                        data[field_name] = field_info.default_factory()
        return data


class ExtractedPapersData(BaseModel):
    """多篇论文提取结果"""
    papers: List[ExtractedPaperData] = Field(default_factory=list)


# =================== 分析模型 ===================

class ClusterInfo(BaseModel):
    """单个聚类信息"""
    cluster_id: int
    theme: str
    keywords: List[str] = []
    paper_count: int = 0
    papers: List[Dict[str, Any]] = []


class AnalysisResult(BaseModel):
    """分析结果"""
    clusters: List[ClusterInfo] = []
    global_analysis: str = ""


# =================== 写作模型 ===================

class SectionTask(BaseModel):
    """写作子任务"""
    index: int
    title: str
    description: str = ""
    content: Optional[str] = None


class WritingResult(BaseModel):
    """写作结果"""
    sections: List[SectionTask] = []


# =================== 全局工作流状态 ===================

class WorkflowState(BaseModel):
    """简化版全局工作流状态"""
    user_request: str
    max_papers: int = 20

    # 各阶段数据
    search_query: Optional[SearchQuery] = None
    search_results: List[PaperMetadata] = []
    extracted_data: ExtractedPapersData = Field(default_factory=ExtractedPapersData)
    analysis_result: Optional[AnalysisResult] = None
    writing_result: Optional[WritingResult] = None
    report_markdown: str = ""

    # 错误信息
    error: Optional[str] = None

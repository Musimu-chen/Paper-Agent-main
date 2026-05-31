"""配置管理 - 简化版（纯 .env 环境变量）"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv


class Config:
    """单例配置管理类"""

    _instance: Optional["Config"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._config: Dict[str, Any] = {}
        self._load_env()
        self._initialized = True

    def _load_env(self):
        env_path = Path(__file__).parent.parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        for key, value in os.environ.items():
            self._config[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        self._config[key] = value

    def get_llm_config(self, model_type: str = "default-model") -> Dict[str, str]:
        """获取 LLM 连接配置（直接从 .env 读取）"""
        return {
            "model": self.get("LLM_MODEL", "Qwen/Qwen3-32B"),
            "base_url": self.get("LLM_BASE_URL", "https://api.siliconflow.cn/v1"),
            "api_key": self.get("SILICONFLOW_API_KEY", ""),
        }


config = Config()

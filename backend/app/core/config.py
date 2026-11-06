"""配置加载：环境变量（部署相关）+ config/*.yaml（算法参数、Schema 白名单、路径模式）。

所有模块只通过 get_settings() / get_whitelist() / get_patterns() 读取配置，不自行解析 YAML。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings

REPO_ROOT = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[3]))
CONFIG_DIR = REPO_ROOT / "config"
CONTRACTS_DIR = REPO_ROOT / "contracts"


# ---------- 环境变量 ----------


class EnvSettings(BaseSettings):
    app_env: Literal["dev", "prod", "test"] = "dev"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:1.5b"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    sqlite_path: str = str(REPO_ROOT / "data" / "app.db")
    faiss_dir: str = str(REPO_ROOT / "data" / "faiss")
    model_cache_dir: str = str(REPO_ROOT / "data" / "model_cache")
    upload_dir: str = str(REPO_ROOT / "data" / "uploads")
    git_commit: str = "unknown"


# ---------- settings.yaml ----------


class PipelineCfg(BaseModel):
    stub_modules: list[str] = Field(default_factory=list)


class RetrievalCfg(BaseModel):
    min_hops: int = 2
    max_hops: int = 3
    max_anchors: int = 5
    per_hop_candidates: int = 10
    max_paths: int = 20
    top_k_paths: int = 3
    vector_anchor_min_score: float = 0.6


class EvidenceCfg(BaseModel):
    token_budget: int = 3000


class GenerationCfg(BaseModel):
    temperature: float = 0.1
    max_tokens: int = 512
    timeout_s: int = 60
    max_retries: int = 1
    fallback: Literal["template", "none"] = "template"


class IngestCfg(BaseModel):
    allowed_extensions: list[str] = ["pdf", "docx", "txt"]
    max_upload_mb: int = 20
    relation_min_confidence: float = 0.8


class EvalCfg(BaseModel):
    scorer_version: str
    dataset_file: str
    dataset_sha256_file: str
    runs_dir: str


class AppSettings(BaseModel):
    pipeline: PipelineCfg
    retrieval: RetrievalCfg
    evidence: EvidenceCfg
    generation: GenerationCfg
    ingest: IngestCfg
    eval: EvalCfg

    def is_stub(self, module: str) -> bool:
        return module in self.pipeline.stub_modules


# ---------- schema_whitelist.yaml ----------


class NodeSpec(BaseModel):
    zh: str
    required: list[str]
    id_format: str


class RelationSpec(BaseModel):
    zh: str
    endpoints: list[tuple[str, str]]


class Whitelist(BaseModel):
    version: int
    common_node_props: list[str]
    common_relation_props: list[str]
    nodes: dict[str, NodeSpec]
    relations: dict[str, RelationSpec]

    @model_validator(mode="after")
    def _endpoints_are_known_labels(self) -> Whitelist:
        for rel, spec in self.relations.items():
            for a, b in spec.endpoints:
                if a not in self.nodes or b not in self.nodes:
                    raise ValueError(f"{rel} 的端点 {a}->{b} 不在节点白名单中")
        return self

    def allows(self, rel_type: str, from_label: str, to_label: str) -> bool:
        spec = self.relations.get(rel_type)
        return spec is not None and (from_label, to_label) in spec.endpoints


# ---------- path_patterns.yaml ----------


class HopSpec(BaseModel):
    type: str
    stored: tuple[str, str]
    traverse: Literal["forward", "reverse"]

    @property
    def from_label(self) -> str:
        return self.stored[0] if self.traverse == "forward" else self.stored[1]

    @property
    def to_label(self) -> str:
        return self.stored[1] if self.traverse == "forward" else self.stored[0]


class PathPattern(BaseModel):
    name: str
    anchor_label: str
    target_label: str
    required_scope: list[Literal["major_code", "entry_year"]]
    hops: list[HopSpec]


class Patterns(BaseModel):
    patterns: dict[str, PathPattern]


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def get_env() -> EnvSettings:
    return EnvSettings()


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings.model_validate(_load_yaml("settings.yaml"))


@lru_cache
def get_whitelist() -> Whitelist:
    return Whitelist.model_validate(_load_yaml("schema_whitelist.yaml"))


@lru_cache
def get_patterns() -> Patterns:
    return Patterns.model_validate(_load_yaml("path_patterns.yaml"))

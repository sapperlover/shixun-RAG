"""冻结测试集（V1.2 附录 D.1）：D1 锁定文件哈希，D5 只执行，禁止事后修改金标准。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.schemas.resources import EvalQuestion


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, expected_sha256: str | None = None) -> list[EvalQuestion]:
    """读取 JSONL；给出 expected_sha256 时校验文件未被改动。"""
    if expected_sha256 is not None and sha256_of(path) != expected_sha256:
        raise ValueError(f"{path} 的哈希与冻结值不一致，拒绝运行评测")
    questions = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if line.strip():
                try:
                    questions.append(EvalQuestion.model_validate(json.loads(line)))
                except ValueError as exc:
                    raise ValueError(f"{path}:{i} 不符合题目契约: {exc}") from exc
    ids = [q.question_id for q in questions]
    if len(ids) != len(set(ids)):
        raise ValueError("question_id 重复")
    return questions

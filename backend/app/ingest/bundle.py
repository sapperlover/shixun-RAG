"""★ 知识包（knowledge bundle）契约：ingest（组员实现）与图谱构建（graph/build.py）之间的唯一接口。

一个知识包是一个目录，包含四个文件：
  documents.csv   文档清单：来源、授权依据、哈希、适用专业/年级、版本（列见 DOCUMENT_COLUMNS）
  chunks.jsonl    原文块：{chunk_id, doc_id, doc_version, page_start, page_end, section, text}
                  chunk_id 必须等于 app.graph.ids.chunk_id(doc_id, doc_version, sha256(text))
  entities.jsonl  实体：{entity_id, label, name, aliases: [...], props: {...}}
                  label 与 props 必须满足 config/schema_whitelist.yaml 的 required
  relations.csv   人工预核验后的关系（列见 app.ingest.verify_csv.COLUMNS）

ingest 流程（parse → chunk → extract → normalize）的产出就是这四个文件；
build_staging() 只认这四个文件，不关心它们是规则抽取、LLM 抽取还是人工整理出来的。
load() 会做全部静态检查，任何一项不通过都拒绝构建。
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import get_whitelist
from app.graph import ids
from app.ingest import verify_csv

DOCUMENT_COLUMNS = [
    "doc_id",
    "doc_version",
    "title",
    "source_uri",
    "authorization_note",
    "access_level",
    "file_sha256",
    "college_code",
    "major_code",
    "entry_year",
    "notes",
]
FILES = ("documents.csv", "chunks.jsonl", "entities.jsonl", "relations.csv")
VERIFICATION_STATUSES = {"verified", "unverified", "rejected"}


@dataclass
class Entity:
    entity_id: str
    label: str
    name: str
    aliases: list[str] = field(default_factory=list)
    props: dict = field(default_factory=dict)


@dataclass
class Bundle:
    root: Path
    documents: list[dict]
    chunks: list[dict]
    entities: list[Entity]
    relations: list[dict]
    manifest_sha: str


class BundleError(ValueError):
    """知识包不符合契约。message 中列出全部问题。"""


def load(root: Path) -> Bundle:
    root = Path(root)
    missing = [f for f in FILES if not (root / f).exists()]
    if missing:
        raise BundleError(f"{root} 缺少文件: {missing}")

    documents = _read_csv(root / "documents.csv", DOCUMENT_COLUMNS)
    relations = _read_csv(root / "relations.csv", verify_csv.COLUMNS)
    chunks = _read_jsonl(root / "chunks.jsonl")
    entities = [Entity(**e) for e in _read_jsonl(root / "entities.jsonl")]

    errors = _check(documents, chunks, entities, relations)
    if errors:
        raise BundleError("知识包校验失败：\n- " + "\n- ".join(errors))

    h = hashlib.sha256()
    for f in FILES:
        h.update((root / f).read_bytes())
    return Bundle(root, documents, chunks, entities, relations, h.hexdigest())


def _check(documents, chunks, entities, relations) -> list[str]:
    wl = get_whitelist()
    errors: list[str] = []

    doc_keys = {(d["doc_id"], d["doc_version"]) for d in documents}
    if len(doc_keys) != len(documents):
        errors.append("documents.csv 中 (doc_id, doc_version) 重复")
    for d in documents:
        if not d["authorization_note"].strip():
            errors.append(f"文档 {d['doc_id']} 缺少授权依据 authorization_note")
        if d["access_level"] not in ("public", "restricted"):
            errors.append(f"文档 {d['doc_id']} 的 access_level 非法: {d['access_level']}")

    chunk_ids: set[str] = set()
    for c in chunks:
        sha = hashlib.sha256(c["text"].encode("utf-8")).hexdigest()
        expect = ids.chunk_id(c["doc_id"], c["doc_version"], sha)
        if c["chunk_id"] != expect:
            errors.append(f"chunk_id 与内容不符: {c['chunk_id']}（应为 {expect}）")
        if (c["doc_id"], c["doc_version"]) not in doc_keys:
            errors.append(f"{c['chunk_id']} 引用了不存在的文档 {c['doc_id']}@{c['doc_version']}")
        if c["chunk_id"] in chunk_ids:
            errors.append(f"chunk_id 重复: {c['chunk_id']}")
        chunk_ids.add(c["chunk_id"])

    labels: dict[str, str] = {}
    for e in entities:
        spec = wl.nodes.get(e.label)
        if spec is None:
            errors.append(f"实体 {e.entity_id} 的标签 {e.label} 不在白名单")
            continue
        lack = [k for k in spec.required if e.props.get(k) in (None, "")]
        if lack:
            errors.append(f"实体 {e.entity_id}（{e.label}）缺少必需属性 {lack}")
        if e.entity_id in labels:
            errors.append(f"entity_id 重复: {e.entity_id}")
        labels[e.entity_id] = e.label

    seen: set[tuple] = set()
    for i, r in enumerate(relations, start=2):  # 第 1 行是表头
        where = f"relations.csv 第 {i} 行"
        a, b = labels.get(r["from_entity_id"]), labels.get(r["to_entity_id"])
        if a is None or b is None:
            errors.append(f"{where}：端点实体不存在")
            continue
        if (a, b) != (r["from_label"], r["to_label"]):
            errors.append(f"{where}：from_label/to_label 与实体标签不符")
        if not wl.allows(r["type"], a, b):
            errors.append(f"{where}：{a} -{r['type']}-> {b} 不在白名单")
        if r["verification_status"] not in VERIFICATION_STATUSES:
            errors.append(f"{where}：verification_status 非法")
        ev = split_ids(r["evidence_chunk_ids"])
        if not ev:
            errors.append(f"{where}：缺少 evidence_chunk_ids")
        if unknown := [c for c in ev if c not in chunk_ids]:
            errors.append(f"{where}：证据块不存在 {unknown}")
        if r["verification_status"] == "verified" and not (r["verified_by"] and r["verified_at"]):
            errors.append(f"{where}：verified 的关系必须填写 verified_by 与 verified_at")
        key = (r["from_entity_id"], r["type"], r["to_entity_id"], r["major_code"], r["entry_year"])
        if key in seen:
            errors.append(f"{where}：关系重复")
        seen.add(key)
    return errors


def split_ids(value: str) -> list[str]:
    return [x for x in (value or "").replace("|", ";").split(";") if x.strip()]


def _read_csv(path: Path, columns: list[str]) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != columns:
            raise BundleError(f"{path.name} 表头与契约不一致：{reader.fieldnames}")
        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def _read_jsonl(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, start=1):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise BundleError(f"{path.name} 第 {n} 行不是合法 JSON: {exc}") from exc
    return out

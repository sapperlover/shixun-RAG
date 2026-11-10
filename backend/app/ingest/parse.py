"""文档解析（V1.2 §4.1）。

输入：上传文件路径。只接受 PDF / DOCX / TXT，大小上限见 settings.ingest。
输出：按页的纯文本 [(page_no, text)]。扫描版 PDF 无可提取文字 → 抛出解析失败及定位信息（P0 不做 OCR）。

PDF 使用 pypdf，DOCX 使用 python-docx；扫描件使用独立离线 OCR 产物。
"""

from __future__ import annotations

from pathlib import Path


def parse(path: Path) -> list[tuple[int, str]]:
    path = Path(path)
    from app.core.config import get_settings

    cfg = get_settings().ingest
    extension = path.suffix.lower().lstrip(".")
    if extension not in cfg.allowed_extensions:
        raise ValueError(f"Unsupported file extension: {path.suffix}")
    if path.stat().st_size > cfg.max_upload_mb * 1024 * 1024:
        raise ValueError(f"File exceeds {cfg.max_upload_mb} MB: {path.name}")
    if extension == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        pages = [
            (i, p.extract_text(extraction_mode="layout") or "")
            for i, p in enumerate(reader.pages, 1)
        ]
        if not any(text.strip() for _, text in pages):
            raise ValueError(f"No PDF text: {path.name}; run offline OCR and review its output")
        return pages
    if extension == "docx":
        from docx import Document

        document = Document(path)
        # DOCX has no stable physical pages. page_no=0 is translated to None by split().
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        parts = []
        for element in document.element.body:
            if element.tag.endswith("}p"):
                parts.append(Paragraph(element, document).text)
            elif element.tag.endswith("}tbl"):
                table = Table(element, document)
                parts.append("\n".join(" | ".join(c.text for c in r.cells) for r in table.rows))
        return [(0, "\n".join(parts))]
    return [(0, path.read_text(encoding="utf-8-sig"))]

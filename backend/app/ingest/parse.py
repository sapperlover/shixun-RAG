"""文档解析（文档-2 §4.2(1) 第 1 步；V1.2 §4.1）。

输入：上传文件路径。只接受 PDF / DOCX / TXT，大小上限见 settings.ingest。
输出：按页的纯文本 [(page_no, text)]。扫描版 PDF 无可提取文字 → 抛出解析失败及定位信息（P0 不做 OCR）。

TODO(Data, D2)：PyMuPDF / python-docx 实现。
"""

from __future__ import annotations

from pathlib import Path


def parse(path: Path) -> list[tuple[int, str]]:
    raise NotImplementedError

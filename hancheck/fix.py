"""安全修复。

「安全」的定义很窄：只重写本项目能百分百确定语义的字符。
凡是可能承载业务含义的（比如字符串里的中文标点），一律只报告不修改。
"""

from __future__ import annotations

import os
from typing import Dict, List, Sequence, Tuple

from .rules import Finding
from .scanner import SourceFile

Edit = Tuple[int, int, str]


def collect(findings: Sequence[Finding]) -> List[Edit]:
    edits: List[Edit] = []
    for f in findings:
        if f.edit is None:
            continue
        offset, length, replacement = f.edit
        if replacement is None:
            replacement = ""
        edits.append((offset, length, replacement))
    # 去重：同一位置可能被多条规则命中
    seen = set()
    unique: List[Edit] = []
    for e in edits:
        if e[0] in seen:
            continue
        seen.add(e[0])
        unique.append(e)
    return unique


def apply_text(text: str, edits: Sequence[Edit]) -> str:
    for offset, length, replacement in sorted(edits, key=lambda e: -e[0]):
        text = text[:offset] + replacement + text[offset + length :]
    return text


def rewrite(path: str, text: str) -> None:
    """原子写入，避免中途失败留下半个文件。"""
    tmp = path + ".hancheck.tmp"
    with open(tmp, "wb") as fh:
        fh.write(text.encode("utf-8"))
    os.replace(tmp, path)


def fix_sources(sources: Sequence[SourceFile]) -> Dict[str, int]:
    """执行修复，返回 {相对路径: 修复条数}。"""
    report: Dict[str, int] = {}
    for source in sources:
        edits = collect(source.findings)
        needs_reencode = source.encoding.lower() in ("gb18030", "gbk", "gb2312") or any(
            f.rule == "CN005" for f in source.findings
        )
        if not edits and not needs_reencode:
            continue
        new_text = apply_text(source.text, edits)
        if new_text == source.text and not needs_reencode:
            continue
        rewrite(source.abspath, new_text)
        report[source.display] = len(edits) or 1
    return report

"""文件发现与编码判定。

编码判定是这个工具里最容易误判的一环，所以策略写得很保守：
只有 UTF-8 严格解码失败、且 GB18030 能完整解码时，才断定「这是 GBK 文件」。
绝不做启发式的字符频率猜测。
"""

from __future__ import annotations

import codecs
import os
import subprocess
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Sequence

from .lexer import Lang, get_lang
from .rules import ERROR, WARNING, Finding, RuleMeta

MAX_BYTES = 2 * 1024 * 1024

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "target",
    "vendor",
    ".next",
    ".nuxt",
    ".idea",
    ".vscode",
    "coverage",
    "htmlcov",
}


@dataclass
class SourceFile:
    display: str
    abspath: str
    text: str
    lang: Lang
    encoding: str = "utf-8"
    findings: List[Finding] = field(default_factory=list)


def _git_files(root: str) -> Optional[List[str]]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "-c", "-o", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    items = [p for p in out.stdout.decode("utf-8", "surrogateescape").split("\0") if p]
    return items or None


def _walk(root: str) -> List[str]:
    found: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return found


def discover(targets: Sequence[str]) -> List[tuple[str, str]]:
    """返回 [(展示路径, 绝对路径)]，路径去重并保持稳定顺序。"""
    result: List[tuple[str, str]] = []
    seen: set[str] = set()

    for target in targets:
        abspath = os.path.abspath(target)
        if os.path.isfile(abspath):
            key = os.path.normcase(abspath)
            if key not in seen:
                seen.add(key)
                result.append((target, abspath))
            continue

        if not os.path.isdir(abspath):
            continue

        rels = _git_files(abspath) or _walk(abspath)
        for rel in sorted(rels):
            full = os.path.join(abspath, rel)
            key = os.path.normcase(os.path.abspath(full))
            if key in seen or not os.path.isfile(full):
                continue
            seen.add(key)
            shown = os.path.join(target, rel) if target not in (".", "") else rel
            result.append((os.path.normpath(shown).replace("\\", "/"), full))

    return result


def _encoding_findings(path: str, encoding: str, has_bom: bool) -> List[Finding]:
    out: List[Finding] = []
    if encoding.lower() in ("gb18030", "gbk", "gb2312"):
        out.append(
            Finding(
                rule="CN005",
                severity=ERROR,
                path=path,
                line=1,
                col=1,
                message="文件为 GBK/GB18030 编码，在 Linux / Docker / CI 环境中会乱码",
                fixable=True,
            )
        )
    elif has_bom:
        out.append(
            Finding(
                rule="CN005",
                severity=WARNING,
                path=path,
                line=1,
                col=1,
                message="文件带 UTF-8 BOM，部分解析器（如 JSON、Shebang 脚本）会报错",
                fixable=True,
            )
        )
    return out


def load(path: str, abspath: str) -> Optional[SourceFile]:
    """读取并解码文件；二进制或超大文件返回 None。"""
    lang = get_lang(abspath)
    if lang is None:
        return None

    try:
        size = os.path.getsize(abspath)
        if size > MAX_BYTES or size == 0:
            return None
        with open(abspath, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None

    if b"\x00" in raw[:8192]:
        return None

    has_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw.decode("utf-8-sig")
        encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            text = raw.decode("gb18030")
            encoding = "gb18030"
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            encoding = "utf-8"

    return SourceFile(
        display=path,
        abspath=abspath,
        text=text,
        lang=lang,
        encoding=encoding,
        findings=_encoding_findings(path, encoding, has_bom),
    )


def load_ignore(dirs: Sequence[str]) -> List[str]:
    """读取各目录下的 .hancheckignore（一行一个 glob，# 开头为注释）。"""
    patterns: List[str] = []
    seen = set()
    for d in dirs:
        path = os.path.join(d, ".hancheckignore")
        if not os.path.isfile(path):
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except OSError:
            continue
    return patterns


def matches(path: str, patterns: Sequence[str]) -> bool:
    import fnmatch

    norm = path.replace("\\", "/")
    for raw in patterns:
        pat = raw.replace("\\", "/").strip()
        if pat.endswith("/"):
            pat += "**"
        if (
            fnmatch.fnmatch(norm, pat)
            or fnmatch.fnmatch("/" + norm, pat)
            or fnmatch.fnmatch(os.path.basename(norm), pat)
        ):
            return True
        # 目录前缀形式：docs/ 或 docs/**
        prefix = pat.rstrip("*").rstrip("/")
        if prefix and norm.startswith(prefix + "/"):
            return True
    return False


def iter_sources(targets: Sequence[str], excludes: Sequence[str] = ()) -> Iterator[SourceFile]:
    dirs = ["."] + [t for t in targets if os.path.isdir(t)]
    patterns = list(excludes) + load_ignore(dirs)

    for display, abspath in discover(targets):
        if patterns and matches(display, patterns):
            continue
        source = load(display, abspath)
        if source is not None:
            yield source

"""极轻量的区域切分器（lexer）。

为什么不用 tree-sitter / ast：
1. 需要同时覆盖十几种语言，而我们要判断的东西只有一类——「这个字符落在
   代码结构里，还是落在字符串/注释里」。
2. 只要这个二分类准确，全角标点、全角空格、零宽字符的错误判定就都成立，
   而且对语法错误的半成品文件也不敏感（AST 解析器遇到坏文件会直接崩）。

因此这里用统一的状态机，按注释符与字符串定界符切出 CODE / STRING / COMMENT /
PROSE 四种区域。它不追求 100% 的语法精确，但足以支撑规则判定。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

CODE = "code"
STRING = "string"
COMMENT = "comment"
PROSE = "prose"

# 这些围栏标记表示「示例输出/纯文本」，不该按代码检查
NON_CODE_FENCES = {
    "",
    "text",
    "txt",
    "plaintext",
    "console",
    "terminal",
    "shell-session",
    "output",
    "log",
    "diff",
    "patch",
    "http",
    "csv",
    "mermaid",
}


@dataclass(frozen=True)
class Span:
    """一段具有统一语义的区域，使用半开区间 [start, end)。"""

    kind: str
    start: int
    end: int


@dataclass(frozen=True)
class Delim:
    start: str
    end: str
    kind: str
    escapes: bool = False


@dataclass
class Lang:
    name: str
    delims: List[Delim] = field(default_factory=list)
    # 是否把 CJK 标识符视为风险（强类型/静态语言更值得提示）
    cjk_identifiers: bool = True
    # 是否按「散文」处理（Markdown 正文等），只检查围栏代码块
    prose: bool = False
    # 围栏代码块的标记
    fences: Sequence[str] = ("```",)
    # 全角标点的定级。YAML/TOML/HTML 这类允许裸标量的格式里，
    # 中文标点出现在值是合法的，只能降为 info
    punct_severity: str = "error"


def _c(*pairs) -> List[Delim]:
    return [Delim(s, e, COMMENT) for s, e in pairs]


def _s(*pairs) -> List[Delim]:
    return [Delim(s, e, STRING, escapes=True) for s, e in pairs]


def _lang(name: str, delims: List[Delim], **kw) -> Lang:
    return Lang(name=name, delims=delims, **kw)


_HASH = _c(("#", "\n"))
_SLASH = _c(("//", "\n"))
_CBLOCK = _c(("/*", "*/"))

LANGS: Dict[str, Lang] = {    ".py": _lang("python", _HASH + _s(('"""', '"""'), ("'''", "'''"), ('"', '"'), ("'", "'"))),
    ".pyi": _lang("python", _HASH + _s(('"""', '"""'), ("'''", "'''"), ('"', '"'), ("'", "'"))),
    ".js": _lang("javascript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".jsx": _lang("javascript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".mjs": _lang("javascript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".cjs": _lang("javascript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".ts": _lang("typescript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".tsx": _lang("typescript", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"), ("`", "`"))),
    ".go": _lang("go", _SLASH + _CBLOCK + _s(('"', '"'), ("`", "`"))),
    ".rs": _lang("rust", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".java": _lang("java", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".kt": _lang("kotlin", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".c": _lang("c", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".h": _lang("c", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".cpp": _lang("cpp", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".hpp": _lang("cpp", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".cs": _lang("csharp", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".php": _lang("php", _SLASH + _HASH + _CBLOCK + _s(('"', '"'), ("'", "'"))),
    ".rb": _lang("ruby", _HASH + _s(('"', '"'), ("'", "'"))),
    ".swift": _lang("swift", _SLASH + _CBLOCK + _s(('"', '"'))),
    ".sh": _lang("shell", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".bash": _lang("shell", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".zsh": _lang("shell", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".ps1": _lang("powershell", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".sql": _lang("sql", _c(("--", "\n")) + _CBLOCK + _s(("'", "'"), ('"', '"')), cjk_identifiers=False),
    ".json": _lang("json", _s(('"', '"')), cjk_identifiers=False),
    ".jsonc": _lang("json", _SLASH + _CBLOCK + _s(('"', '"')), cjk_identifiers=False),
    ".yaml": _lang("yaml", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".yml": _lang("yaml", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".toml": _lang("toml", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".ini": _lang("ini", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".cfg": _lang("ini", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".env": _lang("dotenv", _HASH + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".html": _lang("html", _c(("<!--", "-->")) + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".htm": _lang("html", _c(("<!--", "-->")) + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".vue": _lang("vue", _c(("<!--", "-->"), ("//", "\n")) + _CBLOCK + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".css": _lang("css", _CBLOCK + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".scss": _lang("scss", _SLASH + _CBLOCK + _s(('"', '"'), ("'", "'")), cjk_identifiers=False),
    ".md": _lang("markdown", [], prose=True),
    ".markdown": _lang("markdown", [], prose=True),
    ".mdx": _lang("markdown", [], prose=True),
    ".rst": _lang("rst", [], prose=True),
    ".txt": _lang("text", [], prose=True),
}

# 这些格式允许裸标量/正文直接出现中文标点（YAML 的 description、HTML 的文本节点），
# 全角标点在值是合法的，只能降为 info，否则整份配置会被误报
_RELAXED_EXTS = {
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".html",
    ".htm",
    ".vue",
    ".css",
    ".scss",
    ".md",
    ".markdown",
    ".mdx",
    ".rst",
    ".txt",
}
for _ext in _RELAXED_EXTS:
    if _ext in LANGS:
        LANGS[_ext].punct_severity = "info"

# Markdown 围栏语言标记 -> 用于二次切分的扩展名
TAG_LANGS = {
    "py": ".py",
    "python": ".py",
    "python3": ".py",
    "js": ".js",
    "javascript": ".js",
    "mjs": ".js",
    "ts": ".ts",
    "typescript": ".ts",
    "tsx": ".tsx",
    "jsx": ".jsx",
    "json": ".json",
    "jsonc": ".jsonc",
    "yaml": ".yaml",
    "yml": ".yaml",
    "toml": ".toml",
    "ini": ".ini",
    "env": ".env",
    "sh": ".sh",
    "bash": ".sh",
    "shell": ".sh",
    "zsh": ".sh",
    "ps1": ".ps1",
    "powershell": ".ps1",
    "go": ".go",
    "rust": ".rs",
    "rs": ".rs",
    "java": ".java",
    "kotlin": ".kt",
    "kt": ".kt",
    "c": ".c",
    "cpp": ".cpp",
    "c++": ".cpp",
    "cs": ".cs",
    "csharp": ".cs",
    "rb": ".rb",
    "ruby": ".rb",
    "php": ".php",
    "swift": ".swift",
    "sql": ".sql",
    "html": ".html",
    "css": ".css",
    "scss": ".scss",
    "vue": ".vue",
}

# 无扩展名但有意义的文件名 -> 复用哪个语言定义
NAME_LANGS = {
    "Dockerfile": ".sh",
    "Makefile": ".sh",
    ".editorconfig": ".ini",
    ".gitignore": ".txt",
    ".gitattributes": ".txt",
}


def get_lang(path: str) -> Lang | None:
    """按路径返回语言定义；不认识的扩展名返回 None（跳过）。"""
    import os

    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    if ext in LANGS:
        return LANGS[ext]
    if base in NAME_LANGS:
        return LANGS.get(NAME_LANGS[base])
    return None


def _fenced_spans(text: str, fences: Sequence[str]) -> List[Span]:
    """Markdown：围栏代码块内部算 CODE，其余算 PROSE。

    围栏的语言标记会被读取：`text` / `console` / `diff` 这类标记表示
    「这是示例输出，不是代码」，按 PROSE 处理，否则 README 里的终端截图
    会被自己报一堆错。
    """
    blocks: List[tuple] = []  # (kind, start, end, tag)
    lines = text.splitlines(keepends=True)
    offset = 0
    inside = False
    block_start = 0
    block_kind = CODE
    tag = ""

    for line in lines:
        stripped = line.lstrip()
        marker = next((f for f in fences if stripped.startswith(f)), None)
        if marker is not None:
            info = stripped[len(marker) :].strip()
            if not inside:
                inside = True
                tag = info.split()[0].lower().strip("{}.,") if info else ""
                block_kind = PROSE if tag in NON_CODE_FENCES else CODE
                block_start = offset + len(line)
            elif not info:
                blocks.append((block_kind, block_start, offset, tag))
                inside = False
                block_start = offset + len(line)
        offset += len(line)

    if inside:
        # 未闭合的围栏，按声明类型处理到文末
        blocks.append((block_kind, block_start, len(text), tag))

    spans: List[Span] = []
    cursor = 0
    for kind, start, end, block_tag in blocks:
        if start > cursor:
            spans.append(Span(PROSE, cursor, start))
        if kind == CODE and block_tag in TAG_LANGS:
            # 围栏内再用声明的语言切一次，否则 bash 块里的 # 注释会被当成代码
            inner = get_lang("x" + TAG_LANGS[block_tag])
            if inner is not None and not inner.prose:
                for sub in tokenize(text[start:end], inner):
                    spans.append(Span(sub.kind, start + sub.start, start + sub.end))
            else:
                spans.append(Span(CODE, start, end))
        else:
            spans.append(Span(kind, start, end))
        cursor = end

    if cursor < len(text):
        spans.append(Span(PROSE, cursor, len(text)))
    if not spans:
        spans.append(Span(PROSE, 0, len(text)))
    return spans


def tokenize(text: str, lang: Lang) -> List[Span]:
    """把文本切成 CODE / STRING / COMMENT（或 PROSE）区域，保证连续且无重叠。"""
    if lang.prose:
        return _fenced_spans(text, lang.fences)

    delims = sorted(lang.delims, key=lambda d: -len(d.start))
    if not delims:
        return [Span(CODE, 0, len(text))]

    spans: List[Span] = []
    n = len(text)
    i = 0
    code_start = 0

    while i < n:
        matched = None
        for d in delims:
            if text.startswith(d.start, i):
                matched = d
                break
        if matched is None:
            i += 1
            continue

        if code_start < i:
            spans.append(Span(CODE, code_start, i))

        j = i + len(matched.start)
        while j < n:
            if matched.escapes and text[j] == "\\":
                j += 2
                continue
            if text.startswith(matched.end, j):
                j += len(matched.end)
                break
            j += 1
        j = min(j, n)

        spans.append(Span(matched.kind, i, j))
        i = j
        code_start = i

    if code_start < n:
        spans.append(Span(CODE, code_start, n))
    return spans


class LineIndex:
    """偏移量 -> (行号, 列号) 的快速换算。"""

    def __init__(self, text: str) -> None:
        import bisect

        self._bisect = bisect.bisect_right
        starts = [0]
        for idx, ch in enumerate(text):
            if ch == "\n":
                starts.append(idx + 1)
        self._starts = starts

    def at(self, offset: int) -> tuple[int, int]:
        line = self._bisect(self._starts, offset)
        return line, offset - self._starts[line - 1] + 1

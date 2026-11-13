"""规则定义。

每条规则都必须满足三个条件才会被收进来：
1. 只在中文（CJK）语境下发生，英文项目基本不会踩到；
2. 有明确的判定依据，不做「感觉不太对」式的模糊提示；
3. 误报代价极低，或者能给出可直接执行的修复建议。

当前共 12 条规则。规则编号一旦发布就不再改变语义，只允许新增。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .lexer import CODE, PROSE, STRING, Lang, LineIndex, Span, tokenize

ERROR = "error"
WARNING = "warning"
INFO = "info"

SEVERITY_ORDER = {INFO: 0, WARNING: 1, ERROR: 2}


# --------------------------------------------------------------------------- #
# 规则元数据
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RuleMeta:
    code: str
    title: str
    severity: str
    why: str


RULES: Dict[str, RuleMeta] = {
    "CN001": RuleMeta(
        "CN001",
        "代码结构中出现全角标点",
        ERROR,
        "全角逗号、括号、冒号不是合法语法符号，解析器会直接报错；"
        "在 JSON/YAML 中还会导致配置文件无法加载。",
    ),
    "CN002": RuleMeta(
        "CN002",
        "字符串中出现不成对的中文引号",
        WARNING,
        "成对使用的中文引号（如文案里的“引号”）是正常写法；"
        "不成对出现几乎都是从 AI 输出或网页复制时半角/全角混用造成的，"
        "会让字符串提前结束或静默匹配失败。",
    ),
    "CN003": RuleMeta(
        "CN003",
        "全角空格 / 不换行空格充当缩进",
        ERROR,
        "U+3000 与 U+00A0 在编辑器里看起来和普通空格一样，"
        "Python 会报 IndentationError，Shell 会把命令名拆错。",
    ),
    "CN004": RuleMeta(
        "CN004",
        "零宽字符",
        ERROR,
        "从网页、聊天工具或 AI 输出里复制代码时常带入，肉眼完全不可见，"
        "会导致标识符不相等、正则不匹配、编译报错但定位不到。",
    ),
    "CN005": RuleMeta(
        "CN005",
        "文件编码不是 UTF-8",
        ERROR,
        "GBK/GB18030 文件在 Linux CI、Docker 与 macOS 上会变成乱码或直接抛异常，"
        "属于典型的「本地能跑，服务器报错」。",
    ),
    "CN006": RuleMeta(
        "CN006",
        "硬编码中国大陆手机号",
        WARNING,
        "测试数据里写真实手机号会触发《个人信息保护法》合规风险，"
        "也可能在日志、截图中泄露。",
    ),
    "CN007": RuleMeta(
        "CN007",
        "硬编码身份证号",
        ERROR,
        "身份证号属于敏感个人信息，入库/入仓前必须脱敏。"
        "本工具会用国标校验位算法确认是否是真号。",
    ),
    "CN008": RuleMeta(
        "CN008",
        "疑似银行卡号",
        WARNING,
        "通过与银行卡号一致的 Luhn 校验，识别可能泄露的卡号。"
        "长数字串有约 10% 概率通过校验，因此定为 warning。",
    ),
    "CN009": RuleMeta(
        "CN009",
        "源码中引用中文路径",
        WARNING,
        "中文文件名在 Windows 与 Linux 间迁移时容易因编码不一致失效，"
        "打包、Docker 构建失败也常源于此。",
    ),
    "CN010": RuleMeta(
        "CN010",
        "标识符包含中文字符",
        INFO,
        "Python/JS 允许中文变量名，但会让 grep、代码搜索、第三方工具与国际化协作失效。",
    ),
    "CN011": RuleMeta(
        "CN011",
        "代码结构中出现全角数字/字母",
        WARNING,
        "０１２ ＡＢＣ 与 ASCII 字符视觉几乎一致，作为数字参与运算会抛异常，"
        "作为标识符则无法与正常符号互操作。",
    ),
    "CN012": RuleMeta(
        "CN012",
        "存在乱码替换字符",
        ERROR,
        "出现 U+FFFD 说明文本在某个环节被错误解码，原始字符已永久丢失，只能人工修复。",
    ),
}


# --------------------------------------------------------------------------- #
# 字符表
# --------------------------------------------------------------------------- #
# 全角标点 -> 半角。仅收录语义明确、可安全自动替换的映射。
FULLWIDTH_PUNCT: Dict[str, str] = {
    "，": ",",
    "。": ".",
    "、": ",",
    "；": ";",
    "：": ":",
    "？": "?",
    "！": "!",
    "（": "(",
    "）": ")",
    "【": "[",
    "】": "]",
    "《": "<",
    "》": ">",
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "「": '"',
    "」": '"',
    "『": '"',
    "』": '"',
    "～": "~",
    "－": "-",
    "％": "%",
    "＃": "#",
    "＠": "@",
    "＆": "&",
    "＊": "*",
    "＋": "+",
    "＝": "=",
    "／": "/",
    "＼": "\\",
    "｜": "|",
    "＜": "<",
    "＞": ">",
    "＿": "_",
}

# 无法安全自动替换的全角符号（只报告，不修复）
MANUAL_PUNCT = {"…", "—", "·", "￥", "‰", "℃", "±", "×", "÷"}

ZERO_WIDTH = {
    "\u200b": "ZWSP 零宽空格",
    "\u200c": "ZWNJ 零宽不连字",
    "\u200d": "ZWJ 零宽连字",
    "\u2060": "WJ 断词符",
    "\u00ad": "软连字符",
    "\ufeff": "BOM / 零宽不换行空格",
}

FULLWIDTH_SPACE = "\u3000"
NBSP = "\u00a0"
REPLACEMENT = "\ufffd"

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
QUOTE_CHARS = set("“”‘’「」『』")
QUOTE_OPEN = {"“": "”", "‘": "’", "「": "」", "『": "』"}
QUOTE_CLOSE = {v: k for k, v in QUOTE_OPEN.items()}

# 中文路径：必须长得确实像路径，否则中文正文里的「A/B 测试」会被误判
_PATH_SEP = r"[^\s\"'，。；：、（）【】《》？！“”‘’]+"
PATH_PREFIX_RE = re.compile(
    r"(?:\.{1,2}/|~/|[A-Za-z]:[\\/]|\\\\)" + _PATH_SEP
)
FILE_EXT_RE = re.compile(
    r"[^\s\"'，。；：、（）【】《》？！“”‘’/\\]{1,60}[\u4e00-\u9fff]"
    r"[^\s\"'，。；：、（）【】《》？！“”‘’/\\]{0,60}\."
    r"(?:py|pyi|js|jsx|ts|tsx|mjs|cjs|json|jsonc|ya?ml|toml|ini|cfg|env|md|mdx|txt|csv|tsv"
    r"|xlsx?|docx?|pptx?|png|jpe?g|gif|svg|webp|pdf|zip|tar|gz|sh|bat|ps1|exe|dll|so|log"
    r"|db|sqlite3?|xml|html?|css|scss|vue|go|rs|java|kt|swift|c|h|cpp|hpp|cs|rb|php|sql)\b",
    re.IGNORECASE,
)
IDENT_RE = re.compile(r"[A-Za-z_\u3400-\u4dbf\u4e00-\u9fff][\w\u3400-\u4dbf\u4e00-\u9fff]*")

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_RE = re.compile(
    r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
)
CARD_RE = re.compile(r"(?<!\d)\d{16,19}(?!\d)")

# 文档里公开的、众所周知是假的号码，不应报警
FAKE_NUMBERS = {
    "13800138000",
    "13812345678",
    "13912345678",
    "18688888888",
    "18888888888",
    "10000000000",
    "110101199003070000",
}


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    path: str
    line: int
    col: int
    message: str
    snippet: str = ""
    caret: int = 0
    fixable: bool = False
    # (offset, length, replacement). replacement=None 表示删除
    edit: Optional[Tuple[int, int, Optional[str]]] = None


# --------------------------------------------------------------------------- #
# 校验算法
# --------------------------------------------------------------------------- #
def id_checksum_ok(s: str) -> bool:
    """GB 11643-1999 身份证号校验位。"""
    if len(s) != 18:
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    table = "10X98765432"
    try:
        total = sum(int(s[i]) * weights[i] for i in range(17))
    except ValueError:
        return False
    return table[total % 11] == s[17].upper()


def _is_symbolic(s: str) -> bool:
    """整段只有标点或符号（例如引号映射表里的单个条目），属于数据而非文案。"""
    return all(not ch.isalnum() for ch in s)


def _is_fullwidth_alnum(ch: str) -> bool:
    """全角数字与全角字母（U+FF10-FF19 / FF21-FF3A / FF41-FF5A）。"""
    o = ord(ch)
    return 0xFF10 <= o <= 0xFF19 or 0xFF21 <= o <= 0xFF3A or 0xFF41 <= o <= 0xFF5A


def luhn_ok(s: str) -> bool:
    total = 0
    for idx, ch in enumerate(reversed(s)):
        d = int(ch)
        if idx % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _snippet(text: str, offset: int, index: LineIndex, width: int = 100) -> Tuple[str, int]:
    line, col = index.at(offset)
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    raw = text[start:end].rstrip()

    # tab 统一展开为 4 空格，同时把 caret 的字符下标一并换算，否则指示符会错位
    head = raw[: col - 1]
    raw = raw.replace("\t", "    ")
    col = len(head.replace("\t", "    ")) + 1

    if len(raw) > width:
        cut_from = max(0, col - width // 2)
        raw = raw[cut_from : cut_from + width]
        col = col - cut_from
    return raw, max(1, min(col, len(raw) + 1))


def _mk(
    rule: str,
    path: str,
    text: str,
    index: LineIndex,
    offset: int,
    message: str,
    edit: Optional[Tuple[int, int, Optional[str]]] = None,
    severity: Optional[str] = None,
) -> Finding:
    snippet, caret = _snippet(text, offset, index)
    line, col = index.at(offset)
    meta = RULES[rule]
    return Finding(
        rule=rule,
        severity=severity or meta.severity,
        path=path,
        line=line,
        col=col,
        message=message,
        snippet=snippet,
        caret=caret,
        fixable=edit is not None,
        edit=edit,
    )


# --------------------------------------------------------------------------- #
# 主检查流程
# --------------------------------------------------------------------------- #
def check_text(text: str, path: str, lang: Lang) -> List[Finding]:
    """对单个文件内容执行全部文本级规则。"""
    findings: List[Finding] = []
    spans: List[Span] = tokenize(text, lang)
    index = LineIndex(text)

    for span in spans:
        segment = text[span.start : span.end]
        kind = span.kind
        base = span.start

        # ---- CN001 / CN011：只在代码结构区域判定 ----------------------------
        if kind == CODE:
            # 宽松格式（YAML/HTML 等）里的全角标点可能属于正文，只提示不修复
            strict = lang.punct_severity == "error"
            for i, ch in enumerate(segment):
                if ch in FULLWIDTH_PUNCT:
                    findings.append(
                        _mk(
                            "CN001",
                            path,
                            text,
                            index,
                            base + i,
                            f"全角「{ch}」不能作为语法符号使用",
                            edit=(base + i, 1, FULLWIDTH_PUNCT[ch]) if strict else None,
                            severity=lang.punct_severity,
                        )
                    )
                elif ch in MANUAL_PUNCT:
                    findings.append(
                        _mk(
                            "CN001",
                            path,
                            text,
                            index,
                            base + i,
                            f"全角「{ch}」出现在代码结构中，需人工确认",
                            severity=lang.punct_severity,
                        )
                    )
                elif _is_fullwidth_alnum(ch):
                    findings.append(
                        _mk(
                            "CN011",
                            path,
                            text,
                            index,
                            base + i,
                            f"全角字符「{ch}」出现在代码结构中",
                            edit=(base + i, 1, chr(ord(ch) - 0xFEE0)) if strict else None,
                            severity=lang.punct_severity,
                        )
                    )

        # ---- CN002：字符串里不成对的中文引号 -------------------------------
        elif kind == STRING and not _is_symbolic(segment):
            stack: List[Tuple[int, str]] = []
            unmatched: List[Tuple[int, str]] = []
            for i, ch in enumerate(segment):
                if ch in QUOTE_OPEN:
                    stack.append((i, ch))
                elif ch in QUOTE_CLOSE:
                    if stack and QUOTE_OPEN[stack[-1][1]] == ch:
                        stack.pop()
                    else:
                        unmatched.append((i, ch))
            unmatched.extend(stack)
            for i, ch in unmatched:
                findings.append(
                    _mk(
                        "CN002",
                        path,
                        text,
                        index,
                        base + i,
                        f"字符串中出现不成对的中文引号「{ch}」，"
                        "多为半角/全角混用，会导致字符串提前结束",
                    )
                )

        # ---- CN003：不可见空格 ---------------------------------------------
        if kind in (CODE, STRING):
            prev = ""
            i = 0
            while i < len(segment):
                ch = segment[i]
                if ch == FULLWIDTH_SPACE and kind == CODE and prev != FULLWIDTH_SPACE:
                    # 连续全角空格一次性替换，保证 --fix 单次即可收敛
                    run = 1
                    while i + run < len(segment) and segment[i + run] == FULLWIDTH_SPACE:
                        run += 1
                    label = f"连续 {run} 个全角空格" if run > 1 else "全角空格 U+3000"
                    findings.append(
                        _mk(
                            "CN003",
                            path,
                            text,
                            index,
                            base + i,
                            f"{label}出现在代码结构中（常被当作缩进）",
                            edit=(base + i, run, " " * run),
                        )
                    )
                    prev = FULLWIDTH_SPACE
                    i += run
                    continue
                if ch == NBSP and kind == CODE and prev != NBSP:
                    findings.append(
                        _mk(
                            "CN003",
                            path,
                            text,
                            index,
                            base + i,
                            "不换行空格 U+00A0 出现在代码结构中",
                            edit=(base + i, 1, " "),
                        )
                    )
                prev = ch
                i += 1

        # ---- CN004 / CN012：零宽字符与乱码 ---------------------------------
        if kind != PROSE:
            for i, ch in enumerate(segment):
                if ch in ZERO_WIDTH:
                    findings.append(
                        _mk(
                            "CN004",
                            path,
                            text,
                            index,
                            base + i,
                            f"发现不可见字符 {ZERO_WIDTH[ch]}",
                            edit=(base + i, 1, ""),
                        )
                    )
                elif ch == REPLACEMENT:
                    findings.append(
                        _mk(
                            "CN012",
                            path,
                            text,
                            index,
                            base + i,
                            "存在乱码替换字符 U+FFFD，原字符已丢失",
                        )
                    )
        else:
            for i, ch in enumerate(segment):
                if ch == REPLACEMENT:
                    findings.append(
                        _mk(
                            "CN012",
                            path,
                            text,
                            index,
                            base + i,
                            "存在乱码替换字符 U+FFFD，原字符已丢失",
                        )
                    )

        # ---- CN010：中文标识符 ---------------------------------------------
        if kind == CODE and lang.cjk_identifiers:
            for m in IDENT_RE.finditer(segment):
                name = m.group(0)
                if not CJK_RE.search(name):
                    continue
                # 被中文引号包裹的内容其实是「本该是字符串的文本」，
                # 已由 CN001 报告，不应再算作标识符
                before = segment[m.start() - 1] if m.start() > 0 else ""
                after = segment[m.end()] if m.end() < len(segment) else ""
                if before in QUOTE_CHARS or after in QUOTE_CHARS:
                    continue
                findings.append(
                    _mk(
                        "CN010",
                        path,
                        text,
                        index,
                        base + m.start(),
                        f"标识符「{name[:24]}」含中文字符，"
                        "会影响搜索与国际化协作",
                    )
                )

        # ---- CN009：中文路径 -----------------------------------------------
        if kind in (STRING, PROSE):
            seen_offsets: set = set()
            for regex in (PATH_PREFIX_RE, FILE_EXT_RE):
                for m in regex.finditer(segment):
                    token = m.group(0).strip().strip(".,;:")
                    if m.start() in seen_offsets:
                        continue
                    if not CJK_RE.search(token) or len(token) > 160 or len(token) < 3:
                        continue
                    seen_offsets.add(m.start())
                    findings.append(
                        _mk(
                            "CN009",
                            path,
                            text,
                            index,
                            base + m.start(),
                            f"路径「{token[:48]}」含中文，跨平台迁移易失效",
                        )
                    )

    findings.extend(_check_secrets(text, path, index))
    findings.sort(key=lambda f: (f.line, f.col, f.rule))
    return findings


def _check_secrets(text: str, path: str, index: LineIndex) -> List[Finding]:
    out: List[Finding] = []

    for m in PHONE_RE.finditer(text):
        value = m.group(0)
        if value in FAKE_NUMBERS or len(set(value[3:])) == 1:
            continue
        # 位于身份证号内部的连续数字已被 lookaround 排除
        out.append(
            _mk(
                "CN006",
                path,
                text,
                index,
                m.start(),
                f"疑似真实手机号 {value[:3]}****{value[-4:]}，建议替换为 13800138000",
            )
        )

    for m in ID_RE.finditer(text):
        value = m.group(0)
        if value in FAKE_NUMBERS:
            continue
        if id_checksum_ok(value):
            out.append(
                _mk(
                    "CN007",
                    path,
                    text,
                    index,
                    m.start(),
                    f"身份证号 {value[:6]}********{value[-4:]} 校验位正确，属真实格式",
                )
            )
        else:
            out.append(
                Finding(
                    rule="CN007",
                    severity=INFO,
                    path=path,
                    line=index.at(m.start())[0],
                    col=index.at(m.start())[1],
                    message="疑似身份证号，但校验位不通过（可能是随机数字）",
                )
            )

    for m in CARD_RE.finditer(text):
        value = m.group(0)
        if ID_RE.fullmatch(value) or value in FAKE_NUMBERS:
            continue
        if len(set(value)) <= 2:
            continue
        if luhn_ok(value):
            out.append(
                _mk(
                    "CN008",
                    path,
                    text,
                    index,
                    m.start(),
                    f"疑似银行卡号 {value[:4]} **** {value[-4:]}（Luhn 校验通过）",
                )
            )

    return out


def check_file(text: str, path: str, lang: Lang) -> List[Finding]:
    return check_text(text, path, lang)


def summarize(findings: Iterable[Finding]) -> Dict[str, int]:
    counts = {ERROR: 0, WARNING: 0, INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts

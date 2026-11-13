"""结果渲染：终端、JSON、HTML 三种输出。

终端输出是主要门面，所以对齐做了 CJK 宽度修正——中文字符在等宽字体里占两列，
直接用 len() 填充会让 caret 指示符错位。
"""

from __future__ import annotations

import html
import json
from collections import OrderedDict
from typing import Dict, Iterable, List, Sequence

from . import __version__
from .rules import ERROR, INFO, RULES, SEVERITY_ORDER, WARNING, Finding

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[36m"
GREEN = "\033[32m"
GREY = "\033[90m"

SEV_STYLE = {
    ERROR: ("✗", RED, "error"),
    WARNING: ("!", YELLOW, "warning"),
    INFO: ("i", BLUE, "info"),
}


def _is_wide(ch: str) -> bool:
    o = ord(ch)
    return (
        0x1100 <= o <= 0x115F
        or 0x2E80 <= o <= 0xA4CF
        or 0xAC00 <= o <= 0xD7A3
        or 0xF900 <= o <= 0xFAFF
        or 0xFE30 <= o <= 0xFE6F
        or 0xFF00 <= o <= 0xFF60
        or 0xFFE0 <= o <= 0xFFE6
        or 0x20000 <= o <= 0x3FFFD
    )


def display_width(s: str) -> int:
    return sum(2 if _is_wide(ch) else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * max(0, width - display_width(s))


class Painter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def __call__(self, text: str, *codes: str) -> str:
        if not self.enabled or not codes:
            return text
        return "".join(codes) + text + RESET


def group(findings: Iterable[Finding]) -> "OrderedDict[str, List[Finding]]":
    out: "OrderedDict[str, List[Finding]]" = OrderedDict()
    for f in findings:
        out.setdefault(f.path, []).append(f)
    return out


def render_terminal(
    findings: Sequence[Finding],
    files_scanned: int,
    color: bool = True,
    verbose: bool = False,
    max_per_file: int = 20,
) -> str:
    p = Painter(color)
    grouped = group(findings)
    lines: List[str] = []

    lines.append("")
    lines.append(p(f"hancheck {__version__}", BOLD) + p("  面向中文项目的代码体检", GREY))
    lines.append("")

    for path, items in grouped.items():
        lines.append(p(path, BOLD))
        shown = items if verbose else items[:max_per_file]
        for f in shown:
            mark, hue, label = SEV_STYLE[f.severity]
            head = (
                f"  {p(f'{f.line}:{f.col}', GREY)}  "
                f"{p(mark, hue)} {p(f'{label:<7}', hue)} {p(f.rule, GREY)}  {f.message}"
            )
            lines.append(head)
            if f.snippet:
                gutter = f"      {f.line:>5} │ "
                lines.append(p(gutter, GREY) + f.snippet)
                caret_pad = display_width(f.snippet[: max(0, f.caret - 1)])
                lines.append(
                    p(" " * display_width(gutter), GREY)
                    + " " * caret_pad
                    + p("^", hue)
                )
            lines.append("")
        if len(items) > len(shown):
            lines.append(p(f"  … 另有 {len(items) - len(shown)} 项，加 -v 查看全部", GREY))
            lines.append("")

    counts = {ERROR: 0, WARNING: 0, INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    fixable = sum(1 for f in findings if f.fixable)

    rule = "─" * 46
    lines.append(p(rule, GREY))
    if not findings:
        lines.append(
            p("  ✓ ", GREEN, BOLD) + f"扫描 {files_scanned} 个文件，未发现问题。"
        )
    else:
        lines.append(
            "  "
            + p(f"{counts[ERROR]} error", RED, BOLD)
            + p(" · ", GREY)
            + p(f"{counts[WARNING]} warning", YELLOW)
            + p(" · ", GREY)
            + p(f"{counts[INFO]} info", BLUE)
            + p(f"   共 {files_scanned} 个文件", GREY)
        )
        if fixable:
            lines.append(
                p("  ", GREY)
                + p(f"{fixable} 项可自动修复", GREEN)
                + p("，运行 ", GREY)
                + p("hancheck --fix", BOLD)
            )
    lines.append("")
    return "\n".join(lines)


def render_json(findings: Sequence[Finding], files_scanned: int) -> str:
    counts = {ERROR: 0, WARNING: 0, INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    payload = {
        "tool": "hancheck",
        "version": __version__,
        "files_scanned": files_scanned,
        "summary": counts,
        "findings": [
            {
                "rule": f.rule,
                "title": RULES[f.rule].title if f.rule in RULES else "",
                "severity": f.severity,
                "path": f.path,
                "line": f.line,
                "column": f.col,
                "message": f.message,
                "fixable": f.fixable,
            }
            for f in findings
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# HTML 报告：用于截图分享，所以排版按「一屏看懂」来设计
# --------------------------------------------------------------------------- #
def render_html(findings: Sequence[Finding], files_scanned: int, title: str = "hancheck 体检报告") -> str:
    grouped = group(findings)
    counts = {ERROR: 0, WARNING: 0, INFO: 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    fixable = sum(1 for f in findings if f.fixable)

    rows: List[str] = []
    for path, items in grouped.items():
        items_sorted = sorted(items, key=lambda x: (-SEVERITY_ORDER[x.severity], x.line, x.col))
        body: List[str] = []
        for f in items_sorted:
            sev_cls = f.severity
            snippet = html.escape(f.snippet) if f.snippet else ""
            body.append(
                f"""
        <div class="finding {sev_cls}">
          <div class="fhead">
            <span class="badge {sev_cls}">{f.severity}</span>
            <code class="rid">{f.rule}</code>
            <span class="loc">{f.line}:{f.col}</span>
            <span class="msg">{html.escape(f.message)}</span>
            {('<span class="fix">可自动修复</span>' if f.fixable else '')}
          </div>
          {f'<pre class="snip"><code>{snippet}</code></pre>' if snippet else ''}
        </div>"""
            )
        rows.append(
            f"""
      <section class="file">
        <h2><span class="count">{len(items)}</span>{html.escape(path)}</h2>
        {''.join(body)}
      </section>"""
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#ffffff; --line:#e5e7eb; --ink:#111827; --muted:#6b7280;
    --red:#dc2626; --redbg:#fef2f2; --yellow:#b45309; --yellowbg:#fffbeb;
    --blue:#1d4ed8; --bluebg:#eff6ff; --green:#15803d;
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    line-height:1.55; }}
  .wrap {{ max-width: 920px; margin: 0 auto; padding: 40px 24px 64px; }}
  header h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing:-0.01em; }}
  header p {{ margin:0; color:var(--muted); font-size:14px; }}
  .stats {{ display:grid; grid-template-columns: repeat(4,1fr); gap:12px; margin:26px 0 34px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }}
  .stat .n {{ font-size:26px; font-weight:600; font-variant-numeric: tabular-nums; }}
  .stat .l {{ font-size:12px; color:var(--muted); letter-spacing:.04em; text-transform:uppercase; }}
  .stat.e .n {{ color:var(--red); }}
  .stat.w .n {{ color:var(--yellow); }}
  .stat.i .n {{ color:var(--blue); }}
  .stat.f .n {{ color:var(--green); }}
  .file {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
    margin-bottom:18px; overflow:hidden; }}
  .file h2 {{ font-size:14px; font-weight:600; margin:0; padding:14px 18px;
    border-bottom:1px solid var(--line); font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace;
    display:flex; align-items:center; gap:10px; }}
  .count {{ background:#111827; color:#fff; font-size:11px; border-radius:999px;
    padding:2px 8px; font-family:inherit; }}
  .finding {{ padding:12px 18px; border-bottom:1px solid #f1f2f4; }}
  .finding:last-child {{ border-bottom:none; }}
  .finding.error {{ background:var(--redbg); }}
  .finding.warning {{ background:var(--yellowbg); }}
  .finding.info {{ background:var(--bluebg); }}
  .fhead {{ display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; font-size:13.5px; }}
  .badge {{ font-size:11px; font-weight:600; padding:1px 7px; border-radius:4px; color:#fff; }}
  .badge.error {{ background:var(--red); }}
  .badge.warning {{ background:#d97706; }}
  .badge.info {{ background:#2563eb; }}
  .rid {{ font-size:12px; color:var(--muted); }}
  .loc {{ font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .msg {{ flex:1; min-width:220px; }}
  .fix {{ font-size:11px; color:var(--green); border:1px solid #bbf7d0; background:#f0fdf4;
    padding:1px 7px; border-radius:999px; }}
  pre.snip {{ margin:9px 0 0; background:#0f172a; color:#e2e8f0; border-radius:8px;
    padding:10px 12px; overflow-x:auto; font-size:12.5px; line-height:1.5; }}
  pre.snip code {{ font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; }}
  footer {{ margin-top:34px; color:var(--muted); font-size:12px; text-align:center; }}
  @media (max-width:640px) {{ .stats {{ grid-template-columns: repeat(2,1fr); }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{html.escape(title)}</h1>
    <p>扫描 {files_scanned} 个文件 · hancheck v{__version__}</p>
  </header>
  <div class="stats">
    <div class="stat e"><div class="n">{counts[ERROR]}</div><div class="l">error</div></div>
    <div class="stat w"><div class="n">{counts[WARNING]}</div><div class="l">warning</div></div>
    <div class="stat i"><div class="n">{counts[INFO]}</div><div class="l">info</div></div>
    <div class="stat f"><div class="n">{fixable}</div><div class="l">可自动修复</div></div>
  </div>
  {''.join(rows) if rows else '<section class="file"><h2>未发现问题</h2></section>'}
  <footer>由 hancheck 生成 · 面向中文项目的代码体检</footer>
</div>
</body>
</html>
"""

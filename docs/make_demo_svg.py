"""生成 README 用的终端示意图（SVG）。

为什么用脚本而不是截图：规则一改，示例就该跟着变，截图会过期。
运行：python docs/make_demo_svg.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from hancheck.lexer import get_lang  # noqa: E402
from hancheck.report import display_width, render_terminal  # noqa: E402
from hancheck.rules import Finding, check_text  # noqa: E402

ANSI = re.compile(r"\033\[([0-9;]*)m")

COLORS = {
    "31": "#ff7b72",
    "33": "#e3b341",
    "36": "#79c0ff",
    "32": "#7ee787",
    "90": "#6e7681",
    "1": "#f0f6fc",
}

FONT_SIZE = 13.0
ADV = 7.8  # 等宽字体在 13px 下的推进宽度
LINE_H = 20.0
PAD_X = 22.0
HEAD_H = 38.0
PAD_TOP = 26.0


def parse_ansi(line: str):
    """把一行 ANSI 文本切成 [(文本, 颜色)] 段。"""
    runs = []
    color = "#c9d1d9"
    pos = 0
    for m in ANSI.finditer(line):
        if m.start() > pos:
            runs.append((line[pos : m.start()], color))
        codes = [c for c in m.group(1).split(";") if c]
        if not codes or "0" in codes:
            color = "#c9d1d9"
        else:
            for c in codes:
                if c in COLORS:
                    color = COLORS[c]
        pos = m.end()
    if pos < len(line):
        runs.append((line[pos:], color))
    return runs


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(findings, files: int, out_path: str) -> None:
    text = render_terminal(findings, files, color=True, verbose=False)
    lines = text.rstrip("\n").split("\n")

    body = []
    row = 0
    for line in lines:
        runs = parse_ansi(line)
        if not any(t.strip() for t, _ in runs):
            row += 1
            continue
        x = PAD_X
        spans = []
        for chunk, color in runs:
            if not chunk:
                continue
            spans.append(
                f'<tspan x="{x:.1f}" fill="{color}" xml:space="preserve">{esc(chunk)}</tspan>'
            )
            x += sum(2 * ADV if display_width(c) == 2 else ADV for c in chunk)
        body.append(f'<text y="{PAD_TOP + HEAD_H + row * LINE_H:.1f}">{"".join(spans)}</text>')
        row += 1

    max_cols = max(
        (sum(display_width(c) for c in l) for l in lines if l.strip()), default=80
    )
    width = max(680.0, PAD_X * 2 + min(max_cols, 92) * ADV)
    height = PAD_TOP + HEAD_H + row * LINE_H + 18

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}"
     viewBox="0 0 {width:.1f} {height:.1f}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, 'DejaVu Sans Mono', monospace" font-size="{FONT_SIZE}">
  <rect width="100%" height="100%" rx="10" fill="#0d1117"/>
  <path d="M0 10a10 10 0 0 1 10-10h{width - 20:.0f}a10 10 0 0 1 10 10v{HEAD_H - 10:.0f}H0z" fill="#161b22"/>
  <circle cx="22" cy="{HEAD_H / 2:.0f}" r="5.5" fill="#ff5f56"/>
  <circle cx="40" cy="{HEAD_H / 2:.0f}" r="5.5" fill="#ffbd2e"/>
  <circle cx="58" cy="{HEAD_H / 2:.0f}" r="5.5" fill="#27c93f"/>
  <text x="{width / 2:.0f}" y="{HEAD_H / 2 + 4:.0f}" fill="#6e7681" font-size="11.5"
        text-anchor="middle" xml:space="preserve">hancheck .</text>
  <line x1="0" y1="{HEAD_H}" x2="{width:.0f}" y2="{HEAD_H}" stroke="#21262d"/>
  {chr(10).join("  " + b for b in body)}
</svg>
'''
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"written {out_path} ({width:.0f}x{height:.0f}, {row} lines)")


def main() -> None:
    demo = os.path.join(os.path.dirname(__file__), "..", "..", "_demo")
    if not os.path.isdir(demo):
        raise SystemExit("找不到 _demo 示例目录")

    findings = []
    count = 0
    for name in sorted(os.listdir(demo)):
        path = os.path.join(demo, name)
        if not os.path.isfile(path):
            continue
        lang = get_lang(path)
        if lang is None:
            continue
        raw = open(path, "rb").read()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            content = raw.decode("gb18030", errors="replace")
        findings.extend(check_text(content, name, lang))
        count += 1
    findings.sort(key=lambda f: (f.path, f.line, f.col))

    # 截图只保留最具代表性的 5 类问题，避免图太长在 README 首屏放不下
    wanted = ["CN001", "CN003", "CN004", "CN007", "CN008"]
    picked: list[Finding] = []
    for rule in wanted:
        for f in findings:
            if f.rule == rule:
                picked.append(f)
                break
    picked.sort(key=lambda f: (f.path, f.line, f.col))

    build(picked, count, os.path.join(os.path.dirname(__file__), "demo.svg"))


if __name__ == "__main__":
    main()

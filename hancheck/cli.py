"""命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Sequence

from . import __version__
from .fix import fix_sources
from .report import render_html, render_json, render_terminal
from .rules import ERROR, INFO, RULES, SEVERITY_ORDER, WARNING, Finding, check_text
from .scanner import iter_sources

FAIL_LEVELS = {"error": ERROR, "warning": WARNING, "info": INFO, "none": None}


def _split(value: str) -> List[str]:
    return [v.strip().upper() for v in value.replace(" ", ",").split(",") if v.strip()]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hancheck",
        description="面向中文项目的代码体检：扫出全角标点、零宽字符、GBK 编码、"
        "硬编码手机号/身份证号等中文语境专属问题。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  hancheck .                     体检当前项目\n"
            "  hancheck --fix .               自动修复可安全修复的问题\n"
            "  hancheck --html report.html .  生成可分享的 HTML 报告\n"
            "  hancheck --json . > out.json   供 CI 消费\n"
            "  hancheck --fail-level warning  有 warning 即失败\n"
        ),
    )
    p.add_argument("paths", nargs="*", default=[], help="要检查的文件或目录，默认当前目录")
    p.add_argument("--fix", action="store_true", help="自动修复可安全修复的问题")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--html", metavar="FILE", help="生成 HTML 报告到指定文件")
    p.add_argument("--select", metavar="RULES", help="只启用指定规则，如 CN001,CN007")
    p.add_argument("--ignore", metavar="RULES", help="忽略指定规则")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="排除匹配的文件")
    p.add_argument("--fail-level", default="error", choices=list(FAIL_LEVELS), help="退出码阈值，默认 error")
    p.add_argument("--no-color", action="store_true", help="禁用彩色输出")
    p.add_argument("-v", "--verbose", action="store_true", help="显示全部问题（默认每个文件最多 20 条）")
    p.add_argument("-q", "--quiet", action="store_true", help="只输出汇总")
    p.add_argument("--list-rules", action="store_true", help="列出全部规则")
    p.add_argument("--version", action="version", version=f"hancheck {__version__}")
    return p


def _sync_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _list_rules() -> int:
    print()
    print(f"  hancheck {__version__} · 共 {len(RULES)} 条规则")
    print()
    for code in sorted(RULES):
        meta = RULES[code]
        print(f"  {code}  {meta.severity:<8}  {meta.title}")
        print(f"          {meta.why}")
        print()
    return 0


def _filter(findings: Sequence[Finding], select: Sequence[str], ignore: Sequence[str]) -> List[Finding]:
    out = []
    for f in findings:
        if select and f.rule not in select:
            continue
        if ignore and f.rule in ignore:
            continue
        out.append(f)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    _sync_stdout()
    args = build_parser().parse_args(argv)

    if args.list_rules:
        return _list_rules()

    select = _split(args.select) if args.select else []
    ignore = _split(args.ignore) if args.ignore else []

    unknown = [r for r in select + ignore if r not in RULES]
    if unknown:
        print(f"hancheck: 未知规则 {', '.join(unknown)}", file=sys.stderr)
        return 2

    targets = args.paths or ["."]
    sources = list(iter_sources(targets, args.exclude))
    if not sources:
        print("hancheck: 没有找到可检查的文件", file=sys.stderr)
        return 2

    findings: List[Finding] = []
    for source in sources:
        findings.extend(source.findings)
        findings.extend(check_text(source.text, source.display, source.lang))
    findings = _filter(findings, select, ignore)
    findings.sort(key=lambda f: (f.path, f.line, f.col))

    fixed_files: List[str] = []
    fixed_count = 0
    if args.fix:
        to_fix = [s for s in sources if any(f.path == s.display for f in findings)]
        for s in to_fix:
            s.findings = [f for f in findings if f.path == s.display]
        report = fix_sources(to_fix)
        fixed_count = sum(report.values())
        fixed_files = list(report)
        if report:
            # 修复后重新扫描，报告剩余问题
            sources = list(iter_sources(targets, args.exclude))
            findings = []
            for source in sources:
                findings.extend(source.findings)
                findings.extend(check_text(source.text, source.display, source.lang))
            findings = _filter(findings, select, ignore)
            findings.sort(key=lambda f: (f.path, f.line, f.col))

    if args.json:
        print(render_json(findings, len(sources)))
    elif args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(findings, len(sources)))
        color = sys.stdout.isatty() and not args.no_color
        print(render_terminal(findings, len(sources), color=color, verbose=args.verbose))
        print(f"  HTML 报告已写入 {os.path.abspath(args.html)}")
        print()
    elif not args.quiet:
        color = sys.stdout.isatty() and not args.no_color and os.environ.get("NO_COLOR") is None
        if fixed_count:
            print(f"\n  ✓ 已自动修复 {fixed_count} 处，涉及 {len(fixed_files)} 个文件\n")
        print(render_terminal(findings, len(sources), color=color, verbose=args.verbose))

    fail_level = FAIL_LEVELS[args.fail_level]
    if fail_level is None:
        return 0
    threshold = SEVERITY_ORDER[fail_level]
    return 1 if any(SEVERITY_ORDER[f.severity] >= threshold for f in findings) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""规则测试。

重点覆盖三类容易出错的地方：
1. 误报——注释、字符串里的中文标点必须放过；
2. 收敛——--fix 必须一次跑完，不能要求执行两遍；
3. 校验位——身份证与银行卡的算法必须和国标/Luhn 一致。
"""

from __future__ import annotations

from hancheck.fix import apply_text, collect
from hancheck.lexer import get_lang
from hancheck.rules import check_text, id_checksum_ok, luhn_ok
from hancheck.scanner import load


def scan(text: str, ext: str = ".py"):
    lang = get_lang("sample" + ext)
    assert lang is not None
    return check_text(text, "sample" + ext, lang)


def rules_of(findings):
    return [f.rule for f in findings]


# --------------------------------------------------------------------------- #
# CN001 / CN002：标点的区域语义
# --------------------------------------------------------------------------- #
def test_fullwidth_comma_in_code_is_error():
    findings = scan('d = {"a": "b"，"c": 1}\n')
    assert "CN001" in rules_of(findings)


def test_fullwidth_in_comment_is_ignored():
    findings = scan("# 这里用中文标点：逗号、句号、问号，都是正常写作。\n")
    assert "CN001" not in rules_of(findings)


def test_fullwidth_in_string_literal_is_not_syntax_error():
    findings = scan('msg = "你好，世界"\n')
    assert "CN001" not in rules_of(findings)


def test_curly_quotes_in_json_are_error():
    findings = scan('{\n  "name": “张三”\n}\n', ".json")
    assert rules_of(findings).count("CN001") == 2


def test_curly_quote_inside_string_is_warning():
    findings = scan('name = "张三”\n')
    assert "CN002" in rules_of(findings)
    assert "CN001" not in rules_of(findings)


# --------------------------------------------------------------------------- #
# CN003 / CN004：不可见字符
# --------------------------------------------------------------------------- #
def test_fullwidth_space_indent():
    findings = scan("def f():\n\u3000\u3000return 1\n")
    hit = [f for f in findings if f.rule == "CN003"]
    assert len(hit) == 1
    assert hit[0].line == 2


def test_zero_width_space_detected():
    findings = scan("total\u200b = 0\n")
    assert "CN004" in rules_of(findings)


# --------------------------------------------------------------------------- #
# CN005：编码
# --------------------------------------------------------------------------- #
def test_gbk_file_is_detected(tmp_path):
    p = tmp_path / "old.py"
    p.write_bytes("# 旧文件，GBK 编码\n".encode("gbk"))
    src = load("old.py", str(p))
    assert src is not None
    assert src.encoding == "gb18030"
    assert "CN005" in rules_of(src.findings)


def test_utf8_file_is_clean(tmp_path):
    p = tmp_path / "new.py"
    p.write_bytes("# 正常文件\n".encode("utf-8"))
    src = load("new.py", str(p))
    assert src is not None
    assert src.findings == []


# --------------------------------------------------------------------------- #
# CN006 - CN008：敏感信息
# --------------------------------------------------------------------------- #
def test_phone_detected():
    findings = scan('phone = "13900001111"\n')
    assert "CN006" in rules_of(findings)


def test_allowlisted_fake_phone_ignored():
    findings = scan('phone = "13800138000"\n')
    assert "CN006" not in rules_of(findings)


def test_valid_id_card_is_error():
    findings = scan('idcard = "11010519491231002X"\n')
    hit = [f for f in findings if f.rule == "CN007"]
    assert hit and hit[0].severity == "error"


def test_invalid_id_card_is_info():
    findings = scan('idcard = "110105194912310021"\n')
    hit = [f for f in findings if f.rule == "CN007"]
    assert hit and hit[0].severity == "info"


def test_bank_card_luhn():
    findings = scan('card = "6222021234567894"\n')
    assert "CN008" in rules_of(findings)


def test_id_checksum_algorithm():
    assert id_checksum_ok("11010519491231002X")
    assert not id_checksum_ok("110105194912310021")
    assert not id_checksum_ok("12345")


def test_luhn_algorithm():
    assert luhn_ok("4111111111111111")
    assert luhn_ok("6222021234567894")
    assert not luhn_ok("6222021234567890")


# --------------------------------------------------------------------------- #
# CN010：标识符
# --------------------------------------------------------------------------- #
def test_chinese_identifier():
    findings = scan("def 计算总价(items):\n    return 0\n")
    assert "CN010" in rules_of(findings)


def test_chinese_inside_quotes_not_treated_as_identifier():
    findings = scan('x = {"a": “张三”}\n', ".json")
    assert "CN010" not in rules_of(findings)


# --------------------------------------------------------------------------- #
# Markdown：围栏内才检查
# --------------------------------------------------------------------------- #
def test_markdown_prose_ignored_but_fence_checked():
    text = "# 标题\n\n正文中文标点：逗号、句号。\n\n```python\nd = {'a': 'b'，'c': 1}\n```\n"
    findings = scan(text, ".md")
    hits = [f for f in findings if f.rule == "CN001"]
    assert len(hits) == 1
    assert hits[0].line == 6


# --------------------------------------------------------------------------- #
# 修复收敛性
# --------------------------------------------------------------------------- #
def test_fix_converges_in_one_pass():
    text = "def f():\n\u3000\u3000return 1\n"
    findings = scan(text)
    fixed = apply_text(text, collect(findings))
    assert "\u3000" not in fixed
    assert scan(fixed) == []


def test_fix_does_not_touch_comments():
    text = "# 中文，标点。\nx = 1，2\n"
    findings = scan(text)
    fixed = apply_text(text, collect(findings))
    assert "# 中文，标点。" in fixed
    assert "x = 1,2" in fixed


def test_fix_multiple_fullwidth_punct():
    text = 'd = {"a": 1，"b": 2}\n'
    findings = scan(text)
    fixed = apply_text(text, collect(findings))
    assert fixed == 'd = {"a": 1,"b": 2}\n'


# --------------------------------------------------------------------------- #
# 宽松格式：YAML / HTML 中的正文标点
# --------------------------------------------------------------------------- #
def test_yaml_description_with_cjk_punct_is_info():
    findings = scan("description: 检查标点、编码与敏感信息\n", ".yaml")
    hits = [f for f in findings if f.rule == "CN001"]
    assert hits and all(f.severity == "info" for f in hits)
    assert not any(f.fixable for f in hits)


def test_python_still_strict_and_fixable():
    findings = scan("d = {'a': 1、'b': 2}\n")
    hits = [f for f in findings if f.rule == "CN001"]
    assert hits and hits[0].severity == "error" and hits[0].fixable


def test_markdown_bash_fence_comment_not_identifier():
    text = "```bash\nhancheck .   # 全量体检\n```\n"
    findings = scan(text, ".md")
    assert "CN010" not in rules_of(findings)


def test_markdown_python_fence_keeps_strict_severity():
    """Markdown 本身宽松，但围栏里的 Python 代码必须按 error 判定。"""
    text = "```python\nd = {'a': 1，'b': 2}\n```\n"
    findings = scan(text, ".md")
    hits = [f for f in findings if f.rule == "CN001"]
    assert hits and hits[0].severity == "error"

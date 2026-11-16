# hancheck

**Catch the bugs only Chinese code has — before you commit.**

[中文文档](README.md) · [PyPI](https://pypi.org/project/hancheck/)

`hancheck` is a zero-dependency Python linter for Chinese-language codebases. It targets one specific class of bugs that English-only tooling never sees, and that AI-generated code produces constantly:

- A full-width comma `，` inside a JSON/JS object — the file simply won't parse.
- Indentation made of `U+3000` ideographic spaces — Python raises `IndentationError` with no visible cause.
- A `U+200B` zero-width space hidden inside an identifier — two "identical" strings stop being equal.
- A file saved as GBK — works on Windows, turns into mojibake in Docker.
- Real phone numbers and ID card numbers hard-coded in test fixtures.

What makes it different from existing CJK typography tools (`zhlint`, `autocorrect`) is that those are **copywriting formatters** — they standardize punctuation in comments and strings and never tell you the code is broken. `hancheck` **only reports what actually breaks**, and it knows the difference:

```python
# Chinese punctuation in a comment is normal writing -> ignored
msg = "你好，世界"        # full-width comma in a string is legal -> ignored
data = {"a": 1，"b": 2}   # full-width comma in code structure -> error
```

That region-awareness is why you can run `hancheck .` on a large Chinese repo and get a handful of real findings instead of hundreds of spacing nits.

## Install

```bash
pip install git+https://github.com/DIUDIU1HAO/hancheck.git
hancheck .
```

Zero dependencies. Python 3.8+.

## Rules

| ID | Severity | Checks |
|----|----------|--------|
| `CN001` | error | Full-width punctuation in code structure |
| `CN002` | warning | Unpaired Chinese quotation marks inside strings |
| `CN003` | error | `U+3000` / `U+00A0` used as indentation |
| `CN004` | error | Zero-width characters |
| `CN005` | error | GBK/GB18030 encoding, or UTF-8 BOM |
| `CN006` | warning | Hard-coded mainland China phone numbers |
| `CN007` | error | Hard-coded ID card numbers (GB 11643 checksum verified) |
| `CN008` | warning | Suspected bank card numbers (Luhn verified) |
| `CN009` | warning | Chinese characters in file paths |
| `CN010` | info | Identifiers containing Chinese characters |
| `CN011` | warning | Full-width digits or letters in code structure |
| `CN012` | error | Replacement character `U+FFFD` |

## Usage

```bash
hancheck .                       # scan
hancheck --fix .                 # safe auto-fix, converges in one pass
hancheck --json .                # machine-readable
hancheck --html report.html .    # shareable report
hancheck --fail-level warning .  # CI gate
```

Exit codes: `0` clean, `1` threshold reached, `2` bad arguments.

GitHub Actions:

```yaml
- run: pip install git+https://github.com/DIUDIU1HAO/hancheck.git && hancheck --fail-level warning .
```

## License

MIT

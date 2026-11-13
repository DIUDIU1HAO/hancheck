# Changelog

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-11-13

首个可用版本。

### 新增

- 12 条规则：`CN001` - `CN012`，覆盖全角标点、全角空格、零宽字符、编码异常、敏感信息、中文路径与中文标识符。
- 区域感知判定：区分代码结构 / 字符串 / 注释 / 正文，注释与文案中的中文标点不报警。
- Markdown 支持：正文按散文处理，仅检查围栏代码块；`text` / `console` / `diff` 等标记的输出块不按代码检查；围栏声明的语言（`bash`、`python` 等）会驱动二次切分，注释不会被误判为标识符。
- 宽松格式分级：YAML / TOML / INI / HTML / CSS 中允许裸标量，全角标点降为 `info` 且不参与自动修复。
- 安全自动修复：`--fix` 仅处理语义确定的字符，一次收敛。
- 三种输出：终端（CJK 宽度对齐）、JSON、自包含 HTML 报告。
- `.hancheckignore` 与 `--exclude` 排除机制。
- 优先使用 `git ls-files` 发现文件，天然遵循 `.gitignore`。
- Agent Skill 封装（`skills/hancheck/`），可被支持 Agent Skills 的客户端直接调用。
- 零第三方依赖，Python 3.8+。

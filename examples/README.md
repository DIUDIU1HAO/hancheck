# 故意写坏的样例

这里的文件**故意包含问题**，用来演示 `hancheck` 能抓到什么。不要模仿，也不要修。

```bash
hancheck --no-ignore examples/
```

预期结果（`examples/config.ts` 与 `examples/demo.py` 两份文件）：

- `CN001` 代码结构里的全角引号与逗号
- `CN002` 字符串里不成对的中文引号
- `CN003` 全角空格被当作缩进（连续 2 个会在一次修复内全部处理）
- `CN004` 零宽空格 `U+200B`
- `CN006` 疑似真实手机号
- `CN010` 中文标识符

想验证自动修复：

```bash
cp -r examples /tmp/hancheck-demo && hancheck --no-ignore --fix /tmp/hancheck-demo
```

修复后再检查一遍，应当只剩需要人工判断的项（手机号怎么脱敏取决于业务，不自动改）。

本目录已在 `.hancheckignore` 中排除，所以仓库自检不会因为这份样例失败；要看效果必须加 `--no-ignore`。

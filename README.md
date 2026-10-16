# handitin

一个轻量级、离线优先的 HTML 问卷/调查工具包。零第三方依赖，仅需 Python 3 标准库。

## 项目结构

```
handitin/
├── main.py           # Python CLI 工具（build / serve / collect）
├── generator.html    # 可视化表单设计器（纯浏览器端）
└── README.md
```

## 快速开始

### 1. 设计表单

在浏览器中打开 `generator.html`，通过可视化界面设计表单：

- 设置标题和副标题
- 添加字段（文本、数字、日期、下拉选择、分隔线）
- 编辑标签和下拉选项
- 拖拽排序字段
- 点击「下载 .frm」导出表单定义文件

### 2. 构建 HTML 表单

```bash
python main.py build form.frm
```

生成独立的 `form.html` 文件，可直接分发给受访者离线填写。

### 3. 收集结果

**方式一：在线收集（局域网）**

```bash
python main.py serve form.frm
```

启动本地 HTTP 服务器（默认 `0.0.0.0:8000`），自动检测局域网 IP 并显示访问地址。受访者通过浏览器提交表单，结果实时追加到 `results.csv`。

**方式二：离线收集**

```bash
python main.py collect
```

受访者填写 `form.html` 后，页面会显示 base64 编码的提交内容。将其复制后粘贴到 `collect` 命令的输入流中，按 `Ctrl-C` 结束，结果写入 `results.csv`。

## .frm 文件格式

`.frm` 是一种简单、人类可读的文本格式，用于定义表单结构：

```
# 注释以 # 开头
title "问卷标题"
title "副标题"

text "请输入文本"
int "请输入数字"
date "请选择日期"

text "请选择一个选项"
- "选项一"
- "选项二"
- "选项三"

---
```

### 语法规则

| 关键字 | 说明 |
|--------|------|
| `title "..."` | 标题行（可多次使用） |
| `text "..."` | 文本输入框 |
| `int "..."` | 数字输入框 |
| `date "..."` | 日期选择器 |
| `text "..."` + `- "..."` | 下拉选择框（`text` 后跟若干 `-` 开头的选项） |
| `---` | 分隔线 |

- 字符串使用双引号包裹，支持转义：`\n`、`\t`、`\"`、`\\`
- `#` 开头的行为注释（引号内的 `#` 不受影响）

## CLI 参考

```
python main.py <command> [options]

命令:
  build <file.frm>     将 .frm 文件编译为独立 HTML 表单
  serve <file.frm>     启动 HTTP 服务器，在线收集提交
  collect              从 stdin 读取 base64 编码数据，写入 CSV

选项:
  --host HOST         服务器绑定地址（默认 0.0.0.0）
  --port PORT         服务器端口（默认 8000）
  --output FILE        CSV 输出文件（默认 results.csv）
```

## 特性

- **零依赖** — 仅使用 Python 3 标准库
- **离线优先** — 生成的 HTML 表单无需网络即可填写
- **双模式收集** — 支持在线（HTTP）和离线（复制粘贴）两种方式
- **可视化设计** — 浏览器端 GUI，无需学习语法
- **实时写入** — 提交结果即时追加到 CSV，无需等待
- **局域网友好** — 自动检测并显示 LAN IP，方便多人访问

## 许可证

MIT

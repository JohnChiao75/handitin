#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
handitin.py — 命令行 HTML 问卷工具

用法:
    handitin.py build   <file.frm>          在当前目录生成离线 HTML 表单
    handitin.py serve   <file.frm>          启动局域网表单服务并监听结果
    handitin.py collect                     从 stdin 收集 base64 结果，Ctrl-C 结束并写入 csv
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import socket
import sys
from dataclasses import dataclass, field as dc_field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse


# --------------------------------------------------------------------------- #
# .frm 解析
# --------------------------------------------------------------------------- #

@dataclass
class Field:
    kind: str                       # text | select | int | date | separator
    label: str = ""
    options: list = dc_field(default_factory=list)


def strip_comment(line: str) -> str:
    """去掉行内注释（# 及之后的内容），但忽略字符串内部的 #。"""
    out, in_str, esc = [], False, False
    for ch in line:
        if esc:
            out.append(ch)
            esc = False
            continue
        if ch == "\\":
            out.append(ch)
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            out.append(ch)
            continue
        if ch == "#" and not in_str:
            break
        out.append(ch)
    return "".join(out)


def tokenize(line: str) -> list:
    """把一行拆成 token，支持双引号字符串（含 \\n \\t \\" \\\\ 转义）。"""
    tokens, i, n = [], 0, len(line)
    escapes = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}
    while i < n:
        c = line[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j, buf = i + 1, []
            while j < n:
                if line[j] == "\\" and j + 1 < n:
                    buf.append(escapes.get(line[j + 1], line[j + 1]))
                    j += 2
                    continue
                if line[j] == '"':
                    break
                buf.append(line[j])
                j += 1
            tokens.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and not line[j].isspace():
                j += 1
            tokens.append(line[i:j])
            i = j
    return tokens


def parse_frm(text: str):
    """返回 (titles, fields)。"""
    titles, fields = [], []
    for raw in text.splitlines():
        line = strip_comment(raw).strip()
        if not line:
            continue
        tokens = tokenize(line)
        if not tokens:
            continue
        head = tokens[0]
        value = tokens[1] if len(tokens) > 1 else ""

        if head == "title":
            titles.append(value)
        elif head == "text":
            fields.append(Field("text", value))
        elif head == "int":
            fields.append(Field("int", value))
        elif head == "date":
            fields.append(Field("date", value))
        elif head == "---":
            fields.append(Field("separator"))
        elif head == "-":
            # 属于上一个字段的选项 —— 把 text 升级成下拉框
            if fields and fields[-1].kind in ("text", "select"):
                fields[-1].kind = "select"
                fields[-1].options.append(value)
            else:
                sys.stderr.write(f"handitin: 警告: 孤立的选项行: {line}\n")
        else:
            sys.stderr.write(f"handitin: 警告: 未知指令: {head}\n")
    return titles, fields


# --------------------------------------------------------------------------- #
# HTML 渲染
# --------------------------------------------------------------------------- #

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #f5f6f8;
  --fg: #1c1e21;
  --muted: #57606a;
  --accent: #2f6feb;
  --border: #d0d7de;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 2rem 1rem 4rem;
  background: var(--bg);
  color: var(--fg);
  font: 16px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
}
main { max-width: 640px; margin: 0 auto; }
h1 { font-size: 1.55rem; margin: 0 0 .4rem; }
h2 { font-size: 1.02rem; font-weight: 500; color: var(--muted); margin: 0 0 1.1rem; }
form {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 1px 3px rgba(0,0,0,.05);
}
.field { margin-bottom: 1rem; }
.field label { display: block; margin-bottom: .35rem; font-weight: 500; }
input, select, button {
  font: inherit;
  width: 100%;
  padding: .55rem .65rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  color: inherit;
}
input:focus, select:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
  border-color: var(--accent);
}
hr { border: 0; border-top: 1px solid var(--border); margin: 1.5rem 0; }
button {
  margin-top: .5rem;
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  cursor: pointer;
  font-weight: 600;
}
button:hover { filter: brightness(1.06); }
#result { margin-top: 1.25rem; display: none; }
#result.show { display: block; }
#result pre {
  white-space: pre-wrap;
  word-break: break-all;
  background: #0d1117;
  color: #c9d1d9;
  padding: .9rem;
  border-radius: 8px;
  margin: 0;
  font-size: .85rem;
}
.hint { font-size: .85rem; color: var(--muted); margin: .5rem 0 0; }
</style>
</head>
<body>
<main>
<h1>__TITLE__</h1>
__SUBTITLES__
<form id="qform" autocomplete="off">
__FIELDS__
<button type="submit">提交</button>
</form>
<div id="result">
<p class="hint" id="hint"></p>
<pre id="payload"></pre>
</div>
</main>
<script>
__SCRIPT__
</script>
</body>
</html>
"""


JS_TEMPLATE = """
const FIELDS = __FIELDS__;
const ENDPOINT = __ENDPOINT__;

var form      = document.getElementById('qform');
var resultBox = document.getElementById('result');
var payloadEl = document.getElementById('payload');
var hintEl    = document.getElementById('hint');

function csvEscape(v) {
  var s = (v === null || v === undefined) ? '' : String(v);
  if (/[",\\r\\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function base64Encode(str) {
  var bytes = new TextEncoder().encode(str);
  var bin = '';
  for (var i = 0; i < bytes.length; i++) {
    bin += String.fromCharCode(bytes[i]);
  }
  return btoa(bin);
}

form.addEventListener('submit', function (ev) {
  ev.preventDefault();

  var row = [];
  FIELDS.forEach(function (f) {
    var el = document.getElementById(f.id);
    var v  = el ? el.value : '';

    if (f.type === 'date' && v) {
      // 日期 -> UNIX 时间戳（秒）
      var t = Date.parse(v + 'T00:00:00Z');
      v = isNaN(t) ? '' : String(Math.floor(t / 1000));
    } else if (f.type === 'int' && v !== '') {
      var n = Number(v);
      v = isFinite(n) ? String(Math.trunc(n)) : '';
    }
    row.push(csvEscape(v));
  });

  var csvLine = row.join(',');
  var encoded = base64Encode(csvLine);

  payloadEl.textContent = encoded;
  resultBox.classList.add('show');

  if (ENDPOINT) {
    fetch(ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'text/plain' },
      body: encoded
    }).then(function () {
      hintEl.textContent = '已提交。编码结果：';
    }).catch(function () {
      hintEl.textContent = '提交失败，请复制下面这行：';
    });
  } else {
    hintEl.textContent = '复制下面这行，然后运行： handitin.py collect';
  }
});
"""


def render_html(titles, fields, endpoint=None) -> str:
    main_title = titles[0] if titles else "Questionnaire"
    subtitles = "\n".join(
        f'<h2>{html.escape(t)}</h2>' for t in titles[1:]
    )

    parts, meta = [], []
    for i, f in enumerate(fields):
        if f.kind == "separator":
            parts.append("  <hr>")
            continue

        fid = f"f{i}"
        meta.append({"id": fid, "type": f.kind})
        label = html.escape(f.label)

        if f.kind == "select":
            opts = ['<option value=""></option>']
            for o in f.options:
                eo = html.escape(o, quote=True)
                opts.append(f'<option value="{eo}">{eo}</option>')
            control = f'<select id="{fid}" name="{fid}">' + "".join(opts) + "</select>"
        elif f.kind == "int":
            control = f'<input type="number" step="1" id="{fid}" name="{fid}">'
        elif f.kind == "date":
            control = f'<input type="date" id="{fid}" name="{fid}">'
        else:
            control = f'<input type="text" id="{fid}" name="{fid}">'

        parts.append(
            f'  <div class="field"><label for="{fid}">{label}</label>{control}</div>'
        )

    script = (JS_TEMPLATE
              .replace("__FIELDS__", json.dumps(meta, ensure_ascii=False))
              .replace("__ENDPOINT__", json.dumps(endpoint)))

    return (PAGE_TEMPLATE
            .replace("__TITLE__", html.escape(main_title))
            .replace("__SUBTITLES__", subtitles)
            .replace("__FIELDS__", "\n".join(parts))
            .replace("__SCRIPT__", script))


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #

def _load(filename: str):
    src = Path(filename)
    if not src.is_file():
        sys.exit(f"handitin: 找不到文件: {src}")
    return parse_frm(src.read_text(encoding="utf-8"))


def _base_name(filename: str) -> str:
    return Path(filename).name.split(".")[0]


def cmd_build(args):
    titles, fields = _load(args.filename)
    page = render_html(titles, fields, endpoint=None)
    out = Path.cwd() / (_base_name(args.filename) + ".html")
    out.write_text(page, encoding="utf-8")
    print(f"已生成: {out}")
    print("用浏览器打开该文件，提交后会显示 base64 编码的一行 CSV。")
    print("把它粘贴给 `handitin.py collect` 即可收集。")


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def cmd_serve(args):
    titles, fields = _load(args.filename)
    page = render_html(titles, fields, endpoint="/submit").encode("utf-8")

    out_path = Path(args.output).expanduser().resolve()
    out_path.touch(exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        server_version = "handitin/1.0"

        def _reply(self, code, body=b"", ctype="text/plain; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path in ("/", "/index.html"):
                self._reply(200, page, "text/html; charset=utf-8")
            else:
                self._reply(404, "not found")

        def do_POST(self):
            if urlparse(self.path).path != "/submit":
                self._reply(404, "not found")
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            raw = self.rfile.read(length).decode("utf-8", "replace").strip()
            if not raw:
                self._reply(400, "empty")
                return

            try:
                line = base64.b64decode(raw, validate=True).decode("utf-8")
            except Exception:
                line = raw

            with out_path.open("a", encoding="utf-8", newline="") as fh:
                fh.write(line.rstrip("\r\n") + "\n")

            sys.stdout.write("[+] " + line + "\n")
            sys.stdout.flush()
            self._reply(200, "ok")

    host, port = args.host, args.port
    try:
        httpd = HTTPServer((host, port), Handler)
    except OSError as exc:
        sys.exit(f"handitin: 无法监听 {host}:{port} — {exc}")

    print(f"表单服务已启动： http://{lan_ip()}:{port}/")
    print(f"结果会实时写入： {out_path}")
    print("按 Ctrl-C 停止。")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止服务。")
    finally:
        httpd.server_close()


def cmd_collect(args):
    out_path = Path(args.output).expanduser().resolve()
    rows = []

    sys.stderr.write("从 stdin 读取结果（粘贴 base64 行，Ctrl-C 结束）...\n")
    sys.stderr.flush()

    try:
        while True:
            line = sys.stdin.readline()
            if not line:                 # EOF (Ctrl-D)
                break
            line = line.strip()
            if not line:
                continue
            try:
                decoded = base64.b64decode(line, validate=True).decode("utf-8")
            except Exception:
                decoded = line             # 容错：原样当 CSV
            rows.append(decoded)
            sys.stderr.write("  + " + decoded + "\n")
            sys.stderr.flush()
    except KeyboardInterrupt:
        sys.stderr.write("\n")

    if not rows:
        sys.stderr.write("没有收集到任何结果。\n")
        return

    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        for r in rows:
            try:
                writer.writerow(next(csv.reader([r])))
            except Exception:
                writer.writerow([r])

    print(f"已写入 {len(rows)} 行到 {out_path}")


# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="handitin.py",
        description="命令行 HTML 问卷工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_build = sub.add_parser("build", help="根据 .frm 生成离线 HTML 表单")
    p_build.add_argument("filename")
    p_build.set_defaults(func=cmd_build)

    p_serve = sub.add_parser("serve", help="启动局域网表单服务并监听结果")
    p_serve.add_argument("filename")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("-p", "--port", type=int, default=8000)
    p_serve.add_argument("-o", "--output", default="results.csv")
    p_serve.set_defaults(func=cmd_serve)

    p_collect = sub.add_parser("collect", help="从 stdin 收集结果并写入 csv")
    p_collect.add_argument("-o", "--output", default="results.csv")
    p_collect.set_defaults(func=cmd_collect)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
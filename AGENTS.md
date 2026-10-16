# AGENTS.md

## Commands

```bash
python main.py build <file.frm>              # Compile .frm → standalone HTML
python main.py serve <file.frm> [--host H] [--port P]  # Start HTTP server
python main.py collect                        # Decode base64 CSV from stdin
```

No build step, no package install, no tests. Python 3 standard library only.

## Architecture

- `main.py` — single-file CLI. Subcommands: `build`, `serve`, `collect`. Entry point is `main()` at the bottom.
- `generator.html` — standalone browser form designer. Outputs `.frm` text. No server, no build.
- `.frm` format — line-based text: `title`, `text`, `int`, `date`, `-` (select options), `---` (separator). Supports `#` comments and quoted strings with escapes.

## Conventions

- CSV output defaults to `results.csv`; override with `--output`.
- `serve` auto-detects LAN IP for display.
- Generated HTML embeds base64-encoded CSV in the page for offline copy-paste via `collect`.
- `.gitignore` excludes generated `*.html` (except `generator.html`) and `*.csv`.

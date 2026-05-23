import re
from pathlib import Path


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(content)


def _build_html(title: str, body_html: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
    }}
    body {{
      max-width: 960px;
      margin: 32px auto;
      padding: 0 20px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
    }}
    h1, h2, h3 {{
      line-height: 1.25;
    }}
    h3 {{
      margin-top: 1.5em;
      font-size: 1.05rem;
      color: #333;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 8px 10px;
      text-align: left;
    }}
    .report-figure-grid {{
      display: grid;
      gap: 18px;
      margin: 12px 0 24px;
      align-items: start;
      justify-items: center;
    }}
    .report-figure-grid-2 {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .report-figure {{
      margin: 0;
      text-align: center;
      width: 100%;
      max-width: 280px;
    }}
    .report-figure figcaption {{
      margin-top: 8px;
      font-size: 0.92rem;
      color: #555;
    }}
    img.report-chart {{
      max-width: min(720px, 100%);
      width: 100%;
      height: auto;
      display: block;
      margin: 8px auto 24px;
      border: 1px solid #e5e5e5;
      border-radius: 6px;
    }}
    h3 + p > img.report-chart,
    h3 + img.report-chart {{
      margin-top: 4px;
    }}
    img.report-chart-compact {{
      max-width: min(260px, 100%);
      margin: 0 auto;
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
    pre {{
      padding: 12px;
      overflow-x: auto;
      background: rgba(0, 0, 0, 0.04);
    }}
    @media (max-width: 760px) {{
      .report-figure-grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
{body_html}
</body>
</html>
"""


def _embed_chart_images(body_html: str) -> str:
    """给 markdown 生成的 <img> 加上样式类，便于 HTML 报告排版。"""
    def _repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        class_match = re.search(r'class="([^"]*)"', tag)
        if not class_match:
            return tag.replace("<img ", '<img class="report-chart" ', 1)
        classes = class_match.group(1).split()
        if "report-chart" in classes:
            return tag
        merged = " ".join(["report-chart", *classes])
        return tag[: class_match.start(1)] + merged + tag[class_match.end(1) :]

    return re.sub(r"<img\b[^>]*>", _repl, body_html)


def render_markdown_to_html(
    markdown_path: str,
    output_path: str | None = None,
) -> str:
    try:
        import markdown  # type: ignore
    except Exception as exc:
        raise ModuleNotFoundError(
            "Missing dependency 'markdown'. Install it in the current environment "
            "(e.g. `python -m pip install markdown`)."
        ) from exc

    input_path = Path(markdown_path).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {input_path}")

    if output_path:
        html_path = Path(output_path).expanduser().resolve()
    else:
        html_path = input_path.with_suffix(input_path.suffix + ".html")

    markdown_text = _read_text(input_path)
    body_html = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html5",
    )
    body_html = _embed_chart_images(body_html)
    html = _build_html(input_path.name, body_html)
    _write_text(html_path, html)
    return str(html_path)


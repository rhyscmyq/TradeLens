from __future__ import annotations

import os
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
      max-width: 980px;
      margin: 32px auto;
      padding: 0 22px 40px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.7;
    }}
    h1, h2, h3, h4 {{
      line-height: 1.25;
    }}
    h2 {{
      margin-top: 1.8em;
      padding-top: 0.2em;
      border-top: 1px solid #e8e8e8;
    }}
    h3 {{
      margin-top: 1.4em;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      margin: 12px 0 18px;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    blockquote {{
      margin: 16px 0;
      padding: 10px 14px;
      border-left: 4px solid #89a7d8;
      background: rgba(137, 167, 216, 0.08);
    }}
    code, pre {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }}
    pre {{
      padding: 12px;
      overflow-x: auto;
      background: rgba(0, 0, 0, 0.04);
    }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin: 12px 0 26px;
      align-items: start;
    }}
    .chart-grid.compact {{
      justify-items: center;
    }}
    .chart-stack {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 16px;
      margin: 12px 0 26px;
    }}
    .chart-item {{
      margin: 0;
      text-align: center;
    }}
    .chart-item img {{
      width: 100%;
      height: auto;
      display: block;
      margin: 0 auto;
      border: 1px solid #e5e5e5;
      border-radius: 8px;
      background: #fff;
    }}
    .chart-grid.compact .chart-item {{
      max-width: 280px;
      width: 100%;
    }}
    .chart-item figcaption {{
      margin-top: 8px;
      font-size: 0.92rem;
      color: #555;
    }}
    @media (max-width: 760px) {{
      .chart-grid {{
        grid-template-columns: 1fr;
      }}
      .chart-grid.compact .chart-item {{
        max-width: none;
      }}
    }}
  </style>
</head>
<body>
{body_html}
</body>
</html>
"""


def _urlize(path: str) -> str:
    return path.replace(os.sep, "/").replace(" ", "%20")


def _infer_report_path(analysis_path: Path) -> Path:
    name = analysis_path.name
    if name.endswith("-llm-analysis.md"):
        return analysis_path.with_name(name.replace("-llm-analysis.md", "-financial-report.md"))
    return analysis_path.with_name(name.replace(".md", "-financial-report.md"))


def _figure_key_from_src(src: str) -> str | None:
    lowered = src.lower()
    if "profit_breakdown_full" in lowered:
        return "profit_full"
    if "profit_breakdown_invested" in lowered:
        return "profit_invested"
    if "cost_pie_no_monthly" in lowered:
        return "cost_pie_no_monthly"
    if "cost_pie" in lowered:
        return "cost_pie"
    if "performance_line_no_monthly" in lowered:
        return "performance_no_monthly"
    if "performance_line" in lowered:
        return "performance"
    return None


def _extract_report_figures(report_path: Path) -> dict[str, tuple[str, str]]:
    if not report_path.exists():
        return {}
    text = _read_text(report_path)
    figures: dict[str, tuple[str, str]] = {}
    for alt, src in re.findall(r"!\[([^\]]+)\]\(([^)]+)\)", text):
        key = _figure_key_from_src(src)
        if key:
            figures[key] = (src, alt)
    return figures


def _resolve_src(source_markdown_path: Path, html_dir: Path, asset_ref: str) -> str:
    asset_path = (source_markdown_path.parent / asset_ref).resolve()
    rel = os.path.relpath(asset_path, html_dir)
    return _urlize(rel)


def _figure_item_html(
    source_markdown_path: Path,
    html_dir: Path,
    asset_ref: str,
    caption: str,
) -> str:
    rel = _resolve_src(source_markdown_path, html_dir, asset_ref)
    return (
        "<figure class=\"chart-item\">"
        f"<img src=\"{rel}\" alt=\"{caption}\" />"
        f"<figcaption>{caption}</figcaption>"
        "</figure>"
    )


def _figure_grid_html(
    source_markdown_path: Path,
    html_dir: Path,
    figures: list[tuple[str, str]],
    *,
    compact: bool = False,
) -> str:
    class_name = "chart-grid compact" if compact else "chart-grid"
    items = [
        _figure_item_html(source_markdown_path, html_dir, asset_ref, caption)
        for asset_ref, caption in figures
    ]
    return f"<div class=\"{class_name}\">" + "".join(items) + "</div>"


def _figure_stack_html(
    source_markdown_path: Path,
    html_dir: Path,
    figures: list[tuple[str, str]],
) -> str:
    items = [
        _figure_item_html(source_markdown_path, html_dir, asset_ref, caption)
        for asset_ref, caption in figures
    ]
    return "<div class=\"chart-stack\">" + "".join(items) + "</div>"


def _insert_after_heading(markdown_text: str, heading: str, block_html: str) -> str:
    lines = markdown_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == heading:
            insert_at = i + 2 if i + 1 < len(lines) else i + 1
            lines.insert(insert_at, "")
            lines.insert(insert_at + 1, block_html)
            lines.insert(insert_at + 2, "")
            break
    return "\n".join(lines) + "\n"


def render_diagnosis_to_html(markdown_path: str, output_path: str | None = None) -> str:
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
    report_path = _infer_report_path(input_path)
    figures = _extract_report_figures(report_path)

    profit_figures = [figures[key] for key in ("profit_full", "profit_invested") if key in figures]
    if profit_figures:
        markdown_text = _insert_after_heading(
            markdown_text,
            "### 1.2 Profit Attribution Analysis",
            _figure_grid_html(report_path, html_path.parent, profit_figures),
        )

    cost_figures = [figures[key] for key in ("cost_pie", "cost_pie_no_monthly") if key in figures]
    if cost_figures:
        markdown_text = _insert_after_heading(
            markdown_text,
            "### 1.3 Cost Structure Analysis",
            _figure_grid_html(report_path, html_path.parent, cost_figures, compact=True),
        )

    timeline_figures = [figures[key] for key in ("performance", "performance_no_monthly") if key in figures]
    if timeline_figures:
        markdown_text = _insert_after_heading(
            markdown_text,
            "### 1.4 Portfolio Timeline and Risk Signals",
            _figure_stack_html(report_path, html_path.parent, timeline_figures),
        )

    body_html = markdown.markdown(
        markdown_text,
        extensions=["tables", "fenced_code", "toc"],
        output_format="html5",
    )
    html = _build_html(input_path.name, body_html)
    _write_text(html_path, html)
    print(f"Saved diagnosis HTML to: {html_path}")
    return str(html_path)


"""族谱 PDF/HTML 导出（浏览器打印为 PDF）"""

from __future__ import annotations

from html import escape
from typing import Any

from .tree import build_family_tree


def generate_genealogy_html(
    family: dict,
    persons: list[dict],
    relations: list[dict],
    *,
    style: str = "su",
) -> str:
    tree = build_family_tree(persons, relations, style=style)
    title = escape(family.get("name") or "族谱")
    nodes_html = _render_nodes(tree.get("roots") or [], 0)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{ font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif; background: #F9F5F0; color: #4A3F35; padding: 24px; }}
  h1 {{ color: #8B6F47; border-bottom: 2px solid #C9A961; padding-bottom: 8px; }}
  .meta {{ color: #8B7B6B; margin-bottom: 20px; }}
  .node {{ margin: 6px 0; padding: 6px 10px; border-left: 3px solid #C9A961; background: #fff; border-radius: 4px; }}
  .depth-0 {{ border-left-color: #8B6F47; font-weight: bold; }}
  @media print {{ body {{ padding: 12px; }} }}
</style>
</head>
<body>
  <h1>{title}</h1>
  <p class="meta">族见导出 · 共 {tree.get("person_count", 0)} 人 · 版式：{style}</p>
  <div class="tree">{nodes_html}</div>
  <script>window.onload = () => window.print()</script>
</body>
</html>"""


def _render_nodes(nodes: list[dict], depth: int) -> str:
    parts = []
    for n in nodes:
        name = escape(n.get("name") or "")
        years = ""
        if n.get("birth_year"):
            years = f"（{n['birth_year']}"
            if n.get("death_year"):
                years += f"-{n['death_year']}"
            years += "）"
        gen = f" 第{n['generation']}代" if n.get("generation") else ""
        ziname = f" 字{escape(n.get('generation_name') or '')}" if n.get("generation_name") else ""
        parts.append(f'<div class="node depth-{depth}" style="margin-left:{depth * 24}px">{name}{ziname}{gen}{years}</div>')
        parts.append(_render_nodes(n.get("children") or [], depth + 1))
    return "\n".join(parts)

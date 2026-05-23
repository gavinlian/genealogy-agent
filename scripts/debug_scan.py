import asyncio
import sys

sys.path.insert(0, "backend")
from agent.pipeline import run_scan_pipeline

MULTIGEN_TEXT = """张氏族谱
一世 张公
二世 张子 生1950
三世 孙一 男 生1980
孙二 男 生1985"""


async def _ocr(p, m, i, pr):
    return MULTIGEN_TEXT, ""


async def _parse(p, m, pr):
    return (
        '{"persons": [{"name": "张公", "generation": 1}, {"name": "张子", "generation": 2}, '
        '{"name": "孙一", "generation": 3}], "relations": []}',
        "",
    )


if __name__ == "__main__":
    from agent.name_extractor import refine_persons_list
    from agent.genealogy_builder import auto_build_genealogy

    ai = [
        {"name": "张公", "generation": 1},
        {"name": "张子", "generation": 2},
        {"name": "孙一", "generation": 3},
    ]
    persons = refine_persons_list(ai, MULTIGEN_TEXT)
    print("refined", [(p["name"], p.get("generation")) for p in persons])
    from agent.genealogy_builder import (
        parse_genealogy_text_enhanced,
        infer_relations_by_generation,
        infer_relations_from_child_roles,
        merge_relations,
        dedupe_persons,
    )

    enhanced = parse_genealogy_text_enhanced(MULTIGEN_TEXT)
    persons2 = dedupe_persons(persons + enhanced["persons"])
    rels = enhanced["relations"]
    rels = merge_relations(rels, infer_relations_by_generation(persons2))
    rels = merge_relations(rels, infer_relations_from_child_roles(persons2, MULTIGEN_TEXT))
    print("persons2", [(p["name"], p.get("generation")) for p in persons2])
    print("enhanced rels", len(enhanced["relations"]))
    for r in rels:
        print(" ", r)
    import sys

    sys.exit(0)
    built = auto_build_genealogy(MULTIGEN_TEXT, persons, [])
    rels = [r for r in built["relations"] if r.get("type") == "parent_child"]
    print("pc count", len(rels))
    for r in rels:
        print(" ", r.get("from"), "->", r.get("to"))
    # cycle detect
    graph = {}
    for r in rels:
        graph.setdefault(r["from"], []).append(r["to"])
    visited = set()

    def dfs(n, stack):
        if n in stack:
            print("CYCLE", stack + [n])
            return
        if n in visited:
            return
        visited.add(n)
        for c in graph.get(n, []):
            dfs(c, stack + [n])

    for n in graph:
        dfs(n, [])

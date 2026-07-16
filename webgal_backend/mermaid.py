from __future__ import annotations

import re


# Mermaid accepts Unicode identifiers. Keeping this pattern in one module avoids
# the narrative validator and the game-design compiler disagreeing about which
# edges exist (for example: ``phase6 --> 真结局``).
MERMAID_NODE_PATTERN = r"(?:[^\W\d]|_)[\w-]*"
MERMAID_NODE_SHAPE_PATTERN = r"(?:\[[^\]]*\]|\([^\)]*\)|\{[^\}]*\})?"


def mermaid_edges(narrative_structure: str) -> list[dict[str, str]]:
    edge_re = re.compile(
        rf"(?P<source>{MERMAID_NODE_PATTERN}){MERMAID_NODE_SHAPE_PATTERN}\s*"
        rf"(?:-->|==>|-\.->)\s*"
        rf"(?:\|(?P<label>[^|]+)\|\s*)?"
        rf"(?P<target>{MERMAID_NODE_PATTERN}){MERMAID_NODE_SHAPE_PATTERN}"
    )
    edges: list[dict[str, str]] = []
    for line in narrative_structure.splitlines():
        cleaned = line.strip().rstrip(";")
        if not cleaned or cleaned.startswith(("%%", "#")):
            continue
        for match in edge_re.finditer(cleaned):
            edges.append(
                {
                    "source": match.group("source").strip(),
                    "target": match.group("target").strip(),
                    "label": (match.group("label") or "").strip(),
                }
            )
    return edges


def mermaid_edge_node_pairs(narrative_structure: str) -> list[tuple[str, str]]:
    return [(edge["source"], edge["target"]) for edge in mermaid_edges(narrative_structure)]


def mermaid_standalone_nodes(narrative_structure: str, keywords: set[str] | None = None) -> list[str]:
    node_re = re.compile(
        rf"^\s*(?P<node>{MERMAID_NODE_PATTERN})\s*{MERMAID_NODE_SHAPE_PATTERN}\s*$"
    )
    excluded = keywords or set()
    nodes: list[str] = []
    for line in narrative_structure.splitlines():
        cleaned = line.strip().rstrip(";")
        if not cleaned or cleaned.startswith(("%%", "#")) or any(token in cleaned for token in ("-->", "==>", "-.->")):
            continue
        match = node_re.match(cleaned)
        if match and match.group("node") not in excluded:
            nodes.append(match.group("node"))
    return nodes

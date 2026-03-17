from __future__ import annotations


def _attr_val(v: str) -> str:
    try:
        float(str(v))
        return str(v)
    except (ValueError, TypeError):
        return f"'{v}'"


def _feature_lines(node: dict, lines: list[str], indent: int) -> None:
    tab = "\t" * indent
    attrs = node.get("attributes", {})
    attr_str = ", ".join(f"{k} {_attr_val(str(v))}" for k, v in attrs.items())
    suffix = f" {{ {attr_str} }}" if attr_str else ""
    lines.append(f"{tab}{node['name']}{suffix}")
    for rel in node.get("relations", []):
        rel_type = rel["type"].lower()
        lines.append(f"{tab}\t{rel_type}")
        for child in rel["children"]:
            _feature_lines(child, lines, indent + 2)


_PREC = {"IMPLIES": 0, "OR": 1, "AND": 2, "NOT": 3, "FEATURE": 4}


def ast_to_uvl(node: dict, parent_prec: int = -1) -> str:
    op = node["op"]
    if op == "FEATURE":
        return node["name"]
    if op == "NOT":
        return f"!{ast_to_uvl(node['left'], _PREC['NOT'])}"

    my_prec = _PREC.get(op, 0)
    if op == "IMPLIES":
        expr = f"{ast_to_uvl(node['left'], my_prec)} => {ast_to_uvl(node['right'], my_prec)}"
    elif op == "AND":
        expr = f"{ast_to_uvl(node['left'], my_prec)} & {ast_to_uvl(node['right'], my_prec)}"
    elif op == "OR":
        expr = f"{ast_to_uvl(node['left'], my_prec)} | {ast_to_uvl(node['right'], my_prec)}"
    else:
        return ""

    return f"({expr})" if my_prec < parent_prec else expr


def to_uvl(tree: dict) -> str:
    """Serialise a feature tree dict (from FlamapyService.to_dict) back to UVL text."""
    lines = ["namespace agroTrain", "", "features"]
    _feature_lines(tree, lines, indent=1)
    constraints = tree.get("constraints", [])
    if constraints:
        lines.append("constraints")
        for c in constraints:
            lines.append(f"\t{ast_to_uvl(c['ast'])}")
    return "\n".join(lines)

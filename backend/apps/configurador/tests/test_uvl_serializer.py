"""Cover the small uvl_serializer module that converts trees back to UVL text."""
from __future__ import annotations

from apps.configurador.services.uvl_serializer import _attr_val, ast_to_uvl, to_uvl


class TestAttrValue:
    def test_numeric_values_unquoted(self):
        assert _attr_val("5") == "5"
        assert _attr_val("0.5") == "0.5"

    def test_string_values_quoted(self):
        assert _attr_val("hello") == "'hello'"


class TestAstToUvl:
    def test_feature(self):
        assert ast_to_uvl({"op": "FEATURE", "name": "X"}) == "X"

    def test_implies(self):
        node = {
            "op": "IMPLIES",
            "left": {"op": "FEATURE", "name": "A"},
            "right": {"op": "FEATURE", "name": "B"},
        }
        assert ast_to_uvl(node) == "A => B"

    def test_or_and_combinations(self):
        node = {
            "op": "AND",
            "left": {"op": "FEATURE", "name": "A"},
            "right": {
                "op": "OR",
                "left": {"op": "FEATURE", "name": "B"},
                "right": {"op": "FEATURE", "name": "C"},
            },
        }
        result = ast_to_uvl(node)
        assert "&" in result
        assert "|" in result

    def test_not(self):
        node = {"op": "NOT", "left": {"op": "FEATURE", "name": "X"}}
        assert ast_to_uvl(node) == "!X"


class TestToUvl:
    def test_serialises_tree_with_attributes_and_constraints(self):
        tree = {
            "name": "Root",
            "relations": [
                {
                    "type": "MANDATORY",
                    "children": [
                        {"name": "Child", "relations": [], "attributes": {"csv_col": "c"}},
                    ],
                }
            ],
            "constraints": [
                {
                    "ast": {
                        "op": "IMPLIES",
                        "left": {"op": "FEATURE", "name": "Child"},
                        "right": {"op": "FEATURE", "name": "Root"},
                    }
                }
            ],
        }
        text = to_uvl(tree)
        assert "features" in text
        assert "Root" in text
        assert "Child" in text
        assert "constraints" in text
        assert "Child => Root" in text

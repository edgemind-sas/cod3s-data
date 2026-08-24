"""Safe expression parser for Observatory breakpoint conditions.

Uses Python's ast module with a strict whitelist of allowed node types.
No eval(), no function calls, no imports, no builtins access.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

# Allowed comparison operators
_CMP_OPS: dict[type, Any] = {
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Allowed binary operators
_BIN_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}

# Allowed unary operators
_UNARY_OPS: dict[type, Any] = {
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

# Whitelist of allowed AST node types
_ALLOWED_NODES = frozenset(
    {
        ast.Expression,
        ast.BoolOp,
        ast.And,
        ast.Or,
        ast.Compare,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Attribute,
        ast.Load,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Eq,
        ast.NotEq,
        ast.In,
        ast.NotIn,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.USub,
        ast.Not,
    }
)


def validate_expression(expr: str) -> None:
    """Validate a breakpoint condition expression.

    Raises:
        ValueError: If the expression contains disallowed constructs.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}") from e

    _check_tree(tree)


def evaluate_expression(expr: str, context: dict[str, Any]) -> bool:
    """Evaluate a breakpoint condition expression safely.

    Args:
        expr: The condition expression (e.g., "value > 100")
        context: Variable bindings (value, key, channel, tags.*)

    Returns:
        True if the condition matches.

    Raises:
        ValueError: If expression is invalid.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}") from e

    _check_tree(tree)
    result = _eval_node(tree.body, context)
    return bool(result)


def _check_tree(tree: ast.AST) -> None:
    """Walk the AST and reject any disallowed node types."""
    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(
                f"Disallowed expression construct: {type(node).__name__}. "
                f"Only comparisons, boolean ops, and variable access are allowed."
            )

        # Extra safety: only allow Attribute for tags.* pattern
        if isinstance(node, ast.Attribute) and (
            not isinstance(node.value, ast.Name) or node.value.id != "tags"
        ):
            raise ValueError(f"Attribute access only allowed for 'tags.*', got '{ast.dump(node)}'")


def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id not in ctx:
            raise ValueError(f"Unknown variable: '{node.id}'")
        return ctx[node.id]

    if isinstance(node, ast.Attribute):
        # Only tags.* is allowed (validated in _check_tree)
        key = f"tags.{node.attr}"
        return ctx.get(key)

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, ctx)
        for op_node, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_node(comparator, ctx)
            op_func = _CMP_OPS.get(type(op_node))
            if op_func is None:
                raise ValueError(f"Unsupported comparison: {type(op_node).__name__}")
            if not op_func(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(_eval_node(v, ctx) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(_eval_node(v, ctx) for v in node.values)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, ctx)
        op_func = _UNARY_OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return op_func(operand)

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        op_func = _BIN_OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
        return op_func(left, right)

    raise ValueError(f"Cannot evaluate node type: {type(node).__name__}")

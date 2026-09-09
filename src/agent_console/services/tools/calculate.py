"""Arithmetic, evaluated by walking the AST rather than calling eval()."""

import ast
import operator

from agent_console.services.tools.context import ToolContext
from agent_console.services.tools.registry import ToolRegistry

__all__ = ["register"]

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.left), _evaluate(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_evaluate(node.operand))
    raise ValueError("only + - * / // % ** and numbers are allowed")


def register(registry: ToolRegistry, context: ToolContext) -> None:
    @registry.tool(
        name="calculate",
        description="Evaluate an arithmetic expression. Use instead of doing mental math.",
        parameters={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "e.g. (1200 * 0.15) + 90"}
            },
            "required": ["expression"],
        },
    )
    def calculate(expression: str) -> str:
        # Never put model-generated strings through eval(). Keep this AST-walked.
        return str(_evaluate(ast.parse(expression, mode="eval").body))

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENDPOINTS_DIR = ROOT / "app" / "api" / "v1" / "endpoints"

MAX_FUNCTION_LINES = 220
MAX_FUNCTION_COMPLEXITY = 45

COMPLEXITY_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.Match,
    ast.BoolOp,
    ast.IfExp,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _iter_files() -> list[Path]:
    return sorted(path for path in ENDPOINTS_DIR.rglob("*.py") if path.is_file())


def _function_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nodes.append(node)
    return nodes


def _complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, COMPLEXITY_NODES):
            if isinstance(child, ast.BoolOp):
                score += max(1, len(child.values) - 1)
            else:
                score += 1
    return score


def main() -> int:
    failures: list[str] = []
    for file_path in _iter_files():
        rel = file_path.relative_to(ROOT)
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as exc:
            failures.append(f"{rel} parse failed: {exc}")
            continue
        for fn in _function_nodes(tree):
            start = getattr(fn, "lineno", 0)
            end = getattr(fn, "end_lineno", start)
            line_count = max(0, end - start + 1)
            complexity = _complexity(fn)
            if line_count > MAX_FUNCTION_LINES or complexity > MAX_FUNCTION_COMPLEXITY:
                failures.append(
                    f"{rel}:{start} function '{fn.name}' lines={line_count} complexity={complexity} "
                    f"(max lines={MAX_FUNCTION_LINES}, max complexity={MAX_FUNCTION_COMPLEXITY}). "
                    "Create refactor ticket before further expansion."
                )

    if failures:
        print("Endpoint complexity guard failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Endpoint complexity guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

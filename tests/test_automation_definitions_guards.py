"""Tests for automation_definitions endpoint regression fix."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.api.v1.endpoints import automation_definitions as endpoint_mod


def test_list_workflow_templates_has_db_parameter():
    """list_workflow_templates must have db as a Depends(get_db) parameter."""
    sig = inspect.signature(endpoint_mod.list_workflow_templates)
    assert "db" in sig.parameters, "list_workflow_templates missing db parameter"


def test_create_from_template_has_db_parameter():
    """create_from_template must have db as a Depends(get_db) parameter."""
    sig = inspect.signature(endpoint_mod.create_from_template)
    assert "db" in sig.parameters, "create_from_template missing db parameter"


def test_list_workflow_templates_awaits_require():
    """The _require_workflow_v2 call must be awaited, not bare."""
    source = inspect.getsource(endpoint_mod.list_workflow_templates)
    assert "await _require_workflow_v2" in source, \
        "list_workflow_templates does not await _require_workflow_v2"


def test_create_from_template_awaits_require():
    """The _require_workflow_v2 call must be awaited with proper args."""
    source = inspect.getsource(endpoint_mod.create_from_template)
    assert "await _require_workflow_v2(db" in source, \
        "create_from_template does not properly await _require_workflow_v2(db, ...)"


def test_no_depends_get_db_in_function_body():
    """Depends(get_db) must only appear in function signatures, never in the body.

    We only check the body statements of each async function, not the
    parameter defaults (where Depends(get_db) is correct usage).
    """
    source_file = Path(endpoint_mod.__file__)
    tree = ast.parse(source_file.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            # Only walk the body statements, NOT the args/defaults
            for stmt in node.body:
                for body_node in ast.walk(stmt):
                    if isinstance(body_node, ast.Call):
                        func = body_node.func
                        if isinstance(func, ast.Name) and func.id == "Depends":
                            for arg in body_node.args:
                                if isinstance(arg, ast.Name) and arg.id == "get_db":
                                    assert False, \
                                        f"Found Depends(get_db) in body of {node.name} — must be in signature only"

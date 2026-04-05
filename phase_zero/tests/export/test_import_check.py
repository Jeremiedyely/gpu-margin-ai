"""
Import Check — Tests (IMP-01 → IMP-04).

Verifies all 4 coupled components import EXPORT_COLUMN_ORDER
from the shared constant module. Contract 5 enforcement.
"""

import ast
import inspect
from pathlib import Path

import pytest


# The 4 coupled components that MUST import from column_order
COUPLED_MODULES = [
    "app.export.csv_generator",
    "app.export.excel_generator",
    "app.export.power_bi_generator",
    "app.export.output_verifier",
]


def _module_imports_from_column_order(module_name: str) -> bool:
    """Check that the module imports EXPORT_COLUMN_ORDER from column_order."""
    import importlib

    mod = importlib.import_module(module_name)
    source_file = inspect.getfile(mod)
    source = Path(source_file).read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "column_order" in node.module:
                imported_names = [alias.name for alias in node.names]
                if "EXPORT_COLUMN_ORDER" in imported_names:
                    return True
    return False


class TestImportCheck:
    """Step 7.5 — Import verification (Contract 5)."""

    # IMP-01: CSV Generator imports from column_order
    def test_imp_01_csv_imports(self):
        assert _module_imports_from_column_order("app.export.csv_generator")

    # IMP-02: Excel Generator imports from column_order
    def test_imp_02_excel_imports(self):
        assert _module_imports_from_column_order("app.export.excel_generator")

    # IMP-03: Power BI Generator imports from column_order
    def test_imp_03_power_bi_imports(self):
        assert _module_imports_from_column_order(
            "app.export.power_bi_generator"
        )

    # IMP-04: Output Verifier imports from column_order
    def test_imp_04_verifier_imports(self):
        assert _module_imports_from_column_order("app.export.output_verifier")

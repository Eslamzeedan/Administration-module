"""Prevent incomplete Frappe DocType packages from passing offline CI."""
import ast
import json
from pathlib import Path
import unittest

DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "eup_administration" / "eup_administration" / "doctype"


class TestDocTypeControllerPackages(unittest.TestCase):
    def test_standard_doctypes_have_python_controllers(self):
        schemas = sorted(DOCTYPE_ROOT.glob("*/*.json"))
        self.assertTrue(schemas, "No DocType schemas discovered")
        for schema_path in schemas:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            if schema.get("custom"):
                continue
            with self.subTest(doctype=schema["name"]):
                controller = schema_path.with_suffix(".py")
                self.assertTrue(controller.is_file(), f"Missing Frappe controller {controller}")
                self.assertTrue((schema_path.parent / "__init__.py").is_file())
                module = ast.parse(controller.read_text(encoding="utf-8"))
                expected_class = schema["name"].replace(" ", "")
                self.assertTrue(
                    any(isinstance(n, ast.ClassDef) and n.name == expected_class for n in module.body),
                    f"Missing controller class {expected_class} in {controller}",
                )

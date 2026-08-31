import ast
from pathlib import Path


FORBIDDEN_IMPORTS = ("fal", "openai", "obsws", "requests")


def test_default_package_has_no_vendor_client_imports():
    package_root = Path(__file__).parents[1] / "pack_manager"
    violations = []
    for source_path in package_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(), filename=str(source_path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(
                    name == forbidden or name.startswith(f"{forbidden}.")
                    for forbidden in FORBIDDEN_IMPORTS
                ):
                    violations.append(f"{source_path.relative_to(package_root)}: {name}")

    assert violations == []

"""AST-based discovery of Pydantic model classes without executing modules."""

from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AstModel:
    module: str
    name: str
    qualname: str
    path: Path
    lineno: int
    is_public: bool


@dataclass(slots=True)
class AstDiscoveryResult:
    models: list[AstModel]
    warnings: list[str]


PYDANTIC_BASES = {
    ("pydantic", "BaseModel"),
    ("pydantic", "RootModel"),
    ("pydantic.v1", "BaseModel"),
    ("pydantic.v1", "RootModel"),
}


def discover_models(
    paths: Iterable[Path | str],
    *,
    infer_module: bool = False,
    public_only: bool = False,
) -> AstDiscoveryResult:
    """Discover Pydantic models from the given Python source files using AST parsing."""
    models: list[AstModel] = []
    warnings: list[str] = []

    for raw_path in paths:
        path = Path(raw_path)
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"Failed to read {path}: {exc}")
            continue

        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            warnings.append(f"Failed to parse {path}: {exc}")
            continue

        resolver = _ImportResolver()
        resolver.visit(tree)

        module_name = path.stem if infer_module else "unknown"
        public_names = _extract_public_names(tree)

        for class_node in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
            if not _is_pydantic_model(class_node, resolver):
                continue

            if public_names is not None:
                is_public = class_node.name in public_names
            else:
                is_public = not class_node.name.startswith("_")
            if public_only and not is_public:
                continue

            model = AstModel(
                module=module_name,
                name=class_node.name,
                qualname=f"{module_name}.{class_node.name}",
                path=path,
                lineno=class_node.lineno,
                is_public=is_public,
            )
            models.append(model)

    models.sort(key=lambda m: (m.module, m.name))
    return AstDiscoveryResult(models=models, warnings=warnings)


class _ImportResolver(ast.NodeVisitor):
    def __init__(self) -> None:
        self.aliases: dict[str, tuple[str, str]] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            base_name = alias.name.split(".")[0]
            for module, _ in PYDANTIC_BASES:
                if base_name == module:
                    self.aliases[name] = (module, "*")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module
        if module is None:
            return
        base_module = module.split(".")[0]
        for alias in node.names:
            target_name = alias.asname or alias.name
            qual = alias.name
            if module in {"pydantic", "pydantic.v1"} and qual in {"BaseModel", "RootModel"}:
                self.aliases[target_name] = (module, qual)
            elif base_module in {"pydantic", "pydantic.v1"}:
                self.aliases[target_name] = (base_module, "*")


def _extract_public_names(tree: ast.AST) -> set[str] | None:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, ast.List | ast.Tuple)
                ):
                    names: set[str] = set()
                    for element in node.value.elts:
                        if isinstance(element, ast.Constant) and isinstance(element.value, str):
                            names.add(element.value)
                    return names
    return None


def _is_pydantic_model(node: ast.ClassDef, resolver: _ImportResolver) -> bool:
    for base in node.bases:
        module_class = _resolve_base(base, resolver)
        if module_class is None:
            continue
        module, class_name = module_class
        if (module, class_name) in PYDANTIC_BASES:
            return True
    return False


def _resolve_base(base: ast.expr, resolver: _ImportResolver) -> tuple[str, str] | None:
    if isinstance(base, ast.Name):
        return resolver.aliases.get(base.id)
    if isinstance(base, ast.Attribute):
        parts = _flatten_attribute(base)
        if len(parts) >= 2:
            module_candidate = parts[0]
            class_candidate = parts[-1]
            alias = resolver.aliases.get(module_candidate)
            if alias:
                module, _ = alias
                return (module, class_candidate)
            if module_candidate in {"pydantic", "pydantic.v1"}:
                return (module_candidate, class_candidate)
    return None


def _flatten_attribute(attr: ast.Attribute) -> list[str]:
    parts: list[str] = []
    current: ast.AST | None = attr
    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.insert(0, current.id)
    return parts

# `pfg plugin`

## Capabilities
`pfg plugin` scaffolds a complete Pluggy provider project (pyproject, source package, tests, README, and GitHub Actions workflow). It normalizes names, entry points, and namespaces so the new plugin can be published to PyPI and discovered by fixturegen without manual boilerplate.

## Typical use cases
- Spin up a workspace for a custom provider package (for example, domain-specific Faker data).
- Keep naming conventions consistent across internally maintained plugins.
- Prototype plugins locally with `pip install -e .` immediately after scaffolding.

## Inputs & outputs
- **Name argument**: seed used to derive the slug (`acme-colorizer` → `slug`, default distribution name, default entry point, and class names).
- **Outputs**: directory tree containing `pyproject.toml`, `README.md`, `src/<namespace>/<slug>/__init__.py`, tests, and optional metadata (license, author, etc.).

## Flag reference
- `--directory/-d`: destination directory (defaults to the derived distribution name).
- `--namespace/-n`: dotted namespace for the package (for example `acme.plugins`).
- `--distribution`: override PyPI distribution name (defaults to `pfg-<slug>` or `<namespace>-<slug>`).
- `--entrypoint`: pluggy entry point name (defaults to slug with dashes preserved).
- `--description`, `--author`, `--version`, `--license`: metadata injected into `pyproject.toml` and README.
- `--force`: allow overwriting non-empty directories/files.

## Example workflows
### Scaffold a plugin under a namespace
```bash
pfg plugin new acme-colorizer \
  --namespace acme.plugins \
  --distribution acme-pfg-colorizer \
  --entrypoint acme-colorizer \
  --description "Adds ACME-specific color providers" \
  --author "QA Team" --version 0.1.0
```
Creates `acme-pfg-colorizer/` containing a namespaced package, configured entry point, README, tests, and CI workflow file.

**Sample output**
```text
[plugin_scaffold] target=acme-pfg-colorizer files=9
  created pyproject.toml
  created src/acme/plugins/acme_colorizer/__init__.py
  created tests/test_plugin.py
```

### Scaffold into an existing directory (overwrite)

```bash
pfg plugin new beta-masker \
  --directory plugins/beta-masker \
  --namespace org.mask \
  --force
```

Overwrites the `plugins/beta-masker` directory with a fresh scaffold, keeping the namespace under `org.mask`.

## Operational notes
- The generator sanitizes names to valid Python identifiers and PyPI-safe slugs; invalid inputs raise `BadParameter` with clear instructions.
- Files are written atomically using `write_atomic_text` so partial scaffolds are avoided even when the process is interrupted.
- Use `--force` when re-running in the same directory; otherwise the CLI aborts to protect existing work.

## Related docs
- [CLI reference](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/cli.md#pfg-plugin)
- [Providers](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/providers.md)
- [Architecture](https://github.com/CasperKristiansson/pydantic-fixturegen/blob/main/docs/architecture.md#plugins)

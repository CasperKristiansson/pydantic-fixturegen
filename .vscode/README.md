# VS Code workspace support

This folder contains reusable automation for `pfg` when working inside Visual Studio Code.

- `tasks.json` defines common commands (generate JSON/fixtures/schema, check, doctor) and prompts for module path, output destination, include filters, and seed. Each task appends `--json-errors` so diagnostics are structured.
- `problem-matchers.json` registers the `$pfg-json-errors` matcher that understands the CLI's JSON error payloads and maps them to VS Code Problems entries with file, line, and severity.

To use:
1. Open the repository in VS Code and allow the workspace tasks.
2. Run `Tasks: Run Task` from the Command Palette and choose a `PFG:` entry.
3. Inspect the Problems panel for any reported issues.

You can copy or customise these files for other projects that rely on `pfg`.

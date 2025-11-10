# VS Code integration

> Use ready-made tasks and diagnostics when working with `pfg` from Visual Studio Code.

## Prerequisites

- Install the project in your preferred environment (`pip install pydantic-fixturegen` or use your existing virtualenv).
- Ensure the `pfg` CLI is discoverable in your VS Code terminal.

## Provided tasks

The repository ships reusable tasks under `.vscode/tasks.json` for common workflows:

- **PFG: Generate JSON** – runs `pfg gen json` with prompts for module path, output destination, model filters, and seed.
- **PFG: Generate Fixtures** – runs `pfg gen fixtures` with the same inputs.
- **PFG: Generate Schema** – runs `pfg gen schema` for schema export.
- **PFG: Check** – runs `pfg check` to validate configuration, discovery, and destinations.
- **PFG: Doctor** – runs `pfg doctor` to identify coverage gaps.

Each task prompts for the following inputs:

- `modulePath`: path to a module or package that exposes your Pydantic models (default: `./models.py`).
- `outputPath`: directory or file for generated artifacts (default: `./out`).
- `modelFilter`: optional comma-separated include patterns (defaults to include all models).
- `seed`: deterministic seed value (default: `42`).

Task output is routed to the shared terminal panel and uses a custom problem matcher so errors appear in the Problems view.

## Problem matcher details

`.vscode/problem-matchers.json` registers the `$pfg-json-errors` matcher. It consumes the structured JSON emitted by passing `--json-errors` to CLI commands and converts it into VS Code diagnostics (file, line, message, severity, and code where available).

If you extend the tasks or invoke `pfg` manually, add `--json-errors` so diagnostics are parsed automatically.

## Getting started

1. Open the project folder in VS Code.
2. When prompted, select “Allow” to use the workspace tasks and problem matchers.
3. Open the Command Palette (`⇧⌘P` / `Ctrl+Shift+P`) and run `Tasks: Run Task`.
4. Choose one of the `PFG:` tasks and enter the prompted values.
5. Investigate any reported problems from the Problems panel; they will link back to affected files when location data is available.

## Customising

- You can change defaults or add new tasks by editing `.vscode/tasks.json`.
- To specify additional CLI flags, append them to the `args` array of a task.
- If you prefer global tasks, copy these files to your global VS Code settings, or incorporate them into project templates.

See [docs/cli.md](./cli.md) for more background on the underlying commands.\*\*\* End Patch

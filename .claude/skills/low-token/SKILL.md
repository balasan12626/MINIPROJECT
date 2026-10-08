---
name: low-token
description: Use for efficient work with minimal unnecessary context, file reads, tool calls, and output.
---

# Low Token Workflow

- Inspect only files required for the task.
- Prefer targeted search over broad repo exploration.
- Do not reread unchanged files.
- Ignore node_modules, .git, build output, caches, datasets, model weights, logs, and virtual environments unless required.
- Keep the change small and correct.
- Reuse existing code before creating new code.
- Run focused validation instead of the full suite.
- Keep final responses concise.

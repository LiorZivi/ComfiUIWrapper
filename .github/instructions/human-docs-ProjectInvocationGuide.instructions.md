---
applyTo: "src/comfywrap/capabilities/**"
---

# Keep the invocation doc in sync

Whenever you **add, remove, or change a capability** (or the general functionality it exposes on the CLI) under `src\comfywrap\capabilities\`, update `human-docs\ProjectInvocationGuide.md` in the same change:

- Add/update the capability's row in the **Capabilities** table with a very short "how to invoke" (its `generate` invocation and key flags, e.g. `--model` / `--image`).
- If a `doctor`/`capabilities`-style command changes, update the **General functionality** table instead.

The invocation guide must always reflect the capabilities the tool actually exposes.

# Copilot instructions — ComfiUIWrapper (`comfywrap`)

This repo is a thin, typed, scriptable **CLI that drives
[comfy-cli](https://github.com/Comfy-Org/comfy-cli) as a subprocess** to run
ComfyUI workflows headlessly. v1 ships one capability — `text_to_video` via
**LTX-2** (`ltx2-t2v`) — behind a stable command/`--json` contract. It is a
reusable, modality-agnostic core/runtime plus pluggable capability adapters.

These instructions are **project-wide**. Path-specific guidance lives in scoped
files under `.github\instructions\` (applied automatically by path):

- `.github\instructions\docs.instructions.md` — writing docs (under
  `agent-memory\` and `human-docs\`).
- `.github\instructions\capability.instructions.md` — capability adapters under
  `src\comfywrap\capabilities\`.

**Read these first** — the agent's curated docs in `agent-memory\` (the source of
truth; keep them accurate when behavior changes):

- `agent-memory\STRUCTURE.md` — the repo's doc layout + what to read.
- `agent-memory\ProjectSpec.md` — the purpose + the stable automation contract.
- `agent-memory\adding-a-capability.md` — how to add a model/modality (no core edits).
- `README.md` — user-facing setup/usage.

**Do NOT read `human-docs\`.** Those files (`HighLevelArchitecture.md`,
`Implementation.md`, `FirstUseAndHowToRunExplanation.md`, `skill-invocation.md`,
`validation.md`) are
narrative/reference material written for the human maintainer. Everything you
need to act is in `agent-memory\` + these instruction files; for specifics, read
the **code** under `src\comfywrap\` directly. Repo-root `spec.md` and
`output\architect\` are the historical intent + plan (not current behavior).

## Project-wide constraints

- **Drive comfy-cli as a subprocess; NEVER `import comfy_cli`.** This is a hard
  rule: it gives crash isolation, dependency isolation, and a clean GPL boundary
  (comfy-cli is GPL-3.0; comfywrap is MIT and stdlib-only). All `comfy`
  interaction lives in **one module**: `src\comfywrap\core\driver.py`.
- **Architecture:** a reusable core (`src\comfywrap\core`) plus pluggable
  capability adapters (`src\comfywrap\capabilities\<modality>\<capability>\`).
  The core is **modality-agnostic** — no model/video/capability specifics in it.
  Adding a capability = a new template + adapter package + one manifest import
  line — **never edit the core** to add one (see
  `agent-memory\adding-a-capability.md`).
- **The CLI contract is stable and scriptable** (a caller / future skill depends
  on it): `generate` prints the saved absolute artifact path as the final stdout
  line; global `--json` emits exactly one object
  `{capability,model,artifacts:[{path,type,metadata}]}` (errors emit one
  `{error:{…}}` object); diagnostics go to stderr. Exit codes are deterministic
  **0–11** — see `agent-memory\ProjectSpec.md`. Do not churn this surface.
- **comfywrap uses no torch/CUDA itself.** The GPU stack (cu12x on the RTX 5090,
  sm_120) lives in **ComfyUI's** venv (`C:\AI\Softwares\.venv`); comfywrap only
  shells out to `comfy`. `comfywrap doctor` verifies GPU + comfy-cli + ComfyUI
  reachability + LTX-2 model files.
- **Server lifecycle:** comfywrap probes `host:port` (default `127.0.0.1:8000`),
  **attaches** if reachable, else auto-launches a headless ComfyUI and keeps it
  warm (model load paid once). Never run two ComfyUI instances on the box (VRAM).
- **Build/test:** develop in `.venv` (`pip install -e ".[dev]"`); run the
  GPU-free unit suite with `.venv\Scripts\python.exe -m pytest`. The suite mocks
  the `comfy` subprocess (canned `--json` envelopes) — keep it GPU-free. The
  opt-in real-GPU test runs only with `CUW_RUN_INTEGRATION=1`. **Never commit**
  `.venv\`, `.scratch\`, `output\` (the architect `output\architect\*.md` are an
  intentional tracked exception), generated media, or any token.
- **Scope discipline:** don't add new modalities/capabilities or change the
  contract without an explicit ask.

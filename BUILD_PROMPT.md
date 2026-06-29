# Build prompt — ComfiUIWrapper

Start a new Copilot CLI session with the working directory set to this folder
(`C:\Dev\MyRepos\ComfiUIWrapper`), then paste the prompt below to build the
project. `spec.md` in this repo is the source of truth.

---

```
Read spec.md in this repo top-to-bottom — it is the source of truth for what to build. Then build the project.

Hard constraints:
- This project is SELF-CONTAINED. Do not depend on, import, reference, or copy from any other local project. Anything you need must be defined here.
- Honor the invocation contract in spec.md §4 exactly: the `generate` grammar, the `--json` stdout envelope `{capability, model, artifacts:[{path,type,metadata}]}`, the final-stdout-line-is-the-absolute-path rule, diagnostics on stderr, and exit codes per §4.3. This contract must stay stable and scriptable.
- Capability-oriented, not a generic graph runner. Keep all ComfyUI-version-specific logic isolated in the backend manager (spec.md §3.1).
- Environment: Windows + PowerShell (backslash paths); GPU is an RTX 5090 (Blackwell, sm_120) — see spec.md Appendix A for ComfyUI app/data paths, the source LTX-2 workflow, and the model files it loads.

Deliver the §6 vertical slice end-to-end: `doctor`, `capabilities`, and `generate "<prompt>" --model ltx2-t2v --seed <n> [--json]` for the `text_to_video` capability, driving a headless ComfyUI to run the LTX-2 workflow and returning the absolute path to the produced .mp4 plus a sidecar provenance JSON.

Key setup notes:
- ComfyUI's /prompt endpoint needs the workflow in API format, not the UI workflow JSON. Plan how to capture an API-format export of `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` (e.g. ComfyUI Dev Mode → Export (API)) and store it under workflows/. If you can't produce it programmatically, stop and tell me exactly what to export.
- Inject prompt/seed/params by stable node title/role bindings, not raw numeric IDs.
- Add a GPU-free unit suite that mocks the ComfyUI HTTP/websocket surface (submit → progress → history → output collection), plus error→exit-code mapping and the --json envelope shape. An opt-in integration test may hit a real local ComfyUI.

Workflow:
1. First, post a short build plan and resolve spec.md §12 open questions by proposing sensible defaults (binary name `comfywrap`, auto-launch ComfyUI, etc.) — flag anything you need me to decide.
2. Then scaffold the repo (src/comfywrap, pyproject.toml console script `comfywrap = "comfywrap.core.cli:main"`, README, tests), init a git repo, and implement the slice.
3. Validate: `comfywrap doctor`, `comfywrap capabilities`, and a real `comfywrap generate ... --json` that yields a playable .mp4; ensure unit tests pass. Report results.
```

# ComfiUIWrapper — Plan

> Build the `comfywrap` typed CLI as a thin wrapper that drives `comfy-cli` as a subprocess to run the LTX-2 `text_to_video` slice, returning a stable artifact path / `--json` envelope and a provenance sidecar.

**Created**: 2026-06-30 **Approach**: Pragmatic **Spec**: C:\Dev\MyRepos\ComfiUIWrapper\output\architect\ComfiUIWrapper-spec.md **Review Score**: 8/10 — PASS (2026-06-30) **Status**: ✅ Complete — all 6 phases / 23 steps delivered and validated on the RTX 5090 (see `human-docs\validation.md`; unit suite: 35 passed, 1 skipped). Progress marked 2026-07-03.

> Authoritative technical design: `spec.md` at the repo root. All `§` references below point to it.

## Architecture plan
Two thin layers per `spec.md` §3: a reusable `core/` runtime plus one capability adapter, with every ComfyUI/comfy-cli quirk quarantined in a single driver module. The driver is the only code that shells out to the `comfy` binary (never imported); it owns server lifecycle, workflow submission, envelope parsing, and the mapping onto the 0–11 exit taxonomy (§4.3, §5). Typed parameters are injected into a stored flat API-format LTX-2 template by stable node `_meta.title`/role bindings, written to a temp prompt, and handed to the driver. A minimal registry keyed by `(capability, model)` is the single seam for future capabilities — and it is deliberately **modality-agnostic**: each adapter declares its own typed parameter schema and artifact type (today `video/mp4`; tomorrow other ComfyUI video models, or non-video modalities such as image or audio), while the core (driver, injection, registry, dispatcher, output/provenance) stays capability- and modality-neutral. Adding a capability is a new adapter module + workflow template + binding map with **no core changes**. v1 still ships only `text_to_video`/`ltx2-t2v` — no plugin framework, no speculative extensibility — but the seam is shaped so more video and non-video models slot in later. The CLI dispatcher enforces the stable stdout/stderr discipline and the `--json` envelope (§4.2); an output/provenance writer emits the artifact plus its `<artifact>.json` sidecar (§4.4). GPU-free unit tests fake the subprocess seam; a real RTX 5090 run proves the end-to-end slice and warm reuse.

## ✅ Phase 1: Scaffolding, packaging, config & error taxonomy
> Foundations that touch no ComfyUI: an installable package, layered config, typed errors → exit codes, and the CLI grammar.

**Milestone**: `comfywrap` installs as a console script and parses the full command grammar; config resolution and error→exit mapping are unit-testable. **Acceptance**: The foundations load and behave per the contract with no backend present.
- `--version` and `--help` succeed; unknown/invalid args exit with code 2.
- Config resolves with precedence CLI flag > `CUW_*` env > config file > builtin (verified by unit tests).
- Each typed error maps to its documented code in §4.3 (verified by unit tests).

### ✅ Step 1.1: Repo scaffold & packaging
- **What**: Create the `src/comfywrap` tree, the `core/` and `capabilities/video/text_to_video/` packages, and empty `workflows/`, `scripts/`, `tests/`, `docs/` dirs per §10. Add `pyproject.toml` with the console script entry point.
- **Deliverables**: `pyproject.toml` (console script `comfywrap = "comfywrap.core.cli:main"`), `src/comfywrap/__init__.py`, `core/` and `capabilities/video/text_to_video/` package dirs, placeholder `README.md`.
- **Dependencies**: None

### ✅ Step 1.2: Error taxonomy & exit codes
- **What**: Define typed exception classes for each failure class and a central mapper to codes 0–11 per §4.3. Render an actionable stderr message for each, never a raw traceback.
- **Deliverables**: `core/errors.py` (exception types, exit-code mapping, message formatter).
- **Dependencies**: 1.1

### ✅ Step 1.3: Layered config loader
- **What**: Resolve config with precedence CLI > `CUW_*` env > config file (`comfywrap.toml`/`config.toml` via `tomllib`) > builtin defaults. Expose the §7 keys.
- **Deliverables**: `core/config.py` (loader, defaults, key names: comfy binary path, host, port, launch extra args, auto-launch, keep-warm, base dirs, default output dir, timeouts, default model).
- **Dependencies**: 1.1

### ✅ Step 1.4: CLI dispatcher skeleton
- **What**: Build the argparse grammar for `comfywrap [--version] <command>` with global flags `--json`, `--config`, `-v/--verbose`; register core commands (`doctor`, `capabilities`) and a capability-contributed `generate`. Enforce stdout/stderr discipline and a top-level handler that converts typed errors to exit codes.
- **Deliverables**: `core/cli.py` (`main()`, parser, global-flag handling, command registration, error→exit boundary).
- **Dependencies**: 1.2, 1.3

## ✅ Phase 2: comfy-cli driver
> The single isolation module that shells out to `comfy`; everything version-specific lives here (§5).

**Milestone**: The driver can decide attach-vs-launch, submit a prepared workflow, parse the one JSON envelope, extract output paths, and map failures to 0–11 — all verified against a faked subprocess. **Acceptance**: Driver behavior is correct with the real `comfy` binary mocked.
- With a faked runner, attach/launch/keep-warm/stop decisions follow config.
- A canned success envelope yields the extracted absolute output path(s).
- Each canned failure envelope/exit maps to the documented code (incl. OOM→5, timeout→11).

### ✅ Step 2.1: Subprocess runner seam & comfy argv builder
- **What**: Define a thin runner seam (executes argv → exit/stdout/stderr) that tests can fake, and build argv for the `comfy` launch (background, host/port, extra args), run (wait, local-paths, json, timeout), and stop subcommands per §5. Never import `comfy_cli`.
- **Deliverables**: `core/driver.py` (runner seam, argv builders), plus minimal inline `comfy` runner fakes + canned success/failure envelopes for this phase's tests (later consolidated into the shared fixtures in 5.1).
- **Dependencies**: 1.3

### ✅ Step 2.2: Server lifecycle (probe / attach / launch / keep-warm)
- **What**: Probe the configured host/port; attach if reachable; else, when auto-launch is on, start a background server and wait for readiness. Reuse across calls; optional stop per keep-warm / attach-only config.
- **Deliverables**: `core/driver.py` (probe, ensure-server, readiness wait, stop).
- **Dependencies**: 2.1

### ✅ Step 2.3: Run workflow & parse envelope
- **What**: Hand a prepared prompt file to the run subcommand, read the single JSON envelope from stdout, and extract produced file paths (`data.outputs` / output events) per §5.
- **Deliverables**: `core/driver.py` (run, envelope parse, output-path extraction).
- **Dependencies**: 2.1

### ✅ Step 2.4: Envelope/exit → exit-code mapping
- **What**: Translate comfy-cli `error.code` plus process exit onto the 0–11 taxonomy per §4.3/§5, detecting OOM in the failure message (→5). Always surface an actionable stderr message, never the raw comfy-cli envelope.
- **Deliverables**: `core/driver.py` (failure mapper) reusing `core/errors.py`.
- **Dependencies**: 2.3, 1.2

## ✅ Phase 3: Template capture, bindings & parameter injection
> Obtain a flat API-format LTX-2 template and inject typed params by stable title/role (§5).

**Milestone**: A stored API-format template exists under `workflows/`; typed inputs inject into a concrete temp prompt at the bound nodes; a registry resolves `(capability, model)`. **Acceptance**: Injection produces a valid concrete prompt for the LTX-2 slice.
- The capture helper produces a flat API-format template for the LTX-2 t2v workflow.
- Injecting prompt/seed/size/length/fps/steps/negative/audio sets the bound nodes (verified by unit tests).
- The registry resolves `(text_to_video, ltx2-t2v)` → template + binding + expected model files.

### ✅ Step 3.1: Template capture helper
- **What**: Add a `scripts/` helper that captures/refreshes an API-format template, supporting both the ComfyUI Dev-Mode Export(API) artifact and the programmatic print-prompt conversion route. Document which to run once.
- **Deliverables**: `scripts/capture_template.py` (or `.ps1`), `docs/` capture note.
- **Dependencies**: 2.1

### ✅ Step 3.2: Capture LTX-2 template & document bindings
- **What**: Run the helper once against the source UI workflow `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` (Appendix A) to store the LTX-2 t2v API template, then record the node `_meta.title`/role for each typed param (prompt, negative, seed, size, length, fps, steps, audio).
- **Deliverables**: `workflows/ltx2_t2v.api.json` (captured from `video_ltx2_t2v.json`), `docs/` bindings note.
- **Dependencies**: 3.1

### ✅ Step 3.3: Parameter injection engine
- **What**: Given typed inputs, address nodes by `_meta.title`/role (not numeric IDs), set widget values, and write the concrete prompt to a temp file for the driver. Leave unset params at template defaults.
- **Deliverables**: `core/injection.py` (bind-and-set, temp-file writer).
- **Dependencies**: 3.2

### ✅ Step 3.4: Workflow registry
- **What**: A minimal mapping keyed by `(capability_id, model_id)` → template path + binding + expected model files. This is the single seam for a later capability — no plugin discovery.
- **Deliverables**: `core/registry.py`.
- **Dependencies**: 3.2

## ✅ Phase 4: text_to_video adapter + commands end-to-end (mocked comfy)
> Wire the three commands so the slice runs against a mocked `comfy` with full contract output.

**Milestone**: `doctor`, `capabilities`, and `generate` all function; `generate` injects → runs → collects → writes provenance → emits a path or envelope. **Acceptance**: The vertical slice is complete against a faked runner and temp dirs.
- A `generate` request (model `ltx2-t2v`, with `--json`) emits exactly one valid envelope (§4.2) with `artifacts[0].path` and embedded metadata.
- Human mode's final stdout line is the absolute artifact path; diagnostics go to stderr.
- `doctor` and `capabilities` each emit a single object in `--json` mode.
- The adapter↔core interface is modality-agnostic: a hypothetical second capability (another video model, or a non-video modality such as image/audio) would need only a new adapter + template + binding, with no change to `core/`.

### ✅ Step 4.1: text_to_video adapter
- **What**: Declare the `capability_id`, the `ltx2-t2v` model, the typed param schema (the full shared video surface), and the `video/mp4` artifact type. Resolve params and delegate to injection + driver; optional pydantic schema. The schema accepts length as both `--length <frames>` and `--seconds` (frames↔seconds mapping resolved against the template's frame-count node). Keep the adapter↔core interface modality-agnostic — the artifact type and param schema are declared by the adapter, never hardcoded in `core/` — so future video and non-video capabilities reuse the same core unchanged.
- **Deliverables**: `capabilities/video/text_to_video/` (adapter, param schema, `generate` registration).
- **Dependencies**: 3.3, 3.4, 2.3

### ✅ Step 4.2: Output & provenance writer
- **What**: Move/copy the driver-reported file into `--output-dir` with a collision-safe name; write the `<artifact>.json` sidecar with the §4.4 fields (prompt, negative, seed, capability, model/workflow id + template version, resolved params, ComfyUI version, model file names, start/end timestamps, output filename) and embed the same record as `artifacts[].metadata`.
- **Deliverables**: `core/output.py` (collision-safe naming, mover, provenance writer).
- **Dependencies**: 2.3

### ✅ Step 4.3: generate command
- **What**: Parse the shared options, validate, resolve via the adapter, run through the driver, collect outputs, write provenance, then print the path (human mode) or the one envelope (`--json`).
- **Deliverables**: `generate` wiring across `core/cli.py` and the adapter.
- **Dependencies**: 4.1, 4.2, 1.4

### ✅ Step 4.4: doctor command
- **What**: Check that the GPU/CUDA stack is usable, that `comfy` is on PATH and a local ComfyUI is reachable/launchable, and that the LTX-2 model files (Appendix A) are present. Report the `comfy`/comfy-cli version and enforce the pinned minimum. Emit a single object in `--json` mode.
- **Deliverables**: `core/doctor.py`, `doctor` wiring in `core/cli.py`.
- **Dependencies**: 2.2, 3.4, 1.4

### ✅ Step 4.5: capabilities command
- **What**: List registered capabilities and their models/templates from the registry. Emit a single object in `--json` mode.
- **Deliverables**: `capabilities` wiring in `core/cli.py`.
- **Dependencies**: 3.4, 1.4

## ✅ Phase 5: GPU-free unit suite & docs
> Comprehensive green tests with `comfy` mocked, plus README/docs for the contract.

**Milestone**: The unit suite passes with no GPU, no real ComfyUI, and no network; docs cover the contract, exit codes, config, and template capture. **Acceptance**: The offline suite is green and the docs are caller-ready.
- Tests cover injection, output collection/naming, provenance, error→exit mapping, config layering, and envelope shape.
- The suite runs green fully offline.
- The README documents the grammar, the `--json` envelope, exit codes, config keys, and the consumer integration pattern.

### ✅ Step 5.1: Mock harness & fixtures
- **What**: Provide canned `comfy` envelopes (success plus each failure `error.code`) and exit codes that feed the runner seam, with temp-dir helpers. This harness is what the earlier phases verify against.
- **Deliverables**: `tests/` fixtures and harness.
- **Dependencies**: 2.1

### ✅ Step 5.2: Unit tests across modules
- **What**: Assert injection into the template, temp-file handoff, output collection + collision-safe naming, provenance contents, error→exit mapping, config layering, and the `--json` envelope shape. Describe each test by purpose, not identifier.
- **Deliverables**: `tests/` for `core/` and the adapter.
- **Dependencies**: 5.1, 4.3, 4.4, 4.5

### ✅ Step 5.3: README & docs
- **What**: Document the §4 contract, the exit-code taxonomy, config/env keys, template capture/refresh, the Service Bus integration pattern (§9), and a short "How to add a capability" note — the modality-agnostic adapter + template + binding recipe — covering both additional video models and non-video modalities.
- **Deliverables**: `README.md`, `docs/`.
- **Dependencies**: 4.3

## ✅ Phase 6: Real-GPU end-to-end validation
> Prove the definition of done on the RTX 5090.

**Milestone**: A real `generate` — backed by the source workflow `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json` (captured to API format in Phase 3) — produces a playable `.mp4`; a second reuses the warm server without reloading models. **Acceptance**: The end-to-end slice works on the target machine.
- `doctor` reports the environment ready on the target machine.
- A real `generate` request in `--json` mode, running the capability captured from `video_ltx2_t2v.json`, yields one envelope whose `artifacts[0].path` is a playable `.mp4`.
- A second `generate` reuses the warm server with no multi-tens-of-GB model reload.

### ✅ Step 6.1: Opt-in integration test
- **What**: Add an env-gated test that drives the real `comfy`/ComfyUI and asserts a real `.mp4` is produced. It is skipped by default so the suite stays GPU-free.
- **Deliverables**: `tests/` integration test (env-flag gated).
- **Dependencies**: 4.3

### ✅ Step 6.2: Real end-to-end validation
- **What**: On the RTX 5090, confirm the stored LTX-2 template captured from `C:\AI\Softwares\user\default\workflows\video_ltx2_t2v.json`, run `doctor`, then a real `generate`; confirm one envelope parses and the `.mp4` plays.
- **Deliverables**: Validation run notes.
- **Dependencies**: 6.1, 3.2

### ✅ Step 6.3: Keep-warm verification
- **What**: Issue a second `generate` against the warm server and confirm no model reload (fast path). Tune attach-vs-launch / keep-warm config defaults as needed.
- **Deliverables**: Keep-warm confirmation notes; finalized config defaults.
- **Dependencies**: 6.2

## Risks & Mitigations
| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Exact LTX-2 node titles/roles for injection are unknown | High | Med | Capture the API template early (3.1–3.2) and bind from the real graph; if a node lacks a title, add one in ComfyUI before export or bind by class_type + role. |
| Valid param ranges/defaults undecided (spec open question) | Med | High | Seed defaults from the template's existing widget values; validate format in the adapter; start permissive (clamp-vs-reject decided per param) and leave unset params at template defaults. |
| How `comfy run` reports the produced `.mp4` path | High | Med | Confirm the envelope shape empirically during 2.3/6.2; keep all parsing in the driver; fall back to scanning the ComfyUI output dir if the envelope lacks it. |
| comfy-cli version floor for the json/local-paths/print-prompt behavior | Med | Med | Pin a verified minimum during the driver build; have `doctor` report the `comfy` version; isolate all quirks in the driver. |
| sm_120 (Blackwell) needs a cu128 torch stack | High | Low | No GPU code here; rely on ComfyUI's own cu128 venv; `doctor` verifies torch CUDA is usable. |
| Subgraph UI workflow is awkward to inject into | Med | Med | Store a flat API-format template (the purpose of Phase 3 capture); never inject into UI/subgraph JSON. |
| Keep-warm not actually reusing loaded models | Med | Low | Attach to the same host/port across calls; verify warm reuse in 6.3 before sign-off. |

## Open Questions
- The exact `_meta.title`/role strings for prompt, negative, seed, size, length, fps, steps, and audio in the captured LTX-2 API template.
- Sensible default ranges per param and which to clamp vs reject; whether LTX-2 t2v honors a negative prompt or accepts-but-ignores it.
- The minimum comfy-cli version that emits the envelope and local output paths this design parses.
- The exact envelope field carrying the produced `.mp4` path, and whether local-paths yields absolute paths.
- Whether `--length` is expressed in frames and/or `--seconds`, and how that maps onto the template's frame-count node.

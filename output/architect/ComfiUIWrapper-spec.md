# ComfiUIWrapper — Spec

> A typed, scriptable command-line tool that turns a text prompt plus generation parameters into a locally-rendered video (LTX-2 text-to-video) on the user's own GPU, returning the finished file's path and a provenance record through a stable, machine-readable contract.

**Created**: 2026-06-30

## Goal

Give automated callers and operators a single, stable command that produces a local AI video from typed parameters — hiding ComfyUI's node graphs, model wiring, and tool-specific quirks behind a small, predictable interface — so a backend job (or a person) can request "make this video" and reliably get back a playable file, a result envelope, and a clear success/failure signal.

## Background & Context

Some local AI pipelines — notably LTX-2 audio+video text-to-video — are only runnable today through ComfyUI's node-graph engine and its model handling, not through a simple call. Running them means loading a hand-authored graph, knowing which node holds the prompt versus the seed versus the frame count, and managing a local server. That is too brittle and too specialized for any caller to take on directly.

An existing, actively-maintained tool (comfy-cli) already launches a headless local ComfyUI, runs a workflow, converts editor-format graphs to runnable form, tracks progress, and collects outputs. What it does not provide is a typed, capability-level surface ("generate a text-to-video clip with these parameters"), a stable result/error contract a program can depend on, or a provenance record of how each artifact was made.

The motivating use is an unattended backend job: a message arrives on an Azure Service Bus queue carrying a prompt and properties (seed, size, length, fps, audio); the job must render the clip locally on an RTX 5090 and hand back the result. The queue listener itself is out of scope — this tool is the seam it calls, so the messaging job never needs to understand ComfyUI.

## Users & Audience

- **Primary — an unattended machine caller** (e.g. the Service Bus-triggered backend job) that builds a command from message properties, parses one JSON result object, and branches on a numeric exit code to decide retry versus dead-letter.
- **Secondary — a human operator / developer** running ad-hoc generations or diagnosing the environment from a terminal.
- **Future — capability authors** who add new generation types (other models / modalities) without reworking the core.

## User-Facing Behavior

- **Generate a clip from a prompt** plus a first-class set of typed parameters: seed, size (width/height), length (frames or seconds), fps, steps, negative prompt, and audio on/off — for the LTX-2 text-to-video model.
- **Two output modes:** a human mode whose final line is the absolute path to the produced file, and a machine mode that emits exactly one JSON result object (capability, model, and a list of artifacts each with path, type, and embedded metadata); diagnostics stay separate from that result.
- **A provenance record** written alongside every artifact, capturing how it was produced.
- **An environment / readiness check** reporting whether the GPU stack, the local ComfyUI, and the required LTX-2 model files are usable.
- **A capabilities listing** reporting which generation types and model variants are available.
- **Keep-warm behavior:** the local ComfyUI is started once if needed and reused across calls, so repeated requests do not re-pay the multi-tens-of-GB model load.
- **A documented exit-code taxonomy** distinguishing transient failures (retry) from permanent ones (reject), so a caller can act without parsing prose.

## Success Criteria

- A machine caller can issue one generate request, parse exactly one JSON object from standard output, read the artifact path, and find a playable video file there.
- The same request exits zero on success and returns a documented, stable exit code for each failure class (bad parameters, backend unavailable, out of memory, timeout, unknown model, etc.), enabling automatic retry-versus-reject decisions.
- Every produced artifact has a matching provenance record containing at least the prompt, seed, model/workflow identity, resolved parameters, and start/end timestamps.
- A GPU-free automated test suite passes without a GPU, a real ComfyUI, or network access, covering parameter handling, the result-envelope shape, and failure-to-exit-code mapping.
- End-to-end on the RTX 5090, a real generate request produces a playable video from a prompt; a second request reuses the warm server without reloading models.
- Adding a new capability does not require changing the core orchestration.

## Non-Goals / Out of Scope

- The Azure Service Bus listener, message parsing, retry/dead-letter policy, artifact upload, and status reporting — these belong to the calling job, not this tool.
- Any graphical interface or interactive node editing.
- Model training or fine-tuning.
- A general "run any user-supplied graph" passthrough — capabilities are curated and typed.
- Cloud or hosted-model generation, including paid partner-node services; generation is local-GPU only with no CPU fallback.
- Reimplementing what the underlying execution tool already does (server lifecycle, graph conversion, progress tracking, output collection).
- Capabilities beyond the first text-to-video slice; other models / modalities are seams only in v1.

## Constraints

- **Local GPU only:** targets a single RTX 5090 (Blackwell) workstation and a CUDA 12.8+ class stack; no CPU fallback for real generation.
- **Build on the existing comfy-cli tool** rather than reimplementing ComfyUI orchestration; it is driven at arm's length so this project stays independent of any other repository.
- **Windows / PowerShell** is the target environment.
- **Self-contained** with respect to the user's other projects: it shares only its own command-line convention, depends on no sibling repo, and commits no secrets (tokens via environment only).
- The required LTX-2 model files are large (tens of GB total) and must already be present on the workstation.

## Open Questions

- What are the valid ranges and sensible defaults for the LTX-2 parameters (size, length, fps, steps), and which should be clamped versus rejected outright?
- Does the chosen LTX-2 text-to-video workflow meaningfully support a negative prompt, or should that input be accepted-but-ignored for this model?
- What minimum version of the underlying execution tool is required for the result-envelope and standard-output behavior this design depends on?

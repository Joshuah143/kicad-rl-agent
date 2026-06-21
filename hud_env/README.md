# kicad-schematics — HUD training environment

Kick off GRPO RL training runs where an LLM agent learns to generate
KiCad-quality circuit designs, graded by this repo's deterministic verifier.

This is a self-contained [HUD](https://hud.ai) v6 environment (its own `uv`
subproject) that wraps the `kicad-rl-agent` package. Verified against
**hud-python 0.6.6**.

## The environment model

- **Agent's job:** for a given task, emit a Python `build() -> Circuit` program
  (a string) in the project's constrained DSL. The full instructions are in the
  prompt (`circuit_agent.rl.prompts.build_prompt`).
- **Grader (our verifier):** the program is sandboxed
  (`circuit_agent.dsl.sandbox.run_program` → `CircuitModel`) and scored by
  `circuit_agent.infra.verifier.verify_design` (schema, ERC, graph/electrical
  rules, cost, size, availability). The reward is the verifier's
  **`reward_normalized`** ∈ `[0, 1]` — GRPO-ready, no reward-scale hack needed.
- **Fail-closed:** any unsafe/garbage/invalid program → reward `0.0`, no
  exception. The single grading path lives in `env.grade_program(task_name,
  program_text)`.
- **5 tasks:** `usb_c_5v_led`, `led_resistor`, `ldo_3v3`,
  `i2c_sensor_breakout`, `mcu_minimal` (one `tasks/<name>.yaml` each).

## Prerequisites

- **uv** (provisions Python 3.12 — `hud-python` caps `<3.13`, while the main
  repo stays on 3.13 via a path dependency).
- A **HUD account + API key** (`hud login` or `hud set HUD_API_KEY=...`).
- **KiCad** for local ERC (optional). The CLI is auto-detected; without it ERC
  is skipped (and excluded from the normalized max, so scores stay calibrated).
  Set `KICAD_RL_DISABLE_ERC=1` to force ERC off for faster rollouts.

## Setup

```bash
cd hud_env
uv sync                 # provisions py3.12 + hud-python + kicad-rl-agent (editable)
uv run hud login        # or: uv run hud set HUD_API_KEY=sk-hud-...
```

## Local eval (sanity check — no training)

```bash
uv run hud eval tasks.py claude --task-ids usb-c-5v-led --group 3
```

Task slugs: `usb-c-5v-led`, `led-resistor`, `ldo-3v3`, `i2c-sensor-breakout`,
`mcu-minimal`.

## Training

### Path A — HUD gateway TrainingClient (this repo's `train.py`)

The HUD gateway ships the **Qwen3 family** as the default trainables. Fork one
into a team-owned trainable, point `MODEL` in `train.py` at it, then train:

```bash
uv run hud models list
uv run hud models fork Qwen/Qwen3-4B --name kicad-rl-qwen3-4b   # edit MODEL in train.py
uv run train.py --local --steps 10        # serves env.py locally via LocalRuntime
# or, against a platform-hosted taskset:
uv run hud sync tasks.py                   # push the taskset once
uv run train.py --remote --steps 10
```

`train.py` flags: `--steps` (default 10), `--group` (GRPO group size, default 8),
`--learning-rate` (default 1e-5), `--local` (default) / `--remote`.

The loop: create a gateway agent (`completion_kwargs.extra_body.return_token_ids
= True` so per-token logprobs come back), `TrainingClient(MODEL)`, build the
taskset + runtime, then for each step `taskset.run(agent, runtime, group, job)`
→ `trainer.step(job.runs, learning_rate=..., group_size=...)`.

### Path B — Fireworks (only if you need Gemma)

**Gemma is NOT a pre-configured trainable on HUD's gateway.** To train Gemma you
need Path B: Fireworks RL, which ships Qwen3-8B with a validated training shape.
See `cookbooks/fireworks-rl-training`. This subproject implements Path A only.

## Reward shaping for GRPO

GRPO learns from **within-group variance**: with `--group N`, each task is rolled
out N times and the advantage is each rollout's reward minus the group mean. You
want a group mean roughly in the **0.2–0.5** band early on (lots of partial
credit, room to improve) — not 0 (no signal, the policy never stumbles into
reward) and not 1 (saturated, nothing to learn). Our reward is already a smooth
`reward_normalized` ∈ `[0, 1]` (schema/ERC/rules/cost/size/availability all
contribute fractionally), so groups naturally spread. If early groups collapse
to all-zero, shrink the task (fewer requirements) or warm-start the model;
if they saturate near 1, add harder tasks.

## How Modal fits (optional)

Modal only matters for **env hosting**, not training. Local training serves
`env.py` in a child process via `LocalRuntime` — no Modal, no Docker. To host the
environment remotely instead, use a `ModalRuntime`/`HUDRuntime` and authenticate
Modal (`modal token new`). The main package can also dispatch the *verifier
itself* to a Modal KiCad sandbox (`verify_design(..., use_modal=True)`), an
orthogonal feature this environment does not require.

## Remote deploy (optional)

For platform-hosted rollouts, build the image **from the repo root** (the build
context must reach `../src`):

```bash
docker build -f hud_env/Dockerfile.hud -t kicad-hud-env .
```

Local training/eval needs **no Docker**.

## Files

- `env.py` — the HUD `Environment`, the `kicad_design` template, and the
  reusable `grade_program` helper.
- `tasks.py` — the 5 `Task`s (with slugs/columns) + re-exported `env`.
- `train.py` — Path-A GRPO training script.
- `Dockerfile.hud` — remote hosting image (build from repo root).
- `pyproject.toml` / `.python-version` — the py3.12 uv subproject.
```

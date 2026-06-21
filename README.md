# kicad-rl-agent

An end-to-end reinforcement-learning loop that trains a **Gemma policy model (served by
[Fireworks AI](https://fireworks.ai/))** to emit a constrained **circuit DSL program**. That
program is compiled into KiCad schematic artifacts, scored by **deterministic validators** plus an
optional **Fireworks-hosted LLM critic**, and the resulting scalar **reward** drives the RL update.

The whole pipeline runs **locally** with only `pydantic` + `pyyaml` (mock policy, hand-rolled SVG
visual, validators). KiCad ERC, real Fireworks sampling/critic, Modal sandboxing, and PDF rendering
are all optional add-ons that degrade gracefully when their dependency is missing.

---

## What it is

A research scaffold for *learning to design circuits* rather than hand-writing them. A language
model proposes a circuit as a small Python program against a safe builder API; the system turns that
proposal into something a tool (KiCad) and a set of rules can judge objectively, and feeds the score
back to the model. Nothing is rewarded for merely *looking* plausible — the critic and validators are
deliberately conservative.

---

## Architecture

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                     reward (scalar)                          │
                          │                          ▲                                    │
  ┌──────────────┐        │   ┌───────────────┐      │                                    │
  │  Gemma policy │  DSL   │   │  DSL sandbox  │      │      ┌────────────────────────┐    │
  │  (Fireworks)  ├───────►│   │  run_program  ├──► CircuitModel ─► compile_schematic ─┼──► .kicad_pro / .kicad_sch
  └──────┬───────┘  code   │   └───────────────┘      │      └───────────┬────────────┘    │
         │ RL update        │                          │                  │                 │
         │ (Fireworks RFT)  │   ┌──────────────────────┴───────────┐      ▼                 │
         │                  │   │ deterministic validators         │  KiCad CLI ERC         │
         │                  │   │  graph_rules / electrical_rules  │  + SVG/PDF export      │
         │                  │   │  bom_cost / package_size / avail │      │                 │
         │                  │   └──────────────────────┬───────────┘      │                 │
         │                  │                          │                  ▼                 │
         │                  │   ┌──────────────────────┴───────┐   hand-rolled SVG graph    │
         │                  │   │  LLM critic (Fireworks, opt.) │   (always available)       │
         │                  │   └──────────────────────────────┘                            │
         └──────────────────┴─────────────────────────────────────────────────────────────┘
                       Modal = sandbox to run KiCad + validators at scale (optional)
```

Flow, concretely:

1. **Policy → DSL program.** The Gemma model (via Fireworks) is prompted with the task and the
   builder API reference and returns *only* Python that defines `build() -> Circuit`.
2. **Sandbox → CircuitModel.** `dsl/sandbox.py` AST-checks the program (no imports, no dunder access,
   no `os`/`sys`/`subprocess`/…) then `exec`s it in a subprocess and serializes the result to a
   validated Pydantic v2 `CircuitModel`.
3. **Compiler → KiCad project.** `kicad/compile_schematic.py` emits a minimal `.kicad_pro` and a
   `.kicad_sch` s-expression using generic rectangular symbols and **global labels** for electrical
   connectivity (no geometric wire routing yet — see roadmap). This stage is marked EXPERIMENTAL; the
   hand-rolled SVG graph is the reliable visual.
4. **KiCad CLI → ERC + visuals.** When `kicad-cli` is installed, `kicad/run_kicad_cli.py` runs ERC to
   a JSON report and exports SVG/PDF. If KiCad is missing, ERC is skipped (never a hard error).
5. **Deterministic validators → structured results.** `graph_rules`, `electrical_rules`, `bom_cost`,
   `package_size`, `availability` produce `ValidatorResult`/dicts. Given identical inputs they produce
   identical outputs — no wall-clock, no randomness.
6. **LLM critic → CriticResult (optional).** A conservative reviewer (stub or Fireworks) that will not
   reward plausible-but-wrong designs.
7. **Reward.** `validators/reward.py::compute_reward` combines everything into a single deterministic
   `reward` dict using the task's objective weights.
8. **RL update.** Candidates + rewards are logged; `FireworksBackend.update` exports an RFT-style
   JSONL dataset for **Fireworks Reinforcement Fine-Tuning** (job launch is a documented TODO).

---

## Fireworks-centric design

Everything that needs a model goes to **Fireworks AI** via its **OpenAI-compatible REST endpoint**
(`POST {base_url}/chat/completions`, `Authorization: Bearer …`) using `requests`. There is **no
Anthropic/OpenAI-vendor code anywhere**.

- **Policy sampling** — the Gemma policy is sampled through `infra/fireworks_client.py`
  (`FireworksBackend`).
- **LLM critic** — `validators/llm_critic.py::FireworksCritic` calls the same endpoint with a strict
  JSON-output, conservative system prompt.
- **RL fine-tuning** — rewards + completions are exported as a Fireworks RFT dataset for fine-tuning
  the same Gemma model.

**Modal** is used **only** as a sandbox to run KiCad + the validators at scale
(`infra/modal_app.py`). Everything also runs locally with a locally-installed `kicad-cli`.

---

## Install

Requires **Python 3.11+**.

```bash
# core runtime (mock policy + local validators + SVG visual): pydantic + pyyaml only
pip install -e .

# or grab the out-of-the-box set (core + Fireworks client + tests):
pip install -r requirements.txt

# optional extras, install on demand:
pip install -e ".[fireworks]"   # requests  -> real Fireworks sampling + critic
pip install -e ".[modal]"       # modal     -> KiCad/validator sandbox
pip install -e ".[pdf]"         # cairosvg  -> high-fidelity SVG -> PDF
pip install -e ".[dev]"         # pytest
```

The entry scripts and tests prepend `src/` to `sys.path`, so they run **without** an install too.

### KiCad (for ERC + native export)

KiCad is **optional** — when absent, ERC is skipped and the hand-rolled SVG is still produced.

- **macOS:** install KiCad.app; the CLI is auto-detected at
  `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`.
- **Linux:** `apt install kicad` (or your distro's package); `kicad-cli` on `PATH`.
- **Windows:** installed under `C:\Program Files\KiCad\<ver>\bin\kicad-cli.exe` (auto-detected).

ERC is invoked as a subprocess, equivalent to:

```bash
kicad-cli sch erc --output erc.rpt --format json design.kicad_sch
```

The JSON report is parsed by `kicad/parse_erc.py` into an `ERCResult` (`error_count`,
`warning_count`, `violations`). KiCad version target is recent stable (KiCad 8, s-expr
`version 20231120`).

---

## Environment variables

| Variable             | Purpose                                                        | Default                                       |
| -------------------- | -------------------------------------------------------------- | --------------------------------------------- |
| `FIREWORKS_API_KEY`  | Required only for real Fireworks sampling / critic / RFT       | unset (mock + local paths still work)         |
| `FIREWORKS_BASE_URL` | OpenAI-compatible Fireworks endpoint                           | `https://api.fireworks.ai/inference/v1`       |

**Model aliases** (`config.py::MODEL_ALIASES`) map friendly names to Fireworks model ids:

```python
{
  "gemma4":  "accounts/fireworks/models/gemma-3-27b-it",   # PLACEHOLDER — adjust!
  "gemma":   "accounts/fireworks/models/gemma-3-27b-it",
  "critic":  "accounts/fireworks/models/qwen2p5-72b-instruct",
}
```

> **Note:** `"gemma4"` maps to a **placeholder** Fireworks model id. "Gemma 4" may not exist on
> Fireworks yet — edit `MODEL_ALIASES` to the exact model id your account has access to. Any value
> containing a `/` is treated as a literal model id and used as-is.

---

## Usage

### Headline command

```bash
python train_or_rollout.py \
  --task tasks/usb_c_5v_led.yaml \
  --model gemma4 \
  --backend hud \
  --n_candidates 8 \
  --out runs/usb_c_5v_led_001
```

`--backend hud` is a documented **stub**: it fails with a clear, actionable message (use
`--backend mock` for offline, or `--backend fireworks` for the real policy) rather than a traceback.
Add `--train --iters 3` to run the RL training loop instead of a single rollout. Flags:
`--backend {mock,fireworks,hud}` (default `fireworks`), `--kicad/--no-kicad` (default auto-detect),
`--critic {none,stub,fireworks}` (default `stub`), `--modal`.

### MVP mock command (no network, no KiCad required)

```bash
python scripts/rollout_once.py --task tasks/usb_c_5v_led.yaml --backend mock --n_candidates 3
```

The mock backend draws candidate programs from the hand-written reference circuits in
`dsl/examples.py`, so the full rollout → validate → reward → log loop runs entirely offline.

### Other scripts

```bash
# validate a single design (circuit.json OR a .py build() program) against a task
python scripts/validate_design.py --design runs/.../best/circuit.json --task tasks/usb_c_5v_led.yaml

# compile + export SVG/PDF for a design
python scripts/export_design.py --design path/to/design.{json,py} --out out/ --kicad
```

---

## Artifact layout

A rollout writes one directory per candidate plus a `best/` copy:

```
runs/usb_c_5v_led_001/
├── training_log.jsonl              # one record per candidate {task,prompt,completion,valid,reward,...}
├── cand_000/
│   ├── program.py                  # the raw model completion (build() program)
│   ├── circuit.json                # the validated CircuitModel
│   ├── design.kicad_pro            # minimal KiCad project (EXPERIMENTAL emitter)
│   ├── design.kicad_sch            # KiCad schematic s-expression
│   ├── erc.rpt                     # KiCad ERC JSON report (only if KiCad available)
│   ├── schematic.svg               # hand-rolled net graph (ALWAYS produced)
│   ├── schematic.pdf               # best-effort PDF (cairosvg / KiCad; may be absent)
│   ├── bom.json                    # bill-of-materials cost breakdown
│   ├── critic.json                 # LLM/stub critic result ({} if no critic)
│   └── reward.json                 # the deterministic reward dict
├── cand_001/ …
├── cand_002/ …
└── best/                           # contents of the highest-reward valid candidate
```

The `reward.json` shape:

```jsonc
{
  "reward": 11.42,
  "passed": true,
  "breakdown": { "schema_valid": 1.0, "erc": 3.0, "graph_rules": 2.0,
                 "electrical_rules": 4.0, "cost": 1.0, "size": 0.5,
                 "availability": 0.95, "llm_critic": 1.7 },
  "fatal_errors": [],
  "warnings": ["ERC skipped (KiCad unavailable)"],
  "metrics": { "total_cost_usd": 0.71, "total_area_mm2": 88.0,
               "min_availability": 0.9, "smt_count": 4, "tht_count": 0 }
}
```

---

## MVP success criteria

- `pip install -e .` succeeds with only `pydantic` + `pyyaml`.
- The mock command runs offline end-to-end and writes `cand_NNN/` + `best/` artifacts with a
  `reward.json` for each candidate.
- A `schematic.svg` is produced for every candidate **without** KiCad installed, with power nets
  (GND/+5V/+3V3/VBUS/…) highlighted.
- The validators are deterministic: re-running the reward on identical inputs yields an identical
  dict.
- The `usb_c_5v_led` reference circuit passes the electrical rules (5.1k Rd pulldowns on both CC1 and
  CC2), and a USB-C design missing a CC pulldown is flagged FATAL.
- `--backend hud` fails with a friendly message, not a traceback.

Run the test suite:

```bash
pytest
```

---

## Enabling real Fireworks sampling / critic and Modal

1. **Fireworks** — install the client and set credentials:

   ```bash
   pip install -e ".[fireworks]"
   export FIREWORKS_API_KEY=fw_...
   # optionally override the endpoint / point aliases at your models in config.py
   python scripts/rollout_once.py --task tasks/usb_c_5v_led.yaml \
       --backend fireworks --model gemma4 --critic fireworks --n_candidates 8 --out runs/fw_001
   ```

   Missing key/dependency raises a **clear, actionable** error only when the policy/critic is actually
   invoked — never on import, never on the mock path.

2. **RL fine-tuning (Fireworks RFT)** — `FireworksBackend.update` exports completions + rewards to an
   RFT-style JSONL dataset (default `out/rft_dataset.jsonl`). Launching the actual
   `firectl create rft` job using that dataset + this reward is a documented stub
   (`launch_rft_job`) and is the next integration step.

3. **Modal sandbox** — KiCad + validators at scale:

   ```bash
   pip install -e ".[modal]"
   modal token new
   modal run src/circuit_agent/infra/modal_app.py
   # or pass --modal to the rollout to dispatch verification into the Modal container
   ```

   `infra/modal_app.py` is the **only** place Modal is used; the rest of the system imports it
   lazily and falls back to local verification if Modal is unavailable.

---

## Tasks

YAML task specs live in `tasks/` and match `task.py::TaskSpec` (objective weights, preferences such
as `package_type`/`max_bom_cost_usd`/`max_area_mm2`, and `allowed_parts` that reference `parts_db`
keys):

- `led_resistor.yaml` — an LED + current-limiting resistor.
- `ldo_3v3.yaml` — a 3.3 V LDO with input/output decoupling.
- `usb_c_5v_led.yaml` — USB-C 5 V sink with power LED (requires 5.1k Rd on CC1 **and** CC2).
- `i2c_sensor_breakout.yaml` — generic I²C sensor with SDA/SCL pullups.
- `mcu_minimal.yaml` — minimal MCU with decoupling caps.

---

## Repository layout

```
src/circuit_agent/
├── dsl/          schema (CircuitModel), builder (Circuit), sandbox, examples
├── data/         symbols, footprints, parts_db catalogs
├── validators/   base types, value parsing, graph/electrical rules, bom/size/avail, reward, llm_critic
├── kicad/        compile_schematic, run_kicad_cli, parse_erc, export_visuals
├── infra/        fireworks_client, verifier, modal_app
├── rl/           prompts, backends (mock/hud/fireworks), factory, rollout, train_loop
├── config.py     settings + model aliases
└── task.py       TaskSpec
scripts/          rollout_once.py, validate_design.py, export_design.py
train_or_rollout.py   headline entrypoint
tasks/            *.yaml task specs
tests/            pytest suite
```

---

## Roadmap

The current compiler emits generic symbols and connects nets via global labels (no geometric
routing). Planned work:

- **True KiCad-native schematics** — real symbol-library resolution and geometric wire routing (the
  compiler exposes an abstraction seam so a native compiler can be swapped in).
- **PCB layout** — board outline + layer stack generation from the validated netlist.
- **Component placement** — heuristic/RL-driven placement scored on area, thermals, and routability.
- **Routing & autorouter** — net routing with DRC feedback folded into the reward.
- **Launching real Fireworks RFT jobs** from the exported dataset (`launch_rft_job`).
- **Richer parts/symbol catalogs** and an expanded electrical-rule library.
```

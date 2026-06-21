"""Path-A GRPO training for the kicad-schematics environment (HUD gateway).

This trains a HUD *Trainable* gateway model to emit KiCad-quality build()
programs, graded by our deterministic verifier (reward already normalized to
0..1 by the grader — no reward_scale hack needed).

=============================================================================
FULL SETUP SEQUENCE
=============================================================================
1. Provision the subproject (python 3.12 + hud-python + our package):

       cd hud_env
       uv sync

2. Authenticate with HUD (either of these):

       uv run hud login
       # or:
       uv run hud set HUD_API_KEY=sk-hud-...

3. Pick / create a TRAINABLE model. HUD's gateway ships the Qwen3 family as the
   default trainables; fork one into a team-owned trainable you can update:

       uv run hud models list
       uv run hud models fork Qwen/Qwen3-4B --name kicad-rl-qwen3-4b
       # then set MODEL below to "kicad-rl-qwen3-4b" (the forked name).

   NOTE: Gemma is NOT a pre-configured trainable on HUD's gateway. To train
   Gemma you need Path B (Fireworks, which ships Qwen3-8B with a validated
   training shape) — see cookbooks/fireworks-rl-training. This script is Path A
   (HUD gateway TrainingClient) only.

4. (Optional) Modal only matters for *env hosting* (ModalRuntime). Local
   training serves env.py in a child process via LocalRuntime — no Modal needed:

       modal token new      # only if you host the env on Modal

5. Sanity-check with a local eval (no training, cheap):

       uv run hud eval tasks.py claude --task-ids usb-c-5v-led --group 3

6. Train locally (env served from this file, model trained via the gateway):

       uv run train.py --local --steps 10

=============================================================================
API NOTES (verified against hud-python 0.6.6)
=============================================================================
- agent:    hud.agents.create_agent(MODEL, completion_kwargs={...})
            -> a GatewayAgent routed through the HUD gateway. The cookbook
               requires extra_body return_token_ids=True so the trainer gets
               per-token ids/logprobs back from the rollouts.
- trainer:  hud.TrainingClient(MODEL)
            .step(trajectories, *, learning_rate, group_size=...) chains one
            forward_backward + one optim_step (GRPO importance-sampling loss is
            the default loss_fn). It accepts a Sequence of Run objects — which is
            exactly what a finished Job exposes via ``job.runs``.
- rollouts: Taskset.run(agent, runtime=..., group=N, job=job) runs every task N
            times (the GRPO group) and returns the Job populated with Runs.
- runtime:  LocalRuntime("env.py") serves THIS env in a child process (local);
            HUDRuntime() runs against an environment hosted on the platform.
- reward:   already 0..1 (grader's reward_normalized) -> reward_scale stays 1.0.

If a live run errors on auth/network, the failure is at runtime — this module
still IMPORTS cleanly and is a faithful Path-A template.
"""

from __future__ import annotations

import argparse
import asyncio

# -----------------------------------------------------------------------------
# Constants — EDIT THESE.
# -----------------------------------------------------------------------------
# A HUD gateway TRAINABLE model name. Forked from Qwen/Qwen3-8B (Tinker) via:
#   hud models fork Qwen/Qwen3-8B --name kicad-rl-8b
# Qwen3-8B is a REASONING model (emits <think>...</think> then the code); the env
# grader strips that preamble and MAX_TOKENS must be large enough for it to finish
# thinking AND emit the program. (Qwen3.5-4B rambled without converging -> all 0.)
MODEL = "kicad-rl-8b"

# Sampling budget per rollout. Reasoning models need ~3k tokens to think + emit
# code; too low truncates them mid-thought -> unparseable -> reward 0.
MAX_TOKENS = 4096

# Remote taskset name on the HUD platform (used with --remote). Push tasks with
#   hud sync tasks.py
# For local training (--local, the default) this is ignored; we build the
# Taskset in-process from tasks.py.
TASKSET = "kicad-schematics"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Path-A GRPO training for kicad-schematics.")
    p.add_argument("--steps", type=int, default=10, help="number of optimizer steps")
    p.add_argument("--group", type=int, default=8, help="GRPO group size (rollouts per task)")
    p.add_argument("--learning-rate", type=float, default=1e-5, help="optimizer learning rate")
    p.add_argument("--max-tokens", type=int, default=MAX_TOKENS, help="sampling budget per rollout")
    p.add_argument("--tasks", type=str, default=None,
                   help="comma-separated task slugs to train on (default: all)")
    p.add_argument("--out", type=str, default="runs",
                   help="directory for metrics.jsonl + summary")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--local", dest="local", action="store_true",
                      help="serve env.py locally via LocalRuntime (default)")
    mode.add_argument("--remote", dest="local", action="store_false",
                      help="use the platform-hosted taskset + HUDRuntime")
    p.set_defaults(local=True)
    return p.parse_args()


def build_taskset_and_runtime(local: bool, tasks_filter: "set[str] | None"):
    """Return (taskset, runtime, slugs) for either local or remote training."""
    from hud import Taskset, LocalRuntime, HUDRuntime

    if local:
        from tasks import tasks as task_list

        taskset = Taskset("kicad-schematics", task_list)
        runtime = LocalRuntime("env.py")
    else:
        # HUDRuntime is REQUIRED for training: the agent runs remotely next to the
        # env and the rollouts carry per-token ids/logprobs ("trainable turns").
        # HostedRuntime returns rewards only -> trainer.step: "no trainable turns".
        # (The cookbook's load_taskset_and_runtime uses HUDRuntime for remote.)
        taskset = Taskset.from_api(TASKSET)
        runtime = HUDRuntime()

    if tasks_filter:
        kept = [t for t in taskset if (getattr(t, "slug", None) or getattr(t, "id", "")) in tasks_filter]
        taskset = Taskset("kicad-schematics", kept)

    slugs = [getattr(t, "slug", None) or getattr(t, "id", "?") for t in taskset]
    return taskset, runtime, slugs


def build_agent(max_tokens: int):
    """Create the GRPO policy agent routed through the HUD gateway."""
    from hud.agents import create_agent

    # return_token_ids is REQUIRED for training (records token ids + logprobs).
    return create_agent(
        MODEL,
        completion_kwargs={
            "max_tokens": max_tokens,
            "extra_body": {"return_token_ids": True},
        },
    )


def _step_metrics(batch, slugs, group):
    """Compute GRPO-relevant metrics for one step's rollouts.

    ``batch`` is task-major then group, so consecutive ``group`` runs are one
    task's GRPO group. Within-group reward spread is the signal GRPO learns from:
    a task whose group is all-same (saturated ~1 or all-fail ~0) contributes ~no
    gradient; learnable tasks sit in between.
    """
    import statistics as st

    rewards = []
    for r in batch:
        v = getattr(r, "reward", None)
        rewards.append(float(v) if v is not None else 0.0)

    groups = [rewards[i:i + group] for i in range(0, len(rewards), group)]
    per_task = {}
    within = []
    learnable = []
    for i, g in enumerate(groups):
        if not g:
            continue
        slug = slugs[i] if i < len(slugs) else f"group_{i}"
        m = st.mean(g)
        sd = st.pstdev(g) if len(g) > 1 else 0.0
        per_task[slug] = {"mean": round(m, 4), "std": round(sd, 4), "max": round(max(g), 4)}
        within.append(sd)
        if 0.0 < m < 1.0 and sd > 0.02:
            learnable.append(slug)

    return {
        "n_rollouts": len(rewards),
        "n_valid": sum(1 for x in rewards if x > 0.0),
        "mean_reward": round(st.mean(rewards), 4) if rewards else 0.0,
        "std_reward": round(st.pstdev(rewards), 4) if len(rewards) > 1 else 0.0,
        "max_reward": round(max(rewards), 4) if rewards else 0.0,
        "within_group_var": round(st.mean(within), 4) if within else 0.0,
        "learnable_task_count": len(learnable),
        "learnable_tasks": learnable,
        "per_task": per_task,
    }


async def train(args: argparse.Namespace) -> None:
    import json
    import time
    from pathlib import Path
    from hud import Job, TrainingClient

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    metrics_path = out / "metrics.jsonl"
    tasks_filter = set(s.strip() for s in args.tasks.split(",")) if args.tasks else None

    agent = build_agent(args.max_tokens)
    trainer = TrainingClient(MODEL)
    taskset, runtime, slugs = build_taskset_and_runtime(args.local, tasks_filter)

    print(f"[train] model={MODEL} tasks={len(slugs)} group={args.group} "
          f"steps={args.steps} max_tokens={args.max_tokens} -> {metrics_path}", flush=True)

    job = await Job.start("kicad-grpo", group=args.group)
    job_url = f"https://hud.ai/jobs/{getattr(job, 'id', '?')}"
    print(f"[train] job: {job_url}", flush=True)

    start = time.time()
    consecutive_failures = 0
    for step in range(args.steps):
        t0 = time.time()
        rec = {"step": step + 1, "of": args.steps, "elapsed_s": round(time.time() - start, 1)}
        try:
            prev = len(job.runs)
            job = await taskset.run(agent, runtime=runtime, group=args.group, job=job)
            batch = list(job.runs)[prev:]

            metrics = _step_metrics(batch, slugs, args.group)
            result = await trainer.step(
                job.runs[prev:],
                learning_rate=args.learning_rate,
                group_size=args.group,
            )
            rec.update(metrics)
            rec["optim"] = repr(result)[:300]
            rec["step_s"] = round(time.time() - t0, 1)
            rec["ok"] = True
            consecutive_failures = 0

            print(
                f"[step {step + 1}/{args.steps}] "
                f"mean={metrics['mean_reward']:.3f} max={metrics['max_reward']:.3f} "
                f"within_grp_var={metrics['within_group_var']:.3f} "
                f"learnable={metrics['learnable_task_count']}/{len(slugs)} "
                f"valid={metrics['n_valid']}/{metrics['n_rollouts']} "
                f"({rec['step_s']:.0f}s)",
                flush=True,
            )
        except Exception as exc:  # keep the run alive across transient/network failures
            consecutive_failures += 1
            rec["ok"] = False
            rec["error"] = f"{type(exc).__name__}: {exc}"
            rec["step_s"] = round(time.time() - t0, 1)
            print(f"[step {step + 1}/{args.steps}] ERROR ({consecutive_failures}): {rec['error']}", flush=True)
            # Backoff so a network outage / laptop-sleep blip doesn't burn through
            # steps in seconds; gives the connection time to recover. Each completed
            # step already checkpointed, so we never lose trained progress.
            backoff = min(30 * consecutive_failures, 300)
            print(f"[train] backing off {backoff}s before next attempt...", flush=True)
            await asyncio.sleep(backoff)

        with metrics_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

        if consecutive_failures >= 10:
            print("[train] 10 consecutive failures — stopping (network likely down).", flush=True)
            break

    print(f"[train] done. metrics -> {metrics_path}", flush=True)


def main() -> None:
    args = parse_args()
    asyncio.run(train(args))


if __name__ == "__main__":
    main()

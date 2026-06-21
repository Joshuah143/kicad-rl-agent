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
# A HUD gateway TRAINABLE model name. Forked from Qwen/Qwen3.5-4B (Tinker) via:
#   hud models fork Qwen/Qwen3.5-4B --name kicad-rl
# (Re-fork a different trainable base and change this slug to switch policy model.)
MODEL = "kicad-rl"

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
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--local",
        dest="local",
        action="store_true",
        help="serve env.py locally via LocalRuntime (default)",
    )
    mode.add_argument(
        "--remote",
        dest="local",
        action="store_false",
        help="use the platform-hosted taskset + HUDRuntime",
    )
    p.set_defaults(local=True)
    return p.parse_args()


def build_taskset_and_runtime(local: bool):
    """Return (taskset, runtime) for either local or remote training."""
    from hud import Taskset, LocalRuntime, HUDRuntime

    if local:
        # Build the taskset in-process and serve env.py in a child process.
        from tasks import tasks as task_list

        taskset = Taskset("kicad-schematics", task_list)
        runtime = LocalRuntime("env.py")
    else:
        # Pull the registered taskset from the platform; run on a hosted env.
        taskset = Taskset.from_api(TASKSET)
        runtime = HUDRuntime()
    return taskset, runtime


def build_agent():
    """Create the GRPO policy agent routed through the HUD gateway."""
    from hud.agents import create_agent

    # The trainer needs per-token ids back from each rollout; the cookbook sets
    # this via the OpenAI-compatible extra_body on the completion call.
    return create_agent(
        MODEL,
        completion_kwargs={"extra_body": {"return_token_ids": True}},
    )


async def train(args: argparse.Namespace) -> None:
    from hud import Job, TrainingClient

    agent = build_agent()
    trainer = TrainingClient(MODEL)
    taskset, runtime = build_taskset_and_runtime(args.local)

    # One Job groups all the steps' rollouts under a single run on the platform.
    job = Job.start(name="kicad-grpo", group=args.group)

    for step in range(args.steps):
        # Roll out every task `group` times; the finished Job carries the Runs.
        job = await taskset.run(
            agent,
            runtime=runtime,
            group=args.group,
            job=job,
        )

        # Our reward is already normalized 0..1, so reward_scale=1.0 (default).
        # `job.runs` is the Sequence[Run] the trainer's step() consumes.
        result = trainer.step(
            job.runs,
            learning_rate=args.learning_rate,
            group_size=args.group,
        )
        print(f"[step {step + 1}/{args.steps}] mean_reward={job.reward!r} optim={result!r}")


def main() -> None:
    args = parse_args()
    asyncio.run(train(args))


if __name__ == "__main__":
    main()

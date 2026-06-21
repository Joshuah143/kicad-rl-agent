"""Modal sandbox for running KiCad + validators at scale.

This is the **only** place in the codebase that touches Modal. Modal here is a
remote *sandbox* — a Debian image with ``kicad`` installed — in which we run the
exact same :func:`circuit_agent.infra.verifier.verify_design` pipeline that runs
locally. It is never the brain of the system; it just lets us fan out ERC +
validation across many candidates with a real KiCad available.

Usage
-----
1. Install + authenticate Modal once::

       pip install modal
       modal token new

2. Run the demo entrypoint against a task::

       modal run src/circuit_agent/infra/modal_app.py --task tasks/usb_c_5v_led.yaml

3. From Python (e.g. the local verifier with ``use_modal=True``)::

       from circuit_agent.infra import modal_app
       result = modal_app.run_on_modal(model, task)

Importability
-------------
``import modal`` is wrapped in a try/except so that importing this module — and
therefore the whole ``circuit_agent.infra`` package — never hard-requires Modal.
When Modal is missing, :data:`MODAL_AVAILABLE` is ``False`` and the public
functions raise a clear, actionable error only when actually invoked.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from circuit_agent.dsl.schema import CircuitModel
    from circuit_agent.task import TaskSpec


__all__ = [
    "MODAL_AVAILABLE",
    "app",
    "image",
    "verify_remote",
    "run_on_modal",
    "main",
]


_MODAL_INSTALL_HINT = (
    "Modal is not installed. Install it with `pip install modal` (or "
    "`pip install -e '.[modal]'`) and authenticate with `modal token new` "
    "before using the Modal sandbox. The local path (use_modal=False) needs "
    "no Modal."
)

# --- Guarded modal import ----------------------------------------------------
try:  # pragma: no cover - exercised only where modal is installed
    import modal

    MODAL_AVAILABLE = True
except Exception:  # ImportError or any partial-install failure
    modal = None  # type: ignore[assignment]
    MODAL_AVAILABLE = False


# --- App + image definition --------------------------------------------------
# These are only meaningful when modal is importable. When it is not we leave
# placeholders so attribute access elsewhere fails loudly via the public
# functions rather than at import time.
if MODAL_AVAILABLE:  # pragma: no cover - requires modal + network to truly run
    app = modal.App("kicad-rl-verifier")

    # Debian image with KiCad (for `kicad-cli` ERC/exports) plus the minimal
    # core deps. The local `circuit_agent` package is shipped into the image so
    # the remote function can import it.
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("kicad")
        .pip_install("pydantic>=2", "pyyaml")
        # Ship the local source so `import circuit_agent...` works in-container.
        # If your Modal version lacks add_local_python_source, replace with a
        # Mount of the `src/` directory onto the container's site-packages.
        .add_local_python_source("circuit_agent")
    )

    @app.function(image=image, timeout=600)
    def verify_remote(model_json: str, task_json: str) -> dict:
        """Run the full local verifier *inside* the KiCad container.

        Reconstructs the :class:`CircuitModel`/:class:`TaskSpec` from JSON, runs
        :func:`verify_design` to a temp dir with ``use_kicad=True`` (KiCad is
        present in this image) and ``use_modal=False`` (no recursion), then
        returns the reward dict plus a few small inline artifacts (the SVG
        string and the BOM/critic dicts) so the caller can persist them.
        """
        import tempfile

        from circuit_agent.dsl.schema import CircuitModel
        from circuit_agent.infra.verifier import verify_design
        from circuit_agent.task import TaskSpec

        model = CircuitModel.model_validate_json(model_json)
        task = TaskSpec.model_validate_json(task_json)

        with tempfile.TemporaryDirectory() as tmp:
            result = verify_design(
                model,
                task,
                tmp,
                use_kicad=True,
                export=True,
                critic=None,
                use_modal=False,
            )

            inline: dict[str, str] = {}
            svg_path = (result.get("artifacts") or {}).get("svg")
            if svg_path:
                try:
                    with open(svg_path, "r", encoding="utf-8") as fh:
                        inline["svg"] = fh.read()
                except OSError:
                    pass

            bom: dict = {}
            bom_path = (result.get("artifacts") or {}).get("bom")
            if bom_path:
                try:
                    with open(bom_path, "r", encoding="utf-8") as fh:
                        bom = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    pass

            critic: dict = {}
            critic_path = (result.get("artifacts") or {}).get("critic")
            if critic_path:
                try:
                    with open(critic_path, "r", encoding="utf-8") as fh:
                        critic = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    pass

        return {
            "reward": result.get("reward", {}),
            "erc_ran": bool(result.get("erc_ran", False)),
            "inline": inline,
            "bom": bom,
            "critic": critic,
        }

    @app.local_entrypoint()
    def main(task: str = "tasks/usb_c_5v_led.yaml") -> None:
        """Small demo: build the USB-C example, verify it on Modal, print reward.

        Run with::

            modal run src/circuit_agent/infra/modal_app.py --task tasks/usb_c_5v_led.yaml
        """
        from circuit_agent.dsl.examples import EXAMPLE_BUILDERS
        from circuit_agent.task import load_task

        task_spec = load_task(task)
        builder = EXAMPLE_BUILDERS["usb_c_5v_led"]()
        model = builder.to_model()

        result = verify_remote.remote(
            model.model_dump_json(),
            task_spec.model_dump_json(),
        )
        reward = result.get("reward", {})
        print(json.dumps(reward, indent=2, sort_keys=True))

else:  # Modal not installed: provide loud, helpful stand-ins.
    app = None  # type: ignore[assignment]
    image = None  # type: ignore[assignment]

    def verify_remote(model_json: str, task_json: str) -> dict:  # type: ignore[misc]
        """Stub raised when Modal is unavailable."""
        raise RuntimeError(_MODAL_INSTALL_HINT)

    def main(task: str = "tasks/usb_c_5v_led.yaml") -> None:  # type: ignore[misc]
        """Stub raised when Modal is unavailable."""
        raise RuntimeError(_MODAL_INSTALL_HINT)


def run_on_modal(model: "CircuitModel", task: "TaskSpec") -> dict:
    """Dispatch one verification to the Modal sandbox and return its dict.

    Called by :func:`circuit_agent.infra.verifier.verify_design` when
    ``use_modal=True``. Serialises the model/task to JSON, invokes
    :func:`verify_remote` remotely inside the running app, and returns the dict
    the remote produced (``{"reward", "erc_ran", "inline", "bom", "critic"}``).

    Raises
    ------
    RuntimeError
        If Modal is not installed (with an actionable install hint).
    """
    if not MODAL_AVAILABLE:
        raise RuntimeError(_MODAL_INSTALL_HINT)

    model_json = model.model_dump_json()
    task_json = task.model_dump_json()

    # `.remote(...)` requires the app to be running. When called from a plain
    # Python process we wrap the invocation in `app.run()` so a transient app is
    # spun up for the call; if we are already inside a running app context this
    # still works.
    try:
        with app.run():  # type: ignore[union-attr]
            return verify_remote.remote(model_json, task_json)  # type: ignore[attr-defined]
    except Exception:
        # If we are already within an app context, app.run() may complain;
        # fall back to a direct remote call.
        return verify_remote.remote(model_json, task_json)  # type: ignore[attr-defined]

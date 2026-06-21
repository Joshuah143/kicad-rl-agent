"""circuit_agent — RL loop that trains an LLM to emit a constrained circuit DSL.

The DSL is compiled into KiCad schematic artifacts, scored by deterministic
validators plus an optional LLM critic, and used to drive a reinforcement
learning loop. The core package (``dsl``, ``validators``, ``config``, ``task``,
``data``) depends only on the standard library, ``pydantic`` and ``pyyaml``;
heavier dependencies are imported lazily where they are actually needed.
"""

from __future__ import annotations

__version__ = "0.1.0"

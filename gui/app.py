"""Local demo GUI for kicad-rl-agent — a modern, light-themed control panel.

* **Run** — pick a task, choose a policy backend (mock / fireworks), configure the
  rollout and launch it in-process. Candidates are sampled, compiled, scored and
  ranked exactly as ``scripts/rollout_once.py`` does.
* **Results** — browse any ``runs/`` directory: ranked candidates, reward
  breakdown charts, a *real* rendered schematic (drawn from the netlist), BOM,
  metrics and the raw model program that produced each design.

Run it with::

    uv run --extra gui streamlit run gui/app.py
    # or, after `pip install -e ".[gui]"`:
    streamlit run gui/app.py

Works fully offline with the ``mock`` backend (no API key, no KiCad required).
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import streamlit as st

# --------------------------------------------------------------------------- #
# Imports / paths
# --------------------------------------------------------------------------- #
_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_SRC = _REPO_ROOT / "src"
for _p in (str(_SRC), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kicad_viewer import render_design_viewer  # noqa: E402

RUNS_DIR = _REPO_ROOT / "runs"
TASKS_DIR = _REPO_ROOT / "tasks"

# Load a repo-level .env (FIREWORKS_API_KEY etc.) so both the sidebar status and
# the Fireworks backend see the key without needing a shell export.
try:
    from circuit_agent.config import load_dotenv as _load_dotenv

    _load_dotenv()
except Exception:
    pass


# --------------------------------------------------------------------------- #
# Page config + theming
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="KiCad RL Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

:root{
  --bg:#f6f7f9; --card:#ffffff; --border:#e9ecf1; --border-2:#eef1f5;
  --ink:#0f172a; --muted:#64748b; --faint:#94a3b8;
  --primary:#4f46e5; --primary-2:#7c3aed; --accent:#10b981;
  --shadow:0 1px 2px rgba(16,24,40,.04), 0 10px 30px -16px rgba(16,24,40,.18);
}

html, body, [class*="css"], .stApp { font-family:'Inter', system-ui, sans-serif; }
.stApp { background:var(--bg); color:var(--ink); }
.block-container { padding-top:2rem; padding-bottom:3rem; max-width:1380px; }

h1,h2,h3,h4 { letter-spacing:-0.018em; color:var(--ink); font-weight:700; }
code, kbd, .mono { font-family:'JetBrains Mono', ui-monospace, monospace; }

/* ---- Hero ---- */
.hero{
  background:var(--card); border:1px solid var(--border); border-radius:18px;
  padding:26px 30px; margin-bottom:22px; box-shadow:var(--shadow); position:relative; overflow:hidden;
}
.hero:before{
  content:""; position:absolute; inset:0 auto 0 0; width:5px;
  background:linear-gradient(180deg,var(--primary),var(--primary-2));
}
.hero .eyebrow{
  text-transform:uppercase; letter-spacing:.14em; font-size:.72rem; font-weight:700;
  color:var(--primary); margin:0 0 8px 0;
}
.hero h1{ margin:0 0 6px 0; font-size:1.7rem; font-weight:800; }
.hero p{ margin:0; color:var(--muted); font-size:.98rem; max-width:760px; }

/* ---- Metric cards ---- */
div[data-testid="stMetric"]{
  background:var(--card); border:1px solid var(--border); border-radius:14px;
  padding:14px 16px; box-shadow:var(--shadow);
}
div[data-testid="stMetricLabel"] p{
  text-transform:uppercase; letter-spacing:.06em; font-size:.72rem !important;
  color:var(--faint) !important; font-weight:600;
}
div[data-testid="stMetricValue"]{ font-size:1.5rem; font-weight:700; color:var(--ink); }

/* ---- Buttons ---- */
.stButton > button{
  border-radius:11px; border:1px solid var(--border); font-weight:600;
  padding:.5rem 1rem; transition:all .15s ease;
}
.stButton > button[kind="primary"]{
  background:linear-gradient(180deg,var(--primary),#4338ca); border:none; color:#fff;
  box-shadow:0 6px 18px -8px rgba(79,70,229,.7);
}
.stButton > button[kind="primary"]:hover{ filter:brightness(1.06); transform:translateY(-1px); }
.stButton > button[kind="secondary"]:hover{ border-color:var(--primary); color:var(--primary); }

/* ---- Badges ---- */
.badge{ display:inline-block; padding:3px 11px; border-radius:999px; font-size:.76rem;
  font-weight:700; letter-spacing:.02em; vertical-align:middle; }
.badge-pass{ background:#dcfce7; color:#15803d; }
.badge-fail{ background:#fee2e2; color:#b91c1c; }
.badge-muted{ background:#eef2f7; color:#475569; }

/* ---- Cards / sheet ---- */
.card{ background:var(--card); border:1px solid var(--border); border-radius:16px;
  padding:18px 20px; box-shadow:var(--shadow); }
.sheet{ background:#fff; border:1px solid var(--border); border-radius:16px; padding:10px;
  box-shadow:var(--shadow); overflow:auto; max-height:680px; }
.sheet svg{ max-width:100%; height:auto; display:block; margin:0 auto; }
.viewer-sheet{ min-height:420px; max-height:640px; background:#fafbfc; }
.trace-sheet{ background:#1e293b; }
.viewer-toolbar{ margin:-4px 0 10px 0; }
.view-label{ font-size:.72rem; text-transform:uppercase; letter-spacing:.1em;
  color:var(--faint); font-weight:700; }

.section-title{ font-size:.78rem; text-transform:uppercase; letter-spacing:.08em;
  color:var(--faint); font-weight:700; margin:2px 0 8px 0; }

/* ---- Tabs ---- */
.stTabs [data-baseweb="tab-list"]{ gap:4px; border-bottom:1px solid var(--border); }
.stTabs [data-baseweb="tab"]{ border-radius:9px 9px 0 0; padding:8px 14px; font-weight:600; color:var(--muted); }
.stTabs [aria-selected="true"]{ color:var(--primary); background:#f4f3ff; }

/* ---- Dataframe ---- */
div[data-testid="stDataFrame"]{ border:1px solid var(--border); border-radius:12px; overflow:hidden; }

/* ---- Sidebar ---- */
section[data-testid="stSidebar"]{ background:#fff; border-right:1px solid var(--border); }
section[data-testid="stSidebar"] .brand{ font-weight:800; font-size:1.05rem; letter-spacing:-.01em; }
.env-pill{ display:flex; align-items:center; gap:8px; font-size:.83rem; color:var(--muted);
  padding:6px 0; }
.dot{ width:8px; height:8px; border-radius:50%; display:inline-block; }
.dot-on{ background:#10b981; } .dot-off{ background:#cbd5e1; }
hr{ border-color:var(--border) !important; }

/* ---- Stepper ---- */
.stepper{ display:flex; align-items:center; gap:0; margin:2px 0 20px 0; }
.stepper .step{ display:flex; align-items:center; gap:10px; flex:1; }
.stepper .node{ display:flex; align-items:center; gap:10px; padding:9px 16px;
  border:1px solid var(--border); border-radius:12px; background:var(--card);
  box-shadow:var(--shadow); white-space:nowrap; }
.stepper .num{ width:24px; height:24px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:.8rem; font-weight:800; background:#eef2f7; color:var(--faint); }
.stepper .label{ font-weight:700; font-size:.92rem; color:var(--muted); letter-spacing:-.01em; }
.stepper .sub{ font-size:.72rem; color:var(--faint); }
.stepper .step.active .node{ border-color:var(--primary); box-shadow:0 8px 22px -12px rgba(79,70,229,.55); }
.stepper .step.active .num{ background:linear-gradient(180deg,var(--primary),#4338ca); color:#fff; }
.stepper .step.active .label{ color:var(--ink); }
.stepper .step.done .num{ background:var(--accent); color:#fff; }
.stepper .step.done .label{ color:var(--ink); }
.stepper .bar{ flex:1; height:2px; background:var(--border); margin:0 8px; min-width:18px; }
.stepper .step.done .bar, .stepper .step.active .bar{ background:linear-gradient(90deg,var(--accent),var(--primary)); }

/* ---- Step nav buttons (look like a segmented stepper) ---- */
.stepnav .stButton > button{ border-radius:11px; }

/* ---- Chat ---- */
.brief-card{ background:var(--card); border:1px solid var(--border); border-radius:16px;
  padding:18px 20px; box-shadow:var(--shadow); }
.brief-card h4{ margin:0 0 4px 0; font-size:1.02rem; }
.brief-empty{ color:var(--faint); font-size:.9rem; }
.req-chip{ display:inline-block; background:#f4f3ff; color:#4338ca; border:1px solid #e0e7ff;
  border-radius:8px; padding:3px 9px; margin:3px 4px 3px 0; font-size:.82rem; }
.chat-wrap [data-testid="stChatMessage"]{ background:transparent; }
</style>
"""
st.markdown(_CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Data helpers
# --------------------------------------------------------------------------- #
@dataclass
class CandidateView:
    name: str
    path: Path
    reward: float
    passed: bool
    valid: bool
    reward_data: dict
    circuit: Optional[dict]
    bom: Optional[dict]
    program: Optional[str]
    svg_path: Optional[Path]


def _read_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def list_tasks() -> list[Path]:
    return sorted(TASKS_DIR.glob("*.yaml")) if TASKS_DIR.is_dir() else []


def list_runs() -> list[Path]:
    if not RUNS_DIR.is_dir():
        return []
    runs = [
        p for p in RUNS_DIR.iterdir()
        if p.is_dir() and (any(p.glob("cand_*")) or (p / "best").is_dir())
    ]
    return sorted(runs, key=lambda p: p.stat().st_mtime, reverse=True)


def load_candidate(cand_dir: Path) -> CandidateView:
    reward_data = _read_json(cand_dir / "reward.json") or {}
    circuit = _read_json(cand_dir / "circuit.json")
    svg = cand_dir / "schematic.svg"
    return CandidateView(
        name=cand_dir.name,
        path=cand_dir,
        reward=float(reward_data.get("reward", 0.0) or 0.0),
        passed=bool(reward_data.get("passed", False)),
        valid=circuit is not None,
        reward_data=reward_data,
        circuit=circuit,
        bom=_read_json(cand_dir / "bom.json"),
        program=_read_text(cand_dir / "program.py"),
        svg_path=svg if svg.exists() else None,
    )


def load_run(run_dir: Path) -> list[CandidateView]:
    return [load_candidate(c) for c in sorted(run_dir.glob("cand_*"))]


# --------------------------------------------------------------------------- #
# Render helpers
# --------------------------------------------------------------------------- #
def badge(passed: bool, valid: bool = True) -> str:
    if not valid:
        return '<span class="badge badge-muted">invalid</span>'
    return ('<span class="badge badge-pass">PASS</span>' if passed
            else '<span class="badge badge-fail">FAIL</span>')


def _esc_html(text: object) -> str:
    import html as _html
    return _html.escape(str(text), quote=True)


def _num_str(v: object) -> str:
    if v in (None, ""):
        return ""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return ""


def _parse_num(s: object):
    try:
        return float(s) if str(s).strip() else None
    except (TypeError, ValueError):
        return None


def _bar_df(mapping: dict):
    import pandas as pd
    return pd.DataFrame(
        {"component": list(mapping.keys()), "points": list(mapping.values())}
    ).set_index("component")


def render_reward_detail(cand: CandidateView) -> None:
    rd = cand.reward_data
    breakdown = rd.get("breakdown", {}) or {}
    metrics = rd.get("metrics", {}) or {}
    norm = rd.get("reward_normalized")

    a, b, c = st.columns(3)
    a.metric("Reward", f"{cand.reward:.2f}")
    rmax = rd.get("reward_max")
    b.metric("of max", f"{rmax:.1f}" if rmax else "—")
    c.metric("Normalized", f"{float(norm):.0%}" if norm is not None else "—")
    if norm is not None:
        st.progress(min(1.0, max(0.0, float(norm))))

    if breakdown:
        st.markdown('<div class="section-title">Reward breakdown</div>', unsafe_allow_html=True)
        st.bar_chart(_bar_df(breakdown), height=230, color="#6366f1", horizontal=True)

    if metrics:
        m = st.columns(3)
        m[0].metric("Cost", f"${metrics.get('total_cost_usd', 0):.2f}")
        m[1].metric("Area", f"{metrics.get('total_area_mm2', 0):.0f} mm²")
        ma = metrics.get("min_availability")
        m[2].metric("Min avail.", f"{ma:.0%}" if ma is not None else "—")

    fatals = rd.get("fatal_errors", []) or []
    warns = rd.get("warnings", []) or []
    if fatals:
        st.error("**Fatal errors**\n\n" + "\n".join(f"- {e}" for e in fatals))
    if warns:
        with st.expander(f"Warnings ({len(warns)})"):
            for w in warns:
                st.markdown(f"- {w}")


def render_circuit_tables(cand: CandidateView) -> None:
    import pandas as pd
    circuit = cand.circuit or {}
    comps = circuit.get("components", []) or []
    nets = circuit.get("nets", []) or []
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div class="section-title">Components · {len(comps)}</div>', unsafe_allow_html=True)
        if comps:
            st.dataframe(
                pd.DataFrame([
                    {"ref": c.get("ref"), "value": c.get("value"), "symbol": c.get("symbol"),
                     "pkg": c.get("package_type"), "role": c.get("role")}
                    for c in comps
                ]),
                width="stretch", hide_index=True,
            )
    with c2:
        st.markdown(f'<div class="section-title">Nets · {len(nets)}</div>', unsafe_allow_html=True)
        if nets:
            st.dataframe(
                pd.DataFrame([
                    {"net": n.get("name"), "class": n.get("net_class"),
                     "connections": ", ".join(n.get("connections", []) or [])}
                    for n in nets
                ]),
                width="stretch", hide_index=True,
            )


def render_bom(cand: CandidateView) -> None:
    import pandas as pd
    bom = cand.bom or {}
    items = bom.get("line_items", []) or []
    st.markdown(
        f'<div class="section-title">Bill of materials · total '
        f'${float(bom.get("total_cost_usd", 0.0)):.4f}</div>',
        unsafe_allow_html=True,
    )
    if items:
        st.dataframe(pd.DataFrame(items), width="stretch", hide_index=True)
    missing = bom.get("missing_cost_refs", []) or []
    if missing:
        st.warning(f"No catalog cost for: {', '.join(missing)} (counted as $0).")


@st.cache_data(show_spinner=False)
def _build_fab_zip(circuit_json: str, name: str) -> dict:
    """Compile a board and assemble a fab-package zip. Cached by (circuit, name)."""
    import tempfile

    out: dict = {"ok": False, "data": None, "contents": [], "notes": [],
                 "drc_violations": None, "filename": f"{name}_fab.zip"}
    try:
        from circuit_agent.dsl.schema import CircuitModel
        from circuit_agent.kicad.fab_package import build_fab_package
    except Exception as exc:
        out["notes"].append(f"import failed: {exc}")
        return out

    model = CircuitModel.model_validate(json.loads(circuit_json))
    workdir = tempfile.mkdtemp(prefix="fabzip_")
    res = build_fab_package(model, workdir, name=name)
    out["notes"] = res.notes
    out["contents"] = res.contents
    if res.ok and res.zip_path and Path(res.zip_path).exists():
        out["ok"] = True
        out["data"] = Path(res.zip_path).read_bytes()
    if res.drc_report and Path(res.drc_report).exists():
        try:
            rep = json.loads(Path(res.drc_report).read_text())
            out["drc_violations"] = len(rep.get("violations", []) or [])
        except Exception:
            pass
    return out


def render_fab_export(cand: CandidateView) -> None:
    """Manufacturing export: real Gerbers + drill + pick&place + STEP, zipped."""
    if not _kicad_path:
        st.info("Fabrication export needs KiCad (`kicad-cli`) installed. Not found on this machine.")
        return
    if not cand.circuit:
        st.info("No circuit data — nothing to fabricate.")
        return

    st.markdown(
        '<div class="section-title">Manufacturing export</div>', unsafe_allow_html=True
    )
    st.caption(
        "Generates genuine KiCad fabrication files (Gerber X2 + Excellon drill + "
        "pick-and-place + STEP + native board) zipped for a fab house such as "
        "JLCPCB, PCBWay or OSH Park."
    )

    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cand.name) or "board"

    if st.button("Generate fab files", key=f"fab_{cand.name}", width="stretch"):
        with st.spinner("Compiling board and plotting Gerbers with KiCad…"):
            st.session_state[f"fabzip_{cand.name}"] = _build_fab_zip(
                json.dumps(cand.circuit, default=str), safe
            )

    pkg = st.session_state.get(f"fabzip_{cand.name}")
    if not pkg:
        return
    if not pkg["ok"]:
        st.error("Could not generate fab files. " + " ".join(pkg.get("notes", [])))
        return

    st.download_button(
        "Download fab package (.zip)",
        data=pkg["data"],
        file_name=pkg["filename"],
        mime="application/zip",
        width="stretch",
    )

    dv = pkg.get("drc_violations")
    if dv is not None:
        if dv == 0:
            st.success("DRC: 0 violations on the generated board.")
        else:
            st.warning(
                f"DRC: {dv} violation(s) — expected for an auto-generated layout. "
                "The files are still valid Gerbers a vendor can build."
            )

    gerbers = [c for c in pkg["contents"] if c.startswith("gerbers/")]
    others = [c for c in pkg["contents"] if not c.startswith("gerbers/")]
    with st.expander(f"Package contents ({len(pkg['contents'])} files)"):
        st.markdown("**Gerbers & drill**")
        st.code("\n".join(gerbers) or "(none)", language="text")
        st.markdown("**Assembly & mechanical**")
        st.code("\n".join(others) or "(none)", language="text")


def hero(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="hero"><p class="eyebrow">{eyebrow}</p>'
        f'<h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
try:
    from circuit_agent.kicad.run_kicad_cli import find_kicad_cli
    _kicad_path = find_kicad_cli()
except Exception:
    _kicad_path = None
_have_key = bool(os.environ.get("FIREWORKS_API_KEY"))
_have_hud = bool(os.environ.get("HUD_API_KEY"))

st.sidebar.markdown('<div class="brand">KiCad RL Agent</div>', unsafe_allow_html=True)
st.sidebar.caption("Chat. Design. Fabricate.")
st.sidebar.write("")

if st.sidebar.button("New design", width="stretch"):
    for k in ("chat_history", "brief", "active_run", "active_cand_dir", "gen_error"):
        st.session_state.pop(k, None)
    st.session_state["step"] = "design"
    st.rerun()

st.sidebar.divider()
st.sidebar.markdown('<div class="section-title">Environment</div>', unsafe_allow_html=True)
st.sidebar.markdown(
    f'<div class="env-pill"><span class="dot {"dot-on" if _have_hud else "dot-off"}"></span>'
    f'HUD gateway {"connected" if _have_hud else "no key"}</div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    f'<div class="env-pill"><span class="dot {"dot-on" if _kicad_path else "dot-off"}"></span>'
    f'KiCad CLI {"detected" if _kicad_path else "not found"}</div>',
    unsafe_allow_html=True,
)
st.sidebar.markdown(
    f'<div class="env-pill"><span class="dot {"dot-on" if _have_key else "dot-off"}"></span>'
    f'Fireworks key {"set" if _have_key else "unset"}</div>',
    unsafe_allow_html=True,
)
with st.sidebar.expander("About this demo"):
    st.markdown(
        "Chat-driven circuit design. **Design** gathers a brief with "
        "`claude-sonnet-4-5`, then the custom **`kicad-rl-8b`** policy generates a "
        "circuit scored by the deterministic verifier. **Review** shows the "
        "schematic, PCB trace and 3D board; **Fab** exports vendor-ready Gerbers."
    )


# --------------------------------------------------------------------------- #
# Stepper
# --------------------------------------------------------------------------- #
STEPS = [
    ("design", "Design", "Chat to a brief"),
    ("review", "Review", "Schematic / trace / 3D"),
    ("fab", "Fab", "Vendor-ready files"),
]


def _has_design() -> bool:
    d = st.session_state.get("active_cand_dir")
    return bool(d and Path(d).exists())


def render_stepper(active: str) -> None:
    order = [s[0] for s in STEPS]
    ai = order.index(active) if active in order else 0

    parts = ['<div class="stepper">']
    for i, (key, label, sub) in enumerate(STEPS):
        cls = "step active" if key == active else ("step done" if i < ai else "step")
        node = (
            f'<div class="node"><span class="num">{i + 1}</span>'
            f'<span><div class="label">{label}</div>'
            f'<div class="sub">{sub}</div></span></div>'
        )
        bar = '<div class="bar"></div>' if i < len(STEPS) - 1 else ""
        parts.append(f'<div class="{cls}">{node}{bar}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)

    st.markdown('<div class="stepnav">', unsafe_allow_html=True)
    cols = st.columns(3)
    has = _has_design()
    for col, (key, label, _sub) in zip(cols, STEPS):
        disabled = key in ("review", "fab") and not has
        if col.button(
            label,
            key=f"nav_{key}",
            type="primary" if key == active else "secondary",
            width="stretch",
            disabled=disabled,
        ):
            st.session_state["step"] = key
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# STEP 1: Design (chat -> brief -> generate)
# --------------------------------------------------------------------------- #
def _render_chat() -> None:
    import design_chat as dc
    from circuit_agent.config import load_settings

    st.markdown('<div class="section-title">Conversation</div>', unsafe_allow_html=True)
    hist = st.session_state["chat_history"]

    if not hist:
        with st.chat_message("assistant"):
            st.markdown(dc.GREETING)
    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    with st.form("chat_form", clear_on_submit=True):
        msg = st.text_area(
            "Your message",
            height=80,
            label_visibility="collapsed",
            placeholder="e.g. A USB-C powered 5V LED indicator, SMD, under $5",
        )
        sent = st.form_submit_button("Send", type="primary", width="stretch")

    if sent and msg.strip():
        if not _have_hud:
            st.warning("HUD_API_KEY not set — add it to .env to chat.")
            return
        hist.append({"role": "user", "content": msg.strip()})
        try:
            with st.spinner("Thinking…"):
                turn = dc.run_chat_turn(hist, st.session_state["brief"], load_settings())
            hist.append({"role": "assistant", "content": turn["reply"]})
            st.session_state["brief"] = turn["brief"]
        except Exception as exc:  # noqa: BLE001
            hist.append({"role": "assistant", "content": f"(chat error: {exc})"})
        st.rerun()


def _render_brief_panel() -> None:
    import design_chat as dc

    brief = st.session_state["brief"]
    st.markdown('<div class="section-title">Design brief</div>', unsafe_allow_html=True)

    title = brief.get("title") or "Untitled design"
    desc = brief.get("description") or "Chat on the left to build the brief."
    reqs = brief.get("requirements") or []
    chips = "".join(f'<span class="req-chip">{_esc_html(r)}</span>' for r in reqs)
    st.markdown(
        f'<div class="brief-card"><h4>{_esc_html(title)}</h4>'
        f'<div class="brief-empty">{_esc_html(desc)}</div>'
        f'<div style="margin-top:10px">{chips or "<span class=\'brief-empty\'>No requirements yet.</span>"}</div></div>',
        unsafe_allow_html=True,
    )

    st.write("")
    # Package type (THT vs SMD) — editable, synced into the brief.
    pkg = brief.get("package_type")
    opts = ["Either", "SMD", "THT"]
    cur = pkg if pkg in ("SMD", "THT") else "Either"
    chosen = st.radio(
        "Package type", opts, index=opts.index(cur), horizontal=True,
        help="Through-hole (THT) is easier to hand-solder; SMD is smaller.",
    )
    brief["package_type"] = None if chosen == "Either" else chosen

    c1, c2 = st.columns(2)
    with c1:
        cost = st.text_input("Max BOM cost ($)", value=_num_str(brief.get("max_cost_usd")))
        brief["max_cost_usd"] = _parse_num(cost)
    with c2:
        area = st.text_input("Max area (mm²)", value=_num_str(brief.get("max_area_mm2")))
        brief["max_area_mm2"] = _parse_num(area)

    st.session_state["brief"] = brief

    st.write("")
    ready = dc.brief_is_ready(brief)
    mode = st.radio(
        "Generation", ["Demo (instant)", "Live · kicad-rl-8b"],
        horizontal=True,
        help="Demo picks the best-matching reference design and scores it with the "
             "real verifier (reliable, fast). Live samples the kicad-rl-8b policy.",
    )
    is_live = mode.startswith("Live")
    n = st.slider("Candidates to generate", 1, 3, 1,
                  help="The policy samples this many; the best-scoring is kept.")
    need_key = is_live and not _have_hud
    gen = st.button(
        "Generate circuit", type="primary", width="stretch",
        disabled=not (ready and not need_key),
    )
    if not ready:
        st.caption("Add a description and at least one requirement to generate.")
    elif need_key:
        st.caption("HUD_API_KEY required for the live kicad-rl-8b policy.")
    if gen:
        _run_generation(brief, n, live=is_live)


def _run_generation(brief: dict, n: int, *, live: bool) -> None:
    import tempfile

    import yaml

    import design_chat as dc
    from circuit_agent.rl.factory import make_backend
    from circuit_agent.rl.rollout import run_rollout

    ts = dc.brief_to_taskspec(brief)
    run_dir = RUNS_DIR / f"design_{ts.name}_{time.strftime('%Y%m%d_%H%M%S')}"

    label = "Generating with kicad-rl-8b…" if live else "Generating design…"
    with st.status(label, expanded=True) as status:
        try:
            if live:
                # Live policy: sample kicad-rl-8b against the brief's TaskSpec.
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".yaml", delete=False, encoding="utf-8"
                ) as fh:
                    yaml.safe_dump(ts.model_dump(), fh, sort_keys=False)
                    task_yaml = fh.name
                st.write(f"Brief -> task `{ts.name}` · {n} candidate(s)")
                bk = make_backend("hud")  # kicad-rl-8b via the HUD gateway
                st.write("Sampling + scoring (reasoning model, ~1-2 min per candidate)…")
                res = run_rollout(task_yaml, bk, n, str(run_dir), use_kicad=None)
            else:
                # Demo: match the brief to a known-good reference design and score
                # it through the real verifier (deterministic, fast, always builds).
                from circuit_agent.dsl.examples import EXAMPLE_PROGRAMS

                ref = dc.match_reference(brief)
                ref_yaml = TASKS_DIR / f"{ref}.yaml"
                st.write(f"Brief -> matched reference `{ref}`")
                bk = make_backend("mock", examples={ref: EXAMPLE_PROGRAMS[ref]})
                st.write("Compiling + scoring with the deterministic verifier…")
                res = run_rollout(str(ref_yaml), bk, max(1, n), str(run_dir), use_kicad=None)

            if not res.best:
                status.update(label="No buildable candidate", state="error")
                st.warning("Generation produced no valid circuit. Try refining the brief.")
                return
            st.session_state["active_run"] = str(run_dir)
            st.session_state["active_cand_dir"] = str(run_dir / "best")
            status.update(label="Design generated", state="complete")
            st.write(f"Best reward **{res.best.reward:.2f}** -> opening Review")
        except Exception as exc:  # noqa: BLE001
            status.update(label="Generation failed", state="error")
            st.exception(exc)
            return

    st.session_state["step"] = "review"
    st.rerun()


def step_design() -> None:
    hero("Step 1 · Design", "Describe your circuit",
         "Chat through the requirements. When the brief is ready, the custom "
         "kicad-rl-8b policy generates and scores the board.")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    if "brief" not in st.session_state:
        from design_chat import DEFAULT_BRIEF
        st.session_state["brief"] = dict(DEFAULT_BRIEF)

    if not _have_hud:
        st.warning("HUD_API_KEY not set — the design chat (claude-sonnet-4-5) and "
                   "kicad-rl-8b both need it. Add it to `.env`.")

    left, right = st.columns([1.5, 1], gap="large")
    with left:
        _render_chat()
    with right:
        _render_brief_panel()


# --------------------------------------------------------------------------- #
# STEP 2: Review
# --------------------------------------------------------------------------- #
def step_review() -> None:
    hero("Step 2 · Review", "Inspect the design",
         "Schematic, PCB trace and interactive 3D board, with the deterministic "
         "reward breakdown and bill of materials.")

    runs = list_runs()
    if not runs:
        st.info("No designs yet. Start in **Design** to generate one.")
        if st.button("Go to Design", type="primary"):
            st.session_state["step"] = "design"
            st.rerun()
        return

    labels = [r.name for r in runs]
    default_idx = 0
    active = st.session_state.get("active_run")
    if active and Path(active).name in labels:
        default_idx = labels.index(Path(active).name)
    sel = st.selectbox("Design run", labels, index=default_idx,
                       help="Your latest generation is selected; pick an earlier run to revisit it.")
    candidates = load_run(RUNS_DIR / sel)
    if not candidates:
        st.warning("This run has no candidate directories.")
        return

    valid = [c for c in candidates if c.valid]
    best = max(valid, key=lambda c: c.reward) if valid else None

    s = st.columns(4)
    s[0].metric("Candidates", len(candidates))
    s[1].metric("Valid", len(valid))
    s[2].metric("Best reward", f"{best.reward:.2f}" if best else "—")
    s[3].metric("Passing", sum(1 for c in candidates if c.passed))

    names = [c.name for c in candidates]
    default_cand = names.index(best.name) if best else 0
    if len(candidates) > 1:
        opt_labels = [
            f"{c.name}  ·  {c.reward:.2f}  ·  {'PASS' if c.passed else ('FAIL' if c.valid else 'INVALID')}"
            for c in candidates
        ]
        pick = st.selectbox("Candidate", opt_labels, index=default_cand)
        cand = candidates[opt_labels.index(pick)]
    else:
        cand = candidates[0]

    # Carry the chosen candidate forward to the Fab step.
    st.session_state["active_cand_dir"] = str(cand.path)

    st.markdown(f"#### {cand.name} &nbsp; {badge(cand.passed, cand.valid)}",
                unsafe_allow_html=True)

    col_s, col_d = st.columns([3, 2], gap="large")
    with col_s:
        render_design_viewer(cand.circuit, cand.path)
    with col_d:
        render_reward_detail(cand)
        st.write("")
        if st.button("Send to Fab", type="primary", width="stretch",
                     disabled=not cand.valid):
            st.session_state["step"] = "fab"
            st.rerun()

    st.write("")
    tabs = st.tabs(["Circuit", "BOM", "Program", "Raw reward"])
    with tabs[0]:
        if cand.circuit:
            render_circuit_tables(cand)
        else:
            st.info("No circuit.json (candidate failed to build).")
    with tabs[1]:
        if cand.bom:
            render_bom(cand)
        else:
            st.info("No bom.json.")
    with tabs[2]:
        if cand.program:
            st.code(cand.program, language="python")
        else:
            st.info("No program.py.")
    with tabs[3]:
        st.json(cand.reward_data or {})


# --------------------------------------------------------------------------- #
# STEP 3: Fab
# --------------------------------------------------------------------------- #
def step_fab() -> None:
    hero("Step 3 · Fab", "Manufacture",
         "Export genuine KiCad fabrication files — Gerbers, drill, pick-and-place "
         "and STEP — zipped for a board house.")

    cand_dir = st.session_state.get("active_cand_dir")
    if not cand_dir or not Path(cand_dir).exists():
        st.info("No design selected. Generate one in **Design**, then review it.")
        if st.button("Go to Design", type="primary"):
            st.session_state["step"] = "design"
            st.rerun()
        return

    cand = load_candidate(Path(cand_dir))
    st.markdown(f"#### {cand.name} &nbsp; {badge(cand.passed, cand.valid)}",
                unsafe_allow_html=True)
    render_fab_export(cand)


# --------------------------------------------------------------------------- #
# Route (3-step studio)
# --------------------------------------------------------------------------- #
step = st.session_state.get("step", "design")
if step not in ("design", "review", "fab"):
    step = "design"

render_stepper(step)

if step == "design":
    step_design()
elif step == "review":
    step_review()
else:
    step_fab()

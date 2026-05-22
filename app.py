"""
Streamlit web interface for PEA (Power Electronics AI Agent).

Uses the same stack as ``pea chat`` and ``pea tool``: ``execute_tool`` from
``pea.tools.calculator`` for sidebar calculators, and ``PEAAgent`` for the
main chat when ``OPENAI_API_KEY`` is set.

Contrast: ``index.html`` + ``pea.desktop`` is a separate static UI; keep
user-facing behavior in sync when you change calculators or taxonomy.
"""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from pea.agent.runner import PEAAgent
from pea.optimization import OptimizationConfig, optimize_converter_design
from pea.tools.calculator import execute_tool


st.set_page_config(
    page_title="PEA - Power Electronics AI",
    page_icon="⚡",
    layout="wide",
)

st.title("⚡ PEA - Power Electronics AI Agent")
st.caption("Design assistant for DC-DC converters: topology selection, parameter calculation, component guidance")

# ── Sidebar: Quick tools (no API key) ────────────────────────────────────
with st.sidebar:
    st.header("Quick Tools")
    st.caption("Direct calculations (no API key needed)")

    tool_choice = st.selectbox(
        "Select tool",
        [
            "Topology Recommendation",
            "Buck",
            "Boost",
            "Buck-Boost",
            "SEPIC",
            "Cuk",
            "Forward",
            "Flyback",
            "LLC Resonant",
            "DAB (Dual Active Bridge)",
            "Cascade (Multi-Stage)",
            "Inductor Design",
            "Transformer Design",
            "Efficiency Estimate",
            "Component Recommendation",
        ],
    )

    # Show appropriate input fields depending on tool
    if tool_choice == "DAB (Dual Active Bridge)":
        col1, col2 = st.columns(2)
        with col1:
            v1 = st.number_input("V₁ Port 1 (V)", min_value=0.1, value=400.0, step=1.0)
            p_rated = st.number_input("P_rated (W)", min_value=1.0, value=1000.0, step=50.0)
        with col2:
            v2 = st.number_input("V₂ Port 2 (V)", min_value=0.1, value=48.0, step=0.5)
            phi_deg = st.number_input("Phase shift φ (°)", min_value=1.0, value=30.0, step=1.0)
        f_sw = st.number_input("f_sw (kHz)", min_value=10, value=100, step=10)
    elif tool_choice == "Inductor Design":
        col1, col2 = st.columns(2)
        with col1:
            ind_L = st.number_input("Inductance (µH)", min_value=0.1, value=100.0, step=1.0)
            ind_ipk = st.number_input("I_peak (A)", min_value=0.01, value=5.0, step=0.1)
        with col2:
            ind_irms = st.number_input("I_rms (A)", min_value=0.01, value=3.0, step=0.1)
            f_sw = st.number_input("f_sw (kHz)", min_value=10, value=100, step=10)
        core_shape = st.selectbox("Core shape", ["EE", "PQ", "RM", "ETD", "EFD", "EP", "toroid", "EI"])
        material = st.selectbox("Material", ["N87", "N97", "3C90", "3C95", "3F3", "PC40", "PC95"])
        b_max = st.number_input("B_max (mT)", min_value=50.0, value=300.0, step=10.0)
    elif tool_choice == "Transformer Design":
        col1, col2 = st.columns(2)
        with col1:
            tx_vpri = st.number_input("V_pri (V)", min_value=0.1, value=400.0, step=1.0)
            tx_power = st.number_input("Power (W)", min_value=1.0, value=500.0, step=10.0)
        with col2:
            tx_vsec = st.number_input("V_sec (V)", min_value=0.1, value=12.0, step=0.1)
            tx_duty = st.number_input("Duty cycle", min_value=0.05, max_value=0.95, value=0.45, step=0.05)
        f_sw = st.number_input("f_sw (kHz)", min_value=10, value=100, step=10)
        core_shape = st.selectbox("Core shape", ["EE", "PQ", "RM", "ETD", "EFD", "EP", "toroid", "EI"])
        material = st.selectbox("Material", ["N87", "N97", "3C90", "3C95", "3F3", "PC40", "PC95"])
        b_max = st.number_input("B_max (mT)", min_value=50.0, value=250.0, step=10.0)
    else:
        col1, col2 = st.columns(2)
        with col1:
            v_in = st.number_input("V_in (V)", min_value=0.1, value=12.0, step=0.1)
            v_out = st.number_input("V_out (V)", min_value=0.1, value=5.0, step=0.1)
        with col2:
            i_out = st.number_input("I_out (A)", min_value=0.01, value=2.0, step=0.1)
            f_sw = st.number_input("f_sw (kHz)", min_value=10, value=100, step=10)

    if tool_choice in ("Flyback", "Forward"):
        v_in_min = st.number_input("V_in_min (V)", min_value=0.1, value=9.0, step=0.1)
        v_in_max = st.number_input("V_in_max (V)", min_value=0.1, value=18.0, step=0.1)
    elif tool_choice not in ("DAB (Dual Active Bridge)", "Inductor Design", "Transformer Design"):
        v_in_min, v_in_max = 9.0, 18.0

    if tool_choice == "LLC Resonant":
        q_factor = st.number_input("Q factor", min_value=0.1, value=0.5, step=0.1)
    elif tool_choice not in ("DAB (Dual Active Bridge)", "Inductor Design", "Transformer Design"):
        q_factor = 0.5

    if tool_choice == "Efficiency Estimate":
        st.markdown("**Component parameters**")
        rds_on = st.number_input("MOSFET Rds(on) (mΩ)", min_value=1.0, value=50.0, step=5.0)
        dcr = st.number_input("Inductor DCR (mΩ)", min_value=1.0, value=30.0, step=5.0)
        vf_diode = st.number_input("Diode Vf (V)", min_value=0.0, value=0.5, step=0.1)
        t_rise_ns = st.number_input("Rise time (ns)", min_value=1.0, value=20.0, step=5.0)
        t_fall_ns = st.number_input("Fall time (ns)", min_value=1.0, value=20.0, step=5.0)
    else:
        rds_on = 50.0
        dcr = 30.0
        vf_diode = 0.5
        t_rise_ns = 20.0
        t_fall_ns = 20.0

    if tool_choice == "Topology Recommendation":
        isolated = st.checkbox("Require isolation", value=False)
        bidirectional = st.checkbox("Bidirectional", value=False)
    else:
        isolated = False
        bidirectional = False

    if st.button("Calculate", use_container_width=True):
        tool_map = {
            "Topology Recommendation": lambda: execute_tool(
                "topology_recommendation", v_in=v_in, v_out=v_out, i_out=i_out,
                isolated=isolated, bidirectional=bidirectional,
            ),
            "Buck": lambda: execute_tool(
                "buck_converter_design", v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Boost": lambda: execute_tool(
                "boost_converter_design", v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Buck-Boost": lambda: execute_tool(
                "buck_boost_design", v_in=v_in, v_out=-v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "SEPIC": lambda: execute_tool(
                "sepic_design", v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Cuk": lambda: execute_tool(
                "cuk_design", v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Forward": lambda: execute_tool(
                "forward_design", v_in_min=v_in_min, v_in_max=v_in_max,
                v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Flyback": lambda: execute_tool(
                "flyback_design", v_in_min=v_in_min, v_in_max=v_in_max,
                v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "LLC Resonant": lambda: execute_tool(
                "llc_design", v_in=v_in, v_out=v_out, i_out=i_out,
                f_sw_khz=f_sw, q_factor=q_factor,
            ),
            "DAB (Dual Active Bridge)": lambda: execute_tool(
                "dab_design", v1=v1, v2=v2, p_rated=p_rated,
                f_sw_khz=f_sw, phi_deg=phi_deg,
            ),
            "Cascade (Multi-Stage)": lambda: execute_tool(
                "cascade_design", v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
            ),
            "Inductor Design": lambda: execute_tool(
                "inductor_design", inductance_uH=ind_L, i_peak=ind_ipk,
                i_rms=ind_irms, f_sw_khz=f_sw, core_shape=core_shape,
                material=material, b_max_mT=b_max,
            ),
            "Transformer Design": lambda: execute_tool(
                "transformer_design", v_pri=tx_vpri, v_sec=tx_vsec,
                power_W=tx_power, f_sw_khz=f_sw, duty_cycle=tx_duty,
                core_shape=core_shape, material=material, b_max_mT=b_max,
            ),
            "Efficiency Estimate": lambda: execute_tool(
                "efficiency_estimate",
                v_in=v_in, v_out=v_out, i_out=i_out, f_sw_khz=f_sw,
                rds_on_mohm=rds_on, dcr_mohm=dcr, vf_diode=vf_diode,
                t_rise_ns=t_rise_ns, t_fall_ns=t_fall_ns,
            ),
            "Component Recommendation": lambda: json.dumps(
                __import__("pea.components.schema", fromlist=["recommend_components"])
                .recommend_components(v_in, v_out, i_out), indent=2,
            ),
        }
        result = tool_map.get(tool_choice, lambda: "{}")()

        try:
            st.json(json.loads(result))
        except json.JSONDecodeError:
            st.code(result)

# ── Main area: Pareto optimizer ──────────────────────────────────────────
st.header("Pareto Optimizer")
st.caption(
    "Generate DC-DC candidate designs and rank the Pareto front by efficiency, power density, and estimated BOM cost."
)

with st.form("pareto_optimizer_form"):
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        opt_vin_min = st.number_input("V_in min (V)", min_value=0.1, value=36.0, step=1.0)
        opt_vin_nom = st.number_input("V_in nominal (V)", min_value=0.1, value=48.0, step=1.0)
        opt_vin_max = st.number_input("V_in max (V)", min_value=0.1, value=60.0, step=1.0)
    with col_b:
        opt_vout = st.number_input("V_out (V)", min_value=0.1, value=12.0, step=0.5)
        opt_iout = st.number_input("I_out (A)", min_value=0.01, value=20.0, step=0.5)
        opt_isolated = st.checkbox("Require isolation (LLC only in v1)", value=False)
    with col_c:
        opt_fmin = st.number_input("f_sw min (kHz)", min_value=10.0, value=80.0, step=10.0)
        opt_fmax = st.number_input("f_sw max (kHz)", min_value=10.0, value=400.0, step=10.0)
        opt_seed = st.number_input("Seed", min_value=0, value=7, step=1)

    topologies = st.multiselect(
        "Candidate topologies",
        ["Buck", "Boost", "Buck-Boost", "SEPIC", "Cuk", "LLC"],
        default=["Buck", "Boost", "Buck-Boost", "SEPIC", "Cuk", "LLC"],
    )
    col_d, col_e = st.columns(2)
    with col_d:
        pop_size = st.slider("Population size", min_value=16, max_value=160, value=48, step=8)
    with col_e:
        generations = st.slider("Generations", min_value=4, max_value=80, value=18, step=2)
    run_optimizer = st.form_submit_button("Run Pareto Optimization", use_container_width=True)

if run_optimizer:
    try:
        result = optimize_converter_design(
            {
                "v_in_min": opt_vin_min,
                "v_in_nom": opt_vin_nom,
                "v_in_max": opt_vin_max,
                "v_out": opt_vout,
                "i_out": opt_iout,
                "topology_allowlist": topologies,
                "isolation_required": opt_isolated,
                "fsw_range_khz": [opt_fmin, opt_fmax],
            },
            OptimizationConfig(
                population_size=pop_size,
                generations=generations,
                seed=opt_seed,
                max_candidates=120,
                backend="auto",
            ),
        )
        data = result.to_dict()
        st.session_state["pareto_result"] = data
    except Exception as e:
        st.error(str(e))

if "pareto_result" in st.session_state:
    data = st.session_state["pareto_result"]
    if data.get("warnings"):
        st.warning(" | ".join(data["warnings"]))
    st.markdown(f"**Backend:** `{data.get('backend')}`")
    st.info(data.get("ranking_explanation", ""))

    rec = data.get("recommended_candidate")
    if rec:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Recommended", rec["topology"])
        c2.metric("Efficiency", f"{rec['estimated_efficiency_pct']}%")
        c3.metric("Power density", f"{rec['power_density_W_per_L']} W/L")
        c4.metric("BOM estimate", f"${rec['cost_usd']}")

        st.subheader("Recommended Design")
        st.json(rec)

        with st.expander("Export STEP envelope"):
            st.caption("Requires optional CAD dependency: `pip install -e '.[cad]'`.")
            if st.button("Generate STEP for recommended design"):
                try:
                    from pea.cad import export_candidate_step

                    out = Path(tempfile.gettempdir()) / f"pea_{rec['candidate_id']}.step"
                    info = export_candidate_step(rec, out)
                    with open(out, "rb") as f:
                        st.download_button(
                            "Download STEP",
                            data=f,
                            file_name=out.name,
                            mime="application/step",
                        )
                    st.success(f"STEP generated: {info['path']}")
                except Exception as e:
                    st.error(str(e))

    front = data.get("pareto_front") or []
    if front:
        rows = [
            {
                "id": c["candidate_id"],
                "topology": c["topology"],
                "f_kHz": c["frequency_khz"],
                "efficiency_pct": c["estimated_efficiency_pct"],
                "volume_cm3": round(c["volume_mm3"] / 1000, 2),
                "cost_usd": c["cost_usd"],
                "power_density_W_L": c["power_density_W_per_L"],
                "score": c["score"],
            }
            for c in front
        ]
        st.subheader("Pareto Front")
        st.dataframe(rows, use_container_width=True)
        chart_rows = [
            {
                "cost_usd": row["cost_usd"],
                "efficiency_pct": row["efficiency_pct"],
                "volume_cm3": row["volume_cm3"],
            }
            for row in rows
        ]
        st.scatter_chart(chart_rows, x="cost_usd", y="efficiency_pct", size="volume_cm3")

# ── Main area: AI Chat ───────────────────────────────────────────────────
st.header("AI Chat")
st.caption("Ask design questions or provide specs for full AI-assisted design (requires OpenAI API key)")

api_key = os.getenv("OPENAI_API_KEY") or st.text_input(
    "OpenAI API Key", type="password", placeholder="sk-..."
)

if api_key:
    os.environ["OPENAI_API_KEY"] = api_key

    if "agent" not in st.session_state:
        st.session_state.agent = PEAAgent(api_key=api_key)
    if "messages" not in st.session_state:
        st.session_state.messages = []

    agent: PEAAgent = st.session_state.agent

    col_header, col_btn = st.columns([6, 1])
    with col_btn:
        if st.button("Clear chat"):
            agent.clear_history()
            st.session_state.messages = []
            st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("e.g., Design a 12V to 5V 2A Buck converter"):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = agent.chat(prompt)
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})
else:
    st.info("Enter your OpenAI API key above to use the AI chat. Use the sidebar for direct calculations.")

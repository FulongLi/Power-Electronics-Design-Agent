"""
Command-line interface for PEA (Power Electronics AI Agent).
"""

import argparse
import json
import sys

from pea.tools.calculator import get_available_tools

_TOOL_CHOICES = [
    "buck", "boost", "buck_boost",
    "sepic", "cuk",
    "forward", "flyback", "llc", "dab",
    "cascade",
    "inductor", "transformer",
    "recommend", "efficiency",
    "components",
]

_CLI_TO_CALC = {
    "buck": "buck_converter_design",
    "boost": "boost_converter_design",
    "buck_boost": "buck_boost_design",
    "sepic": "sepic_design",
    "cuk": "cuk_design",
    "forward": "forward_design",
    "flyback": "flyback_design",
    "llc": "llc_design",
    "dab": "dab_design",
    "cascade": "cascade_design",
    "inductor": "inductor_design",
    "transformer": "transformer_design",
    "recommend": "topology_recommendation",
    "efficiency": "efficiency_estimate",
}

_ISOLATED_TOOLS = {"flyback", "forward"}


def run_cli():
    """Run the PEA CLI."""
    parser = argparse.ArgumentParser(
        description="PEA - Power Electronics AI Agent. Design assistant for DC-DC converters."
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Chat
    chat_parser = subparsers.add_parser("chat", help="Chat with PEA AI agent (requires OPENAI_API_KEY)")
    chat_parser.add_argument(
        "message", nargs="?", default=None,
        help="Your question or design specs",
    )
    chat_parser.add_argument("-m", "--model", default="gpt-4o-mini", help="OpenAI model")

    # Tool
    tool_parser = subparsers.add_parser("tool", help="Run design tool directly (no API key needed)")
    tool_parser.add_argument("tool_name", choices=_TOOL_CHOICES, help="Design tool to run")
    tool_parser.add_argument("--v-in", type=float, help="Input voltage (V)")
    tool_parser.add_argument("--v-out", type=float, help="Output voltage (V)")
    tool_parser.add_argument("--i-out", type=float, help="Output current (A)")
    tool_parser.add_argument("--v-in-min", type=float, help="Min input voltage (isolated converters)")
    tool_parser.add_argument("--v-in-max", type=float, help="Max input voltage (isolated converters)")
    tool_parser.add_argument("--f-sw", type=float, default=100, help="Switching freq (kHz)")
    tool_parser.add_argument("--isolated", action="store_true", help="Require isolation (recommend)")
    tool_parser.add_argument("--q-factor", type=float, default=0.5, help="Q factor (LLC)")
    tool_parser.add_argument("--rds-on", type=float, default=50, help="MOSFET Rds(on) mΩ (efficiency)")
    tool_parser.add_argument("--dcr", type=float, default=30, help="Inductor DCR mΩ (efficiency)")
    tool_parser.add_argument("--vf-diode", type=float, default=0.5, help="Diode Vf V (efficiency)")
    tool_parser.add_argument("--bidirectional", action="store_true", help="Bidirectional (recommend)")
    # DAB parameters
    tool_parser.add_argument("--v1", type=float, help="Port 1 voltage V (DAB)")
    tool_parser.add_argument("--v2", type=float, help="Port 2 voltage V (DAB)")
    tool_parser.add_argument("--p-rated", type=float, help="Rated power W (DAB)")
    tool_parser.add_argument("--phi-deg", type=float, default=30, help="Phase shift degrees (DAB)")
    # Magnetics parameters
    tool_parser.add_argument("--inductance", type=float, help="Inductance µH (inductor)")
    tool_parser.add_argument("--i-peak", type=float, help="Peak current A (inductor)")
    tool_parser.add_argument("--i-rms", type=float, help="RMS current A (inductor)")
    tool_parser.add_argument("--core-shape", default="EE", help="Core shape (inductor/transformer)")
    tool_parser.add_argument("--material", default="N87", help="Ferrite material")
    tool_parser.add_argument("--b-max", type=float, default=300, help="Max flux density mT")
    # Transformer parameters
    tool_parser.add_argument("--v-pri", type=float, help="Primary voltage V (transformer)")
    tool_parser.add_argument("--v-sec", type=float, help="Secondary voltage V (transformer)")
    tool_parser.add_argument("--power", type=float, help="Power W (transformer)")
    tool_parser.add_argument("--duty", type=float, default=0.45, help="Duty cycle (transformer)")

    # Pareto optimizer
    opt_parser = subparsers.add_parser("optimize", help="Run Pareto DC-DC optimizer (no API key needed)")
    opt_parser.add_argument("--v-in", type=float, help="Nominal input voltage (V)")
    opt_parser.add_argument("--v-in-min", type=float, help="Minimum input voltage (V)")
    opt_parser.add_argument("--v-in-max", type=float, help="Maximum input voltage (V)")
    opt_parser.add_argument("--v-out", type=float, required=True, help="Output voltage (V)")
    opt_parser.add_argument("--i-out", type=float, required=True, help="Output current (A)")
    opt_parser.add_argument(
        "--topology",
        action="append",
        dest="topologies",
        help="Candidate topology; repeat for multiple (default: all v1 topologies)",
    )
    opt_parser.add_argument("--isolated", action="store_true", help="Require isolation (LLC only in v1)")
    opt_parser.add_argument("--f-sw-min", type=float, default=50.0, help="Minimum switching frequency (kHz)")
    opt_parser.add_argument("--f-sw-max", type=float, default=500.0, help="Maximum switching frequency (kHz)")
    opt_parser.add_argument("--population-size", type=int, default=48, help="Optimizer population size")
    opt_parser.add_argument("--generations", type=int, default=18, help="Optimizer generations")
    opt_parser.add_argument("--max-candidates", type=int, default=80, help="Maximum candidates to return")
    opt_parser.add_argument(
        "--backend",
        choices=["auto", "pymoo", "deterministic"],
        default="auto",
        help="Optimizer backend",
    )
    opt_parser.add_argument("--summary", action="store_true", help="Print compact summary instead of full JSON")

    # List tools
    subparsers.add_parser("tools", help="List available design tools")

    args = parser.parse_args()

    if args.command == "tools":
        tools = get_available_tools()
        print("Available design tools:\n")
        for t in tools:
            print(f"  {t['name']}")
            print(f"    {t['description']}")
            print(f"    Params: {', '.join(t['parameters'])}\n")
        return 0

    if args.command == "tool":
        from pea.tools.calculator import execute_tool

        calc_name = _CLI_TO_CALC[args.tool_name]

        if args.tool_name == "components":
            import json as _json
            from pea.components.schema import recommend_components
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: components requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            print(_json.dumps(recommend_components(args.v_in, args.v_out, args.i_out), indent=2))
            return 0

        if args.tool_name in _ISOLATED_TOOLS:
            if not all([args.v_in_min, args.v_in_max, args.v_out, args.i_out]):
                print(f"Error: {args.tool_name} requires --v-in-min, --v-in-max, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in_min=args.v_in_min, v_in_max=args.v_in_max,
                                  v_out=args.v_out, i_out=args.i_out, f_sw_khz=args.f_sw)
        elif args.tool_name == "recommend":
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: recommend requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in=args.v_in, v_out=args.v_out,
                                  i_out=args.i_out, isolated=args.isolated,
                                  bidirectional=args.bidirectional)
        elif args.tool_name == "llc":
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: llc requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in=args.v_in, v_out=args.v_out,
                                  i_out=args.i_out, f_sw_khz=args.f_sw, q_factor=args.q_factor)
        elif args.tool_name == "dab":
            if not all([args.v1, args.v2, args.p_rated]):
                print("Error: dab requires --v1, --v2, --p-rated", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v1=args.v1, v2=args.v2, p_rated=args.p_rated,
                                  f_sw_khz=args.f_sw, phi_deg=args.phi_deg)
        elif args.tool_name == "cascade":
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: cascade requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in=args.v_in, v_out=args.v_out,
                                  i_out=args.i_out, f_sw_khz=args.f_sw)
        elif args.tool_name == "inductor":
            if not all([args.inductance, args.i_peak, args.i_rms]):
                print("Error: inductor requires --inductance, --i-peak, --i-rms", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, inductance_uH=args.inductance, i_peak=args.i_peak,
                                  i_rms=args.i_rms, f_sw_khz=args.f_sw,
                                  core_shape=args.core_shape, material=args.material,
                                  b_max_mT=args.b_max)
        elif args.tool_name == "transformer":
            if not all([args.v_pri, args.v_sec, args.power]):
                print("Error: transformer requires --v-pri, --v-sec, --power", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_pri=args.v_pri, v_sec=args.v_sec,
                                  power_W=args.power, f_sw_khz=args.f_sw,
                                  duty_cycle=args.duty, core_shape=args.core_shape,
                                  material=args.material, b_max_mT=args.b_max)
        elif args.tool_name == "efficiency":
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: efficiency requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in=args.v_in, v_out=args.v_out, i_out=args.i_out,
                                  f_sw_khz=args.f_sw, rds_on_mohm=args.rds_on,
                                  dcr_mohm=args.dcr, vf_diode=args.vf_diode)
        else:
            if not all([args.v_in, args.v_out, args.i_out]):
                print("Error: requires --v-in, --v-out, --i-out", file=sys.stderr)
                return 1
            result = execute_tool(calc_name, v_in=args.v_in, v_out=args.v_out,
                                  i_out=args.i_out, f_sw_khz=args.f_sw)

        print(result)
        return 0

    if args.command == "optimize":
        from pea.optimization import OptimizationConfig, optimize_converter_design

        v_nom = args.v_in
        if v_nom is None and args.v_in_min is None and args.v_in_max is None:
            print("Error: optimize requires --v-in or an input range", file=sys.stderr)
            return 1
        if v_nom is None:
            if args.v_in_min is not None and args.v_in_max is not None:
                v_nom = (args.v_in_min + args.v_in_max) / 2
            else:
                v_nom = args.v_in_min if args.v_in_min is not None else args.v_in_max
        v_min = args.v_in_min if args.v_in_min is not None else v_nom
        v_max = args.v_in_max if args.v_in_max is not None else v_nom
        try:
            result = optimize_converter_design(
                {
                    "v_in_min": v_min,
                    "v_in_nom": v_nom,
                    "v_in_max": v_max,
                    "v_out": args.v_out,
                    "i_out": args.i_out,
                    "topology_allowlist": args.topologies
                    or ["Buck", "Boost", "Buck-Boost", "SEPIC", "Cuk", "LLC"],
                    "isolation_required": args.isolated,
                    "fsw_range_khz": [args.f_sw_min, args.f_sw_max],
                },
                OptimizationConfig(
                    population_size=args.population_size,
                    generations=args.generations,
                    max_candidates=args.max_candidates,
                    backend=args.backend,
                ),
            )
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        data = result.to_dict()
        if args.summary:
            rec = data.get("recommended_candidate")
            print(data.get("ranking_explanation", ""))
            print(f"Backend: {data.get('backend')}")
            print(f"Pareto candidates: {len(data.get('pareto_front') or [])}")
            if rec:
                print(
                    "Recommended: "
                    f"{rec['topology']} @ {rec['frequency_khz']} kHz, "
                    f"{rec['estimated_efficiency_pct']}% efficiency, "
                    f"{rec['power_density_W_per_L']} W/L, "
                    f"${rec['cost_usd']}"
                )
            return 0
        print(json.dumps(data, indent=2))
        return 0

    if args.command == "chat":
        from pea.agent.runner import PEAAgent

        agent = PEAAgent(model=args.model)
        try:
            if args.message:
                msg = args.message
            else:
                print("PEA - Power Electronics AI Agent")
                print("Enter your design specs or question (Ctrl+C to exit):\n")
                msg = input("You: ").strip()
                if not msg:
                    return 0

            response = agent.chat(msg)
            print("\nPEA:", response)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            print("Set OPENAI_API_KEY or use 'pea tool' for direct calculations.", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(run_cli())

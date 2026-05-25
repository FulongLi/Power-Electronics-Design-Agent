# PEA — manual test checklist

## Requirements

- Python 3.9+
- Dependencies: `pip install -r requirements.txt` (or `pip install -e .`)
- OpenAI API key for AI chat tests

---

## Step 1 — Calculator tools (no API key)

These use local math only (no LLM).

### 1.1 List tools

```powershell
cd E:\path\to\PEA
python -m pea.cli tools
```

**Expected:** List of design tools and parameter hints.

### 1.2 Topology recommendation

```powershell
python -m pea.cli tool recommend --v-in 12 --v-out 5 --i-out 2
```

**Expected (example):**
```json
{
  "recommended": "Buck",
  "alternatives": ["Buck-Boost"],
  "rationale": "Buck is optimal for step-down (V_out < V_in). Highest efficiency."
}
```

### 1.3 Buck design

```powershell
python -m pea.cli tool buck --v-in 12 --v-out 5 --i-out 2
```

**Expected (example):**
```json
{
  "topology": "Buck",
  "duty_cycle": 0.417,
  "inductance_uH": 48.61,
  "capacitance_uF": 15.0,
  "switching_frequency_kHz": 100,
  "ripple_current_A": 0.6,
  "ripple_voltage_V": 0.05,
  "notes": "Step-down converter. Use synchronous rectification for high efficiency."
}
```

### 1.4 Other tools (examples)

```powershell
python -m pea.cli tool boost --v-in 5 --v-out 12 --i-out 1
python -m pea.cli tool flyback --v-in-min 9 --v-in-max 18 --v-out 24 --i-out 0.5
```

### 1.5 DAB converter

```powershell
python -m pea.cli tool dab --v1 400 --v2 48 --p-rated 1000
```

**Expected:** DAB design with leakage inductance, currents, ZVS status.

### 1.6 Cascade (multi-stage)

```powershell
python -m pea.cli tool cascade --v-in 230 --v-out 12 --i-out 20
```

**Expected:** Auto-selected cascade pattern (e.g. PFC Boost + LLC).

### 1.7 Inductor design

```powershell
python -m pea.cli tool inductor --inductance 100 --i-peak 5 --i-rms 3 --core-shape EE --material N87
```

**Expected:** Core selection, turns, wire gauge, air gap, loss breakdown.

### 1.8 Transformer design

```powershell
python -m pea.cli tool transformer --v-pri 400 --v-sec 12 --power 500 --core-shape ETD --material N87
```

**Expected:** Core selection, primary/secondary turns, wire sizes, losses.

### 1.9 Component recommendation

```powershell
python -m pea.cli tool components --v-in 12 --v-out 5 --i-out 2
```

**Expected:** Recommended MOSFETs, diodes, and capacitors.

### 1.10 Pareto optimizer (Streamlit)

CLI smoke test:

```powershell
python -m pea.cli optimize --v-in-min 36 --v-in 48 --v-in-max 60 --v-out 12 --i-out 20 --summary
```

**Expected:** Backend line, Pareto candidate count, and recommended design summary.

```powershell
streamlit run app.py
```

In **Pareto Optimizer**, run:

- `V_in`: 36 / 48 / 60 V
- `V_out`: 12 V
- `I_out`: 20 A
- `f_sw`: 80–400 kHz

**Expected:** A recommended design, Pareto table, efficiency/cost scatter chart,
loss breakdown, selected semiconductor and magnetics data.

Optional STEP export:

```powershell
pip install -e ".[cad]"
```

Then click **Generate STEP for recommended design**.

**Expected:** A downloadable STEP envelope model. Without `[cad]`, the UI should
show a clear message asking to install the CAD extra.

---

## Step 2 — AI agent (API key required)

### 2.1 Set API key

**PowerShell:**
```powershell
$env:OPENAI_API_KEY = "sk-your-key"
```

**Or** copy `.env.example` to `.env` and set `OPENAI_API_KEY`.

### 2.2 Test script

```powershell
python scripts/agent_smoke_test.py "Design a 12V to 5V 2A Buck converter"
```

**Expected:** Agent uses tools and returns a design narrative.

### 2.3 Default prompt

```powershell
python scripts/agent_smoke_test.py
```

Default: `Design a 12V to 5V 2A Buck converter`

### 2.4 CLI chat

```powershell
pea chat "Design a 12V to 5V 2A Buck converter"
```

### 2.5 Streamlit

```powershell
streamlit run app.py
```

Open http://localhost:8501 and enter the API key in the UI if needed.

### 2.6 Static / desktop UI

- Open `index.html` in a browser, or run `python -m pea.desktop` / `run_pea_desktop.bat`.
- **Topology Advisor** and **Efficiency estimate** are pinned at the top of the sidebar (always visible). Tabs below list DC-DC / DC-AC / AC-DC / AC-AC.

---

## Step 3 — Troubleshooting

### A: `ModuleNotFoundError: langchain_core`

```powershell
pip install langchain-core langchain-openai
```

### B: `Error: Set OPENAI_API_KEY...`

Set the key as in §2.1.

### C: `ImportError: DLL load failed` (uuid / Windows)

Try: install [VC++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe), use Python 3.10+, or a clean venv with `pip install -r requirements.txt`.

### D: `pea` command not found

```powershell
pip install -e .
```

Or: `python -m pea.cli chat "..."`

---

## Result log (optional)

| Step | Command | Notes |
|------|---------|--------|
| 1.1 | `python -m pea.cli tools` | |
| 1.2 | `python -m pea.cli tool recommend ...` | |
| 1.3 | `python -m pea.cli tool buck ...` | |
| 1.5 | `python -m pea.cli tool dab ...` | DAB converter |
| 1.6 | `python -m pea.cli tool cascade ...` | Multi-stage |
| 1.7 | `python -m pea.cli tool inductor ...` | Magnetics |
| 1.8 | `python -m pea.cli tool transformer ...` | Magnetics |
| 1.9 | `python -m pea.cli tool components ...` | Component rec |
| 2.2 | `python scripts/agent_smoke_test.py "..."` | Needs valid key |

"""
Power Electronics AI Agent - main agent logic with tool calling and RAG.

Uses LangChain structured tools for reliable tool calling with OpenAI.
"""
from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from pea.knowledge.retriever import KnowledgeRetriever
from pea.tools.langchain_tools import get_pea_tools


_TOOL_MAP: dict[str, Any] = {t.name: t for t in get_pea_tools()}

SYSTEM_PROMPT = """You are PEA (Power Electronics AI), an expert assistant for power electronics design.

Your capabilities:
1. Recommend converter topologies (Buck, Boost, Buck-Boost, SEPIC, Cuk, Forward, Flyback, LLC, DAB, cascade) based on specs
2. Calculate design parameters (inductance, capacitance, duty cycle) using your tools
3. Design DAB (Dual Active Bridge) bidirectional isolated converters
4. Design cascade (multi-stage) converters for extreme conversion ratios or AC-DC
5. Estimate converter efficiency and power losses
6. Design magnetic components: inductor core selection, turns, wire, air gap, Steinmetz loss
7. Design power transformers: core selection, turns ratio, wire sizes, loss breakdown
8. Run Pareto optimization across topology, switching frequency, semiconductors, magnetics, efficiency, volume, and cost
9. Answer questions about power electronics theory including solid-state transformers (SST)

When the user provides specifications (V_in, V_out, I_out, etc.):
- First use recommend_topology to suggest a suitable topology (set bidirectional=True if needed)
- Then use the appropriate design tool to calculate parameters
- Optionally use design_inductor or design_transformer for magnetics sizing
- Optionally use estimate_efficiency to estimate losses
- Use optimize_converter_design when the user asks for optimal trade-offs, Pareto fronts, high power density, low cost, or frequency/device optimization
- Present results clearly with units and brief design notes

For bidirectional or EV charging applications, recommend and design DAB converters.
For solid-state transformer (SST) queries, explain the multi-stage architecture and use cascade/DAB tools.
For magnetics, use the built-in core and material library (EE, PQ, RM, ETD, etc. with N87, 3C90, etc.).
For optimized designs, explain the Pareto trade-off and why the recommended point was selected.

Use SI units: V for voltage, A for current, kHz for frequency.
"""


class PEAAgent:
    """
    Power Electronics AI Agent.

    Combines LLM with RAG (knowledge retrieval) and design calculation tools.
    Maintains conversation history across calls for multi-turn dialogue.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        use_rag: bool = True,
        use_vector_store: bool = True,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.use_rag = use_rag
        self.retriever = KnowledgeRetriever(use_vector_store=use_vector_store) if use_rag else None
        self._llm = None
        self._history: list[BaseMessage] = []

    @property
    def history(self) -> list[BaseMessage]:
        """Return the conversation history (excluding system prompt)."""
        return list(self._history)

    def clear_history(self) -> None:
        """Reset conversation history."""
        self._history.clear()

    def _get_llm(self):
        """Lazy load LLM with structured tools bound."""
        if self._llm is not None:
            return self._llm

        if not self.api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key."
            )

        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            temperature=0.2,
        )
        self._llm = llm.bind_tools(get_pea_tools())
        return self._llm

    def _build_system_prompt(self, context: str | None) -> str:
        """Build system prompt with optional RAG context."""
        prompt = SYSTEM_PROMPT
        if context:
            prompt += f"\n\nRelevant knowledge from database:\n{context}\n"
        return prompt

    def chat(self, user_message: str, max_tool_rounds: int = 5) -> str:
        """
        Process user message and return agent response.

        Maintains conversation history so follow-up questions work naturally.
        RAG context is retrieved fresh for each message and injected into
        the system prompt so the LLM always has relevant knowledge.
        """
        context = None
        if self.use_rag and self.retriever:
            docs = self.retriever.search(user_message, top_k=4)
            if docs:
                context = "\n---\n".join(docs)

        self._history.append(HumanMessage(content=user_message))

        messages: list[BaseMessage] = [
            SystemMessage(content=self._build_system_prompt(context)),
            *self._history,
        ]

        llm = self._get_llm()
        tool_rounds = 0

        while tool_rounds < max_tool_rounds:
            response_msg = llm.invoke(messages)
            tool_calls = getattr(response_msg, "tool_calls", None) or []

            if not tool_calls:
                self._history.append(
                    AIMessage(content=response_msg.content or "")
                )
                return response_msg.content or str(response_msg)

            messages.append(response_msg)

            for tc in tool_calls:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", "")

                tool_fn = _TOOL_MAP.get(name) if name else None
                if tool_fn:
                    try:
                        result = tool_fn.invoke(args)
                    except Exception as e:
                        result = f"Error: {e}"
                else:
                    result = f"Unknown tool: {name}"

                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc_id or "")
                )

            tool_rounds += 1

        final_msg = llm.invoke(messages)
        self._history.append(AIMessage(content=final_msg.content or ""))
        return final_msg.content or str(final_msg)

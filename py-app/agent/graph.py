from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .nodes import generate_clips, generate_procedure, generate_presigned_url
from .state import ExperimentState


def _route(state: ExperimentState) -> str:
    """Route to END if any node set an error, otherwise continue."""
    return END if state.get("error") else "continue"


builder = StateGraph(ExperimentState)

builder.add_node("generate_procedure", generate_procedure)
builder.add_node("generate_clips", generate_clips)
builder.add_node("generate_presigned_url", generate_presigned_url)

builder.add_edge(START, "generate_procedure")

builder.add_conditional_edges(
    "generate_procedure",
    _route,
    {"continue": "generate_clips", END: END},
)
builder.add_conditional_edges(
    "generate_clips",
    _route,
    {"continue": "generate_presigned_url", END: END},
)

builder.add_edge("generate_presigned_url", END)

chemistry_graph = builder.compile()

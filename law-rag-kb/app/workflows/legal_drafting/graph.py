from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.workflows.legal_drafting import nodes
from app.workflows.legal_drafting.state import LegalDraftingState


def build_graph(checkpointer=None):
    graph = StateGraph(LegalDraftingState)
    graph.add_node("load_context", nodes.load_context)
    graph.add_node("extract_elements", nodes.extract_elements)
    graph.add_node("compute_values", nodes.compute_values)
    graph.add_node("detect_gaps", nodes.detect_gaps)
    graph.add_node("identify_issues", nodes.identify_issues)
    graph.add_node("retrieve_authorities", nodes.retrieve_authorities)
    graph.add_node("create_writing_plan", nodes.create_writing_plan)
    graph.add_node("draft_claims", nodes.draft_claims)
    graph.add_node("draft_facts", nodes.draft_facts)
    graph.add_node("draft_legal_basis", nodes.draft_legal_basis)
    graph.add_node("draft_evidence", nodes.draft_evidence)
    graph.add_node("assemble_sections", nodes.assemble_sections)
    graph.add_node("review_facts", nodes.review_facts)
    graph.add_node("review_law", nodes.review_law)
    graph.add_node("review_evidence", nodes.review_evidence)
    graph.add_node("review_template", nodes.review_template)
    graph.add_node("review_expression", nodes.review_expression)
    graph.add_node("finalize_review", nodes.finalize_review)
    graph.add_node("rewrite_sections", nodes.rewrite_sections)
    graph.add_node("render_document", nodes.render_document)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "extract_elements")
    graph.add_edge("extract_elements", "compute_values")
    graph.add_edge("compute_values", "detect_gaps")
    graph.add_conditional_edges(
        "detect_gaps",
        nodes.should_continue_after_gaps,
        {"wait": END, "continue": "identify_issues"},
    )
    graph.add_edge("identify_issues", "retrieve_authorities")
    graph.add_edge("retrieve_authorities", "create_writing_plan")
    graph.add_edge("create_writing_plan", "draft_claims")
    graph.add_edge("create_writing_plan", "draft_facts")
    graph.add_edge("create_writing_plan", "draft_legal_basis")
    graph.add_edge("create_writing_plan", "draft_evidence")
    graph.add_edge(
        ["draft_claims", "draft_facts", "draft_legal_basis", "draft_evidence"],
        "assemble_sections",
    )
    graph.add_edge("assemble_sections", "review_facts")
    graph.add_edge("review_facts", "review_law")
    graph.add_edge("review_law", "review_evidence")
    graph.add_edge("review_evidence", "review_template")
    graph.add_edge("review_template", "review_expression")
    graph.add_edge("review_expression", "finalize_review")
    graph.add_conditional_edges(
        "finalize_review",
        nodes.should_continue_after_review,
        {"wait": END, "rewrite": "rewrite_sections", "render": "render_document"},
    )
    graph.add_edge("rewrite_sections", "review_facts")
    graph.add_edge("render_document", END)
    return graph.compile(checkpointer=checkpointer)

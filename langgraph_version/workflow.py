from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph_version.graph_state import DrugWorkflowState
from langgraph_version.nodes import (
    ingest_pdf, extract_fields_node, validate_node, evaluate_node,
    route_after_ingest, route_after_evaluate, await_review_node,
    route_decision, reevaluate_node, approval_node, rejection_node
)

def build_graph(checkpointer=None):
    graph = StateGraph(DrugWorkflowState)
    graph.add_node("ingest_pdf", ingest_pdf)
    graph.add_node("extract_fields", extract_fields_node)
    graph.add_node("validate_fields", validate_node)
    graph.add_node("evaluate_report", evaluate_node)
    graph.add_node("await_review", await_review_node)
    graph.add_node("reevaluate", reevaluate_node)
    graph.add_node("approved", approval_node)
    graph.add_node("rejected", rejection_node)

    graph.add_edge(START, "ingest_pdf")
    graph.add_conditional_edges("ingest_pdf", route_after_ingest,
                                {"error": END, "extract": "extract_fields"})
    graph.add_edge("extract_fields", "validate_fields")
    graph.add_edge("validate_fields", "evaluate_report")
    graph.add_conditional_edges("evaluate_report", route_after_evaluate,
                                {"error": END, "await_review": "await_review"})
    graph.add_conditional_edges("await_review", route_decision, {
        "approved": "approved", "rejected": "rejected",
        "reevaluate": "reevaluate", "await_review": END
    })
    graph.add_edge("reevaluate", "await_review")
    graph.add_edge("approved", END)
    graph.add_edge("rejected", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())

def run_langgraph_workflow(pdf_path, report_id, filename=None):
    app = build_graph()
    initial = {
        "pdf_path": str(pdf_path), "report_id": report_id,
        "filename": filename or str(pdf_path), "workflow": "langgraph",
        "reviewer_decision": ""
    }
    result = app.invoke(initial, config={"configurable": {"thread_id": report_id}})
    if result.get("error"):
        raise ValueError(result["error"])
    return {
        "report_id": report_id, "source_text": result.get("source_text", ""),
        "pages": result.get("pages", {}), "extracted": result["extracted"],
        "current": result["current"], "validation": result["validation"],
        "evaluation": result["evaluation"], "extraction_mode": result.get("extraction_mode", "unknown"),
        "workflow": "langgraph", "processing_status": result.get("processing_status", "PROCESSED"),
        "review_status": "PENDING"
    }

def run_review_decision(state, decision, reviewer="", comment=""):
    """Run the human decision through a small review-only graph.

    The PDF-processing graph is not re-run, so reviewer edits are preserved.
    A production app should use a durable checkpointer and resume the original
    graph thread rather than constructing a review-only graph for each decision.
    """
    review_graph = StateGraph(DrugWorkflowState)
    review_graph.add_node("await_review", await_review_node)
    review_graph.add_node("reevaluate", reevaluate_node)
    review_graph.add_node("approved", approval_node)
    review_graph.add_node("rejected", rejection_node)
    review_graph.add_edge(START, "await_review")
    review_graph.add_conditional_edges("await_review", route_decision, {
        "approved": "approved", "rejected": "rejected",
        "reevaluate": "reevaluate", "await_review": END
    })
    review_graph.add_edge("reevaluate", END)
    review_graph.add_edge("approved", END)
    review_graph.add_edge("rejected", END)
    app = review_graph.compile(checkpointer=MemorySaver())
    graph_state = {
        "report_id": state["report_id"],
        "current": state["current"],
        "validation": state["validation"],
        "evaluation": state["evaluation"],
        "reviewer_decision": decision.upper(),
        "reviewer": reviewer,
        "review_comment": comment,
        "workflow": "langgraph",
    }
    return app.invoke(graph_state, config={"configurable": {"thread_id": state["report_id"]}})

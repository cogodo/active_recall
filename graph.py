from langgraph.graph import StateGraph, END

from nodes import GraphState, parse_pdf_node, generate_questions_node

# Define the workflow
workflow = StateGraph(GraphState)

# Add nodes
workflow.add_node("parse_pdf", parse_pdf_node)
workflow.add_node("generate_questions", generate_questions_node)

# Define edges
workflow.set_entry_point("parse_pdf")
workflow.add_edge("parse_pdf", "generate_questions")
workflow.add_edge("generate_questions", END)

# Compile the graph
app = workflow.compile()

# Optional: Visualize the graph (requires graphviz)
# try:
#     app.get_graph().draw_mermaid_png(output_file_path="graph_visualization.png")
#     print("Graph visualization saved to graph_visualization.png")
# except Exception as e:
#     print(f"Could not generate graph visualization: {e}") 
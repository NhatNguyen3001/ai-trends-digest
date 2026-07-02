"""The agentic deep-dive engine (Phase 5).

An on-demand, web-first RAG loop that produces a deeper, cited write-up for a
chosen digest item. LangGraph orchestrates the nodes; the nodes call Tavily
(retrieval) and the existing ``anthropic`` client (reasoning).
"""

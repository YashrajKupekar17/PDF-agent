"""PDF-grounded conversational agent."""
import os

from app.config import settings

# Wire LangSmith tracing if a key is configured.
# Uses LangChain's LANGSMITH_* env-var convention; once these are set BEFORE
# any langchain/langgraph code runs, every node and LLM call is auto-traced.
if settings.langsmith_api_key:
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_TRACING", "true")

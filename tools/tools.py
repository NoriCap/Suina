"""Tools the model can call: JSON schemas, implementations and a safe runner.

This module has no dependency on the model or the Discord client, so it can be
imported (and tested) on its own.
"""
import datetime
import json

import memory_rag.memory as mem

# ---------------------------------------------------------------------------
# 1. Descriptions shown to the model (sent to /apply-template)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tool_get_date",
            "description": "Get the current date and time",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_insert_data",
            "description": (
                "Save a piece of information to long-term memory. "
                "Use it when the user shares a fact worth remembering."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The information to store, written as a clear standalone sentence.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Short topic label, e.g. 'history', 'cooking', 'user_preferences'.",
                    },
                },
                "required": ["text", "subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tool_search_data",
            "description": (
                "Search long-term memory for facts previously saved about the user or past topics. "
                "Use it BEFORE answering when the question may depend on something the user told you earlier "
                "(their location, preferences, projects...). Do not use it for general knowledge."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to look for, phrased as a short question or keywords, e.g. 'where does the user live'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 2. Implementations
# ---------------------------------------------------------------------------
def tool_get_date() -> str:
    return datetime.datetime.now().isoformat()


def tool_insert_data(text: str, subject: str) -> str:
    print("text: ", text, "subject: ", subject)
    res = mem.insert_data(text, subject)
    return json.dumps({"status": "ok", "insert_count": res.get("insert_count", 1)})


def tool_search_data(query: str) -> str:
    print("search query: ", query)
    results = mem.search(query, limit=3)
    if not results:
        return json.dumps({"status": "ok", "results": [], "note": "nothing found in memory"})
    return json.dumps({"status": "ok", "results": results}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 3. Registry: tool name -> function
# ---------------------------------------------------------------------------
TOOL_REGISTRY = {
    "tool_get_date": tool_get_date,
    "tool_insert_data": tool_insert_data,
    "tool_search_data": tool_search_data,
}


# ---------------------------------------------------------------------------
# 4. Runner: always returns a string, never raises (errors go back to the model)
# ---------------------------------------------------------------------------
def run_tool(name: str, args: dict | None = None) -> str:
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool {name}"})
    try:
        result = fn(**(args or {}))
    except Exception as e:  # bad/missing arguments, DB error, ...
        return json.dumps({"error": str(e)})
    return result if isinstance(result, str) else json.dumps(result)
"""State LangGraph agent BizIntel AI - sederhana dan typed.

- messages   : histori percakapan (Human/AI/Tool message, termasuk tool
               calls), dimerge oleh reducer ``add_messages`` bawaan LangGraph.
- tools_used : nama tool yang dipanggil, append-only (reducer ``operator.add``)
               untuk audit dan field ``tools_used`` di response API.
"""

import operator
from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    tools_used: Annotated[list[str], operator.add]

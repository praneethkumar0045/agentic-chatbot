import ast
import logging
import math
import operator
from typing import TypedDict, Annotated

from langchain_tavily import TavilySearch
from langgraph.graph.message import add_messages
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode, tools_condition

from app.core import settings

logger = logging.getLogger(__name__)
SYSTEM_PROMPT = (
    "For current or fast-changing information, use web search before answering. "
    "Use the search results as your source of truth and mention relevant sources "
    "when appropriate."
)


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL or "gemini-3.5-flash",
    temperature=settings.LLM_TEMPERATURE,
    max_tokens=int(settings.MAX_OUTPUT_TOKENS) if settings.MAX_OUTPUT_TOKENS else None,
    timeout=None,
    max_retries=2,
)

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _evaluate_arithmetic(node):
    if isinstance(node, ast.Expression):
        return _evaluate_arithmetic(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        if isinstance(node.value, int) and node.value.bit_length() > 1024:
            raise ValueError("Number is too large.")
        if isinstance(node.value, float) and not math.isfinite(node.value):
            raise ValueError("Number must be finite.")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_arithmetic(node.left)
        right = _evaluate_arithmetic(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 100:
                raise ValueError("Exponent must be between -100 and 100.")
            if isinstance(left, int) and isinstance(right, int) and left.bit_length() * right > 4096:
                raise ValueError("Result is too large.")
        result = _BINARY_OPERATORS[type(node.op)](left, right)
        if isinstance(result, int) and result.bit_length() > 4096:
            raise ValueError("Result is too large.")
        if type(result) not in {int, float}:
            raise ValueError("Result must be a real number.")
        if isinstance(result, float) and not math.isfinite(result):
            raise ValueError("Result is not finite.")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate_arithmetic(node.operand))
    raise ValueError("Only basic arithmetic expressions are supported.")


@tool
def calculator(expression: str) -> str:
    """Calculate a basic arithmetic expression using +, -, *, /, //, %, **, and parentheses."""
    if len(expression) > 256:
        return "Error: Expression is too long."
    try:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 64:
            return "Error: Expression is too complex."
        return str(_evaluate_arithmetic(tree))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as error:
        return f"Error: {error}"


tools = [calculator]
if settings.TAVILY_API_KEY:
    tools.append(TavilySearch(max_results=5, tavily_api_key=settings.TAVILY_API_KEY))
else:
    logger.warning("TAVILY_API_KEY is not configured; web search is disabled.")

def _build_chatbot(model, search_tools):
    model_with_tools = model.bind_tools(search_tools) if search_tools else model

    def chat_node(state: ChatState):
        return {"messages": [model_with_tools.invoke(state["messages"])]}

    graph = StateGraph(ChatState)
    graph.add_node("chat_node", chat_node)
    graph.add_edge(START, "chat_node")
    if search_tools:
        graph.add_node("tools", ToolNode(search_tools))
        graph.add_conditional_edges("chat_node", tools_condition)
        graph.add_edge("tools", "chat_node")
    else:
        graph.add_edge("chat_node", END)
    return graph.compile()


chatbot = _build_chatbot(llm, tools)


def _to_base_message(m):
    role = (m.role or "").lower()
    content = m.content or ""
    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant" or role == "ai":
        return AIMessage(content=content)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="tool")
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


def chat(messages, thread_id: str):
    base_msgs = [_to_base_message(x) for x in messages]
    state = {"messages": [SystemMessage(content=SYSTEM_PROMPT), *base_msgs]}
    result = chatbot.invoke(state)
    return result["messages"]


def stream_chat(messages, thread_id: str):
    base_msgs = [_to_base_message(x) for x in messages]
    state = {"messages": [SystemMessage(content=SYSTEM_PROMPT), *base_msgs]}
    for message_chunk, _metadata in chatbot.stream(state, stream_mode="messages"):
        yield message_chunk

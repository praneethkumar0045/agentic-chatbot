from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.schemas.chat import ChatMessage


def content_to_text(content):
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
        return "".join(text_parts)
    if content is None:
        return ""
    return content if isinstance(content, str) else str(content)


def message_to_schema(message) -> ChatMessage:
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, ToolMessage):
        role = "tool"
    elif isinstance(message, SystemMessage):
        role = "system"
    else:
        message_type = getattr(message, "type", None) or getattr(message, "role", None) or "assistant"
        role = "assistant" if message_type == "thought" else message_type
    return ChatMessage(role=role, content=content_to_text(getattr(message, "content", "")))

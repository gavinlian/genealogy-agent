"""从大模型响应中提取可用文本"""


def extract_anthropic_text(message) -> str:
    """
    Anthropic 兼容接口可能返回 ThinkingBlock + TextBlock。
    只拼接 type=text 的块，忽略 thinking。
    """
    if not message or not getattr(message, "content", None):
        return ""

    parts: list[str] = []
    for block in message.content:
        block_type = getattr(block, "type", None)
        # 只用 getattr，避免 ThinkingBlock 无 .text 时抛 AttributeError
        text = getattr(block, "text", None)
        if block_type == "text" and text:
            parts.append(text)
    return "".join(parts).strip()

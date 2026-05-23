"""智能体状态与能力描述"""

from .config import AGENT_NAME, AGENT_VERSION, DEFAULT_OCR, DEFAULT_PARSE, SUPPORTED_TASKS


def get_agent_status(
    *,
    ocr_configured: bool,
    parse_configured: bool,
    ocr_selection: dict,
    parse_selection: dict,
) -> dict:
    """返回族谱智能体当前能力与 AI 就绪状态"""
    ai_ready = ocr_configured and parse_configured
    return {
        "name": AGENT_NAME,
        "version": AGENT_VERSION,
        "description": "本地优先的族谱领域 AI 智能体，负责扫描建谱、校验与族谱管理",
        "domain": "genealogy",
        "tasks": SUPPORTED_TASKS,
        "ai": {
            "ready": ai_ready,
            "ocr": {
                "configured": ocr_configured,
                "provider": ocr_selection.get("provider", DEFAULT_OCR["provider"]),
                "model": ocr_selection.get("model", DEFAULT_OCR["model"]),
            },
            "parse": {
                "configured": parse_configured,
                "provider": parse_selection.get("provider", DEFAULT_PARSE["provider"]),
                "model": parse_selection.get("model", DEFAULT_PARSE["model"]),
            },
        },
        "modes": {
            "without_ai": ["crud", "import", "export", "validate", "tree", "graph", "generate"],
            "with_ai": ["scan", "ocr", "parse", "search", "generate"],
        },
    }

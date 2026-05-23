"""智能体常量与 Provider 元数据"""

AGENT_NAME = "族见族谱智能体"
AGENT_VERSION = "1.0.0"

SUPPORTED_TASKS = [
    "scan",       # 扫描建谱：OCR → 解析 → 自动整理 → 校验
    "generate",   # 自动整理族谱：推理关系 + 树预览
    "validate",   # 数据校验
    "crud",       # 族谱增删改查
    "import",     # JSON 导入
    "export",     # JSON 导出
]

DEFAULT_OCR = {"provider": "minimax", "model": "MiniMax-M2.7"}
DEFAULT_PARSE = {"provider": "minimax", "model": "MiniMax-M2.7"}

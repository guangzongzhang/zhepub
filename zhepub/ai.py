"""调用国产 AI 大模型（OpenAI 兼容接口）。

所有支持的供应商都使用 /chat/completions 形式，仅在 endpoint 和环境变量名上不同。
使用 stdlib 的 urllib 调用，避免新增 PyPI 依赖。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtCore import QSettings

# ============================================================ 供应商预设
AI_PROVIDERS: dict[str, dict] = {
    "通义千问 (阿里)": {
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen-plus",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "DeepSeek": {
        "endpoint": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "智谱 GLM": {
        "endpoint": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "model": "glm-4-flash",
        "env_key": "ZHIPUAI_API_KEY",
    },
    "月之暗面 Kimi": {
        "endpoint": "https://api.moonshot.cn/v1/chat/completions",
        "model": "moonshot-v1-8k",
        "env_key": "MOONSHOT_API_KEY",
    },
    "文心大模型 (百度)": {
        "endpoint": "https://qianfan.baidubce.com/v2/chat/completions",
        "model": "ernie-4.0-8k-latest",
        "env_key": "QIANFAN_API_KEY",
    },
}

DEFAULT_PROVIDER = "DeepSeek"

SYSTEM_PROMPT = (
    "你是一位 EPUB 电子书编辑助手，精通 XHTML 1.1 / EPUB 3 和 CSS 排版，"
    "尤其熟悉中文电子书的版式需求（如首行缩进、分页、字体嵌入、中英文混排）。"
    "用户可能会发送选中的代码片段并请你解释或修改。"
    "回答请简洁清晰，给出可直接套用的代码示例时使用三反引号代码块，"
    "不要用 HTML 标签包裹示例。"
)


# ============================================================ 配置读取
def resolve_config(settings: QSettings) -> dict:
    """合并 QSettings 覆盖值、环境变量、默认值，返回实际调用配置。

    返回字段：provider / endpoint / model / api_key
    """
    provider = settings.value("ai/provider", DEFAULT_PROVIDER, type=str)
    preset = AI_PROVIDERS.get(provider, AI_PROVIDERS[DEFAULT_PROVIDER])

    endpoint = settings.value("ai/endpoint", "", type=str) or preset["endpoint"]
    model = settings.value("ai/model", "", type=str) or preset["model"]

    # 优先用 UI 配置的 key，其次环境变量
    api_key = settings.value("ai/api_key", "", type=str) or os.environ.get(preset["env_key"], "")

    return {
        "provider": provider,
        "endpoint": endpoint,
        "model": model,
        "api_key": api_key,
        "env_key": preset["env_key"],
    }


# ============================================================ HTTP 调用
def chat(config: dict, user_msg: str, context_code: str | None = None) -> str:
    """同步调用一次 chat completion。失败时抛出 RuntimeError。"""
    if not config.get("api_key"):
        env_hint = config.get("env_key", "")
        raise RuntimeError(
            "未配置 API Key。请到 AI > AI 设置 中填写，"
            + (f"或设置环境变量 {env_hint}。" if env_hint else "")
        )

    user_content = user_msg.strip()
    if context_code:
        user_content += f"\n\n相关代码片段：\n```\n{context_code}\n```"

    body = {
        "model": config["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config["endpoint"],
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = _extract_error_message(e)
        raise RuntimeError(f"AI 接口返回 HTTP {e.code}：{detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 AI 服务：{e.reason}") from None
    except TimeoutError:
        raise RuntimeError("AI 请求超时（60 秒）。") from None

    try:
        payload = json.loads(raw)
        # OpenAI 兼容返回结构：choices[0].message.content
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"无法解析 AI 返回：{raw[:300]}") from e


def _extract_error_message(e: urllib.error.HTTPError) -> str:
    """从 HTTP 错误响应中尝试提取 message 字段。"""
    try:
        body = e.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        err = payload.get("error") or payload
        if isinstance(err, dict):
            return err.get("message") or err.get("code") or body[:200]
        return str(err)[:200]
    except Exception:
        return ""


# ============================================================ 异步 worker
class AIWorker(QObject):
    """在 QThread 中运行 chat()。"""

    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config: dict, user_msg: str, context_code: str | None = None):
        super().__init__()
        self._config = config
        self._user_msg = user_msg
        self._context_code = context_code

    def run(self) -> None:
        try:
            text = chat(self._config, self._user_msg, self._context_code)
            self.finished.emit(text)
        except RuntimeError as e:
            self.failed.emit(str(e))
        except Exception as e:  # 兜底
            self.failed.emit(f"未知错误：{e}")


def make_worker(settings: QSettings, user_msg: str, context_code: str | None = None) -> tuple[QThread, AIWorker]:
    """便利函数：构造一个 QThread + AIWorker 并把 worker 移到线程。调用方负责启动和清理。"""
    config = resolve_config(settings)
    thread = QThread()
    worker = AIWorker(config, user_msg, context_code)
    worker.moveToThread(thread)
    return thread, worker

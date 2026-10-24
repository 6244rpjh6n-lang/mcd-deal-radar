"""极简 MCP Streamable HTTP 客户端（仅使用 Python 标准库）。

只实现了本 Skill 需要的三个方法：initialize / tools/list / tools/call。
协议参考：https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

DEFAULT_URL = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"


class McpError(RuntimeError):
    """MCP 调用失败（网络、鉴权、协议或工具返回错误）。"""


def _flatten(result):
    """把 tools/call 的 content 数组压平成 Python 对象。

    麦当劳 MCP 的多数工具把结构化结果以 JSON 字符串放在 text 内容块里，
    这里优先按 JSON 解析，解析不了就原样返回文本。
    """
    parts = result.get("content") or []
    texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    raw = "\n".join(t for t in texts if t).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class McpClient:
    def __init__(self, url=None, token=None, timeout=30):
        self.url = (url or os.environ.get("MCD_MCP_URL") or DEFAULT_URL).strip()
        self.token = (token or os.environ.get("MCD_MCP_TOKEN") or "").strip()
        if not self.token:
            raise McpError(
                "缺少 MCP Token。请先设置环境变量：\n"
                "  Windows (PowerShell): $env:MCD_MCP_TOKEN=\"你的Token\"\n"
                "  macOS / Linux:        export MCD_MCP_TOKEN=\"你的Token\""
            )
        self.timeout = timeout
        self.session_id = None
        self._id = 0

    # ------------------------------------------------------------------ 底层
    def _post(self, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer " + self.token,
            "User-Agent": "mcd-deal-radar/1.0",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        req = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                sid = resp.headers.get("Mcp-Session-Id")
                if sid:
                    self.session_id = sid
                ctype = resp.headers.get("Content-Type", "")
                return ctype, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            hint = {
                401: "MCP Token 无效、已过期或未提供",
                403: "无权限（检查 Token 与服务协议是否已同意）",
                429: "触发限流（600 次/分钟），请降低频率",
            }.get(exc.code, "")
            raise McpError(f"HTTP {exc.code} {hint} {body}".strip()) from None
        except urllib.error.URLError as exc:
            raise McpError(f"网络不可达：{exc.reason}") from None

    @staticmethod
    def _parse(ctype, text):
        """兼容 application/json 与 text/event-stream 两种响应。"""
        if "text/event-stream" in (ctype or ""):
            chunks = []
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("data:"):
                    piece = line[5:].strip()
                    if piece and piece != "[DONE]":
                        chunks.append(piece)
            if not chunks:
                raise McpError("SSE 响应为空")
            return json.loads(chunks[-1])
        if not text.strip():
            return {}
        return json.loads(text)

    def _rpc(self, method, params=None):
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            payload["params"] = params
        ctype, text = self._post(payload)
        msg = self._parse(ctype, text)
        if msg.get("error"):
            err = msg["error"]
            raise McpError(f"{err.get('message', err)} (code={err.get('code')})")
        return msg.get("result", {})

    # ------------------------------------------------------------------ 协议
    def initialize(self):
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-deal-radar", "version": "1.0.0"},
            },
        )
        # 通知服务端握手完成（无 id、无返回值）
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return result

    def list_tools(self):
        return self._rpc("tools/list", {}).get("tools", [])

    def call_tool(self, name, arguments=None):
        """调用一个工具，返回已解析的结果（dict / list / str）。"""
        result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if result.get("isError"):
            raise McpError("工具返回错误：" + str(_flatten(result))[:300])
        return _flatten(result)

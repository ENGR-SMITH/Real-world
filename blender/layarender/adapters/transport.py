"""Transports for talking to an MCP server, kept independent of any particular server.

The workflow owns *what* to call and in what order; a transport owns *how* the call reaches a
server. Three implementations ship here, and each is honest about what it can do:

``RecordingTransport``  never executes anything. It records every call as a request and returns
                        the response a caller supplied (or a ``NotExecuted`` marker). This is the
                        shadow mode the doc's rollout stage 2 asks for: read, plan, and record,
                        with automatic writes disabled.
``JsonFileTransport``   reads a JSONL file of responses keyed by call index. It is how the agent
                        host -- which actually holds the MCP connection -- feeds real results
                        back into an offline control-plane run.
``McpClientTransport``  wraps the official ``mcp`` Python SDK when it is installed, for a
                        programmatic run against a stdio server (for example
                        ``laya-mcp-server`` or a Blender MCP server).

Nothing here retries silently: the doc requires a bounded retry policy, and the caller
(:mod:`layarender.adapters.render_mcp`) owns it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class TransportError(RuntimeError):
    """The transport could not deliver or read a call."""


class NotExecuted(RuntimeError):
    """The call was recorded but deliberately not executed (shadow mode, no response supplied)."""


@dataclass
class McpCall:
    index: int
    tool: str
    arguments: Dict[str, Any]
    read_only: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "tool": self.tool, "arguments": self.arguments,
                "read_only": self.read_only}


@dataclass
class McpResponse:
    index: int
    tool: str
    ok: bool
    payload: Any = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"index": self.index, "tool": self.tool, "ok": self.ok, "payload": self.payload,
                "error": self.error, "latency_ms": self.latency_ms}


class McpTransport:
    """The interface the Render MCP adapter depends on."""

    name = "transport"

    def call(self, tool: str, arguments: Dict[str, Any], read_only: bool = True) -> Any:
        raise NotImplementedError

    def calls(self) -> List[McpCall]:
        return []

    def responses(self) -> List[McpResponse]:
        return []


@dataclass
class RecordingTransport(McpTransport):
    """Record every call; execute nothing unless a response was supplied up front."""

    name: str = "recording"
    responses_by_tool: Dict[str, List[Any]] = field(default_factory=dict)
    _calls: List[McpCall] = field(default_factory=list, init=False)
    _responses: List[McpResponse] = field(default_factory=list, init=False)
    fail_tools: Dict[str, str] = field(default_factory=dict)

    def call(self, tool: str, arguments: Dict[str, Any], read_only: bool = True) -> Any:
        index = len(self._calls)
        self._calls.append(McpCall(index=index, tool=tool, arguments=dict(arguments),
                                   read_only=read_only))
        if tool in self.fail_tools:
            error = self.fail_tools[tool]
            self._responses.append(McpResponse(index=index, tool=tool, ok=False, error=error))
            raise TransportError(error)
        queue = self.responses_by_tool.get(tool)
        if queue:
            payload = queue.pop(0)
            self._responses.append(McpResponse(index=index, tool=tool, ok=True, payload=payload))
            return payload
        self._responses.append(McpResponse(index=index, tool=tool, ok=False,
                                           error="recorded only (shadow mode)"))
        raise NotExecuted("call %d (%s) was recorded, not executed" % (index, tool))

    def calls(self) -> List[McpCall]:
        return list(self._calls)

    def responses(self) -> List[McpResponse]:
        return list(self._responses)

    def write_requests(self, path: str) -> None:
        """Persist the recorded calls so a host can execute them against the real server."""
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            for call in self._calls:
                handle.write(json.dumps(call.to_dict()) + "\n")


@dataclass
class JsonFileTransport(McpTransport):
    """Replay responses from a JSONL file, matched to calls in order.

    Each line is ``{"tool": ..., "ok": true, "payload": ...}``. A line whose ``ok`` is false
    raises :class:`TransportError`, which the caller records as a failed tool call rather than a
    silent success.
    """

    path: str
    name: str = "json-file"
    _index: int = field(default=0, init=False)
    _calls: List[McpCall] = field(default_factory=list, init=False)
    _responses: List[McpResponse] = field(default_factory=list, init=False)
    _replay: List[Dict[str, Any]] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if not os.path.exists(self.path):
            raise TransportError("response file not found: %s" % self.path)
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    self._replay.append(json.loads(line))

    def call(self, tool: str, arguments: Dict[str, Any], read_only: bool = True) -> Any:
        index = len(self._calls)
        self._calls.append(McpCall(index=index, tool=tool, arguments=dict(arguments),
                                   read_only=read_only))
        if self._index >= len(self._replay):
            self._responses.append(McpResponse(index=index, tool=tool, ok=False,
                                               error="no scripted response left"))
            raise TransportError("no scripted response for call %d (%s)" % (index, tool))
        entry = self._replay[self._index]
        self._index += 1
        recorded_tool = entry.get("tool")
        if recorded_tool and recorded_tool != tool:
            self._responses.append(McpResponse(index=index, tool=tool, ok=False,
                                               error="scripted response is for %s" % recorded_tool))
            raise TransportError("call %d expected %s but the script answers %s"
                                 % (index, tool, recorded_tool))
        if not entry.get("ok", True):
            error = entry.get("error") or "scripted failure"
            self._responses.append(McpResponse(index=index, tool=tool, ok=False, error=error))
            raise TransportError(error)
        payload = entry.get("payload")
        self._responses.append(McpResponse(index=index, tool=tool, ok=True, payload=payload))
        return payload

    def calls(self) -> List[McpCall]:
        return list(self._calls)

    def responses(self) -> List[McpResponse]:
        return list(self._responses)


class McpClientTransport(McpTransport):
    """Call a real MCP stdio server through the official ``mcp`` Python SDK.

    The SDK is imported lazily so the workflow runs without it; a missing SDK is reported as a
    capability gap, not swallowed.
    """

    name = "mcp-sdk"

    def __init__(self, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None, timeout: float = 30.0):
        self.command = command
        self.args = list(args or [])
        self.env = dict(env or {})
        self.timeout = timeout
        self._calls: List[McpCall] = []
        self._responses: List[McpResponse] = []
        self._client = None
        self._loop = None
        self._tools: Dict[str, Any] = {}

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from mcp import ClientSession, StdioServerParameters  # type: ignore
            from mcp.client.stdio import stdio_client  # type: ignore
        except Exception as error:  # pragma: no cover - optional dependency
            raise TransportError(
                "the 'mcp' package is required for McpClientTransport "
                "(pip install mcp): %s" % error) from None
        self._sdk = (ClientSession, StdioServerParameters, stdio_client)

    def available_tools(self) -> Dict[str, Any]:
        self._ensure_client()
        return dict(self._tools)

    def call(self, tool: str, arguments: Dict[str, Any], read_only: bool = True) -> Any:
        """Run one call in its own session.

        A new session per call is slower than a persistent one but keeps the transport free of a
        background event loop, which matters because a control-plane round must not be able to
        strand a connection.
        """
        import anyio

        self._ensure_client()
        ClientSession, StdioServerParameters, stdio_client = self._sdk
        index = len(self._calls)
        self._calls.append(McpCall(index=index, tool=tool, arguments=dict(arguments),
                                   read_only=read_only))
        parameters = StdioServerParameters(command=self.command, args=self.args,
                                           env=self.env or None)
        captured: Dict[str, Any] = {}

        async def run() -> None:
            with anyio.fail_after(self.timeout):
                async with stdio_client(parameters) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments)
                        captured["result"] = _normalise_tool_result(result)

        try:
            anyio.run(run)
        except Exception as error:
            self._responses.append(McpResponse(index=index, tool=tool, ok=False, error=str(error)))
            raise TransportError("tool %s failed: %s" % (tool, error)) from None
        payload = captured.get("result")
        self._responses.append(McpResponse(index=index, tool=tool, ok=True, payload=payload))
        return payload

    def calls(self) -> List[McpCall]:
        return list(self._calls)

    def responses(self) -> List[McpResponse]:
        return list(self._responses)


def _normalise_tool_result(result: Any) -> Any:
    """Flatten an MCP tool result into JSON-friendly data.

    ``CallToolResult`` carries a list of content blocks; text blocks are parsed as JSON when they
    look like JSON so a server that answers with a JSON string behaves like one that answers with
    structured content.
    """
    blocks = getattr(result, "content", None)
    if blocks is None:
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return result
    texts: List[str] = []
    others: List[Any] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text is not None:
            texts.append(text)
            continue
        data = getattr(block, "data", None)
        if data is not None:
            others.append({"type": getattr(block, "type", "binary"), "bytes": len(str(data))})
            continue
        if hasattr(block, "model_dump"):
            others.append(block.model_dump())
        else:
            others.append(str(block))
    parsed: List[Any] = []
    for text in texts:
        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                parsed.append(json.loads(stripped))
                continue
            except json.JSONDecodeError:
                pass
        parsed.append(text)
    if len(parsed) == 1 and not others:
        return parsed[0]
    if parsed and not others:
        return parsed
    return {"text": parsed, "other": others}


class CallableTransport(McpTransport):
    """Adapter for a host that already has an MCP client in hand: pass ``call(tool, args)``."""

    name = "callable"

    def __init__(self, call: Callable[[str, Dict[str, Any]], Any], name: str = "callable"):
        self._call = call
        self.name = name
        self._calls: List[McpCall] = []
        self._responses: List[McpResponse] = []

    def call(self, tool: str, arguments: Dict[str, Any], read_only: bool = True) -> Any:
        index = len(self._calls)
        self._calls.append(McpCall(index=index, tool=tool, arguments=dict(arguments),
                                   read_only=read_only))
        try:
            payload = self._call(tool, arguments)
        except Exception as error:
            self._responses.append(McpResponse(index=index, tool=tool, ok=False, error=str(error)))
            raise
        self._responses.append(McpResponse(index=index, tool=tool, ok=True, payload=payload))
        return payload

    def calls(self) -> List[McpCall]:
        return list(self._calls)

    def responses(self) -> List[McpResponse]:
        return list(self._responses)

"""The two adapter boundaries, kept apart on purpose.

``render_mcp``  speaks the Render MCP Designer's verified tool surface and is the only module
                that can change the scene.
``laya_ai``     speaks Laya's verified question/answer contract and is the only module that can
                produce a routing decision.

They share no types, no state and no imports in either direction, so a change to one native
interface cannot force a change in the other. ``transport`` is the shared plumbing that lets
either one reach a server without owning the connection.
"""
from .laya_ai import (LayaAdapter, LayaAnswer, LayaMalformed, LayaRunner, LayaUnavailable,
                      build_laya_adapter)
from .render_mcp import ApplyReceipt, RenderMcpAdapter, RenderMcpError, build_op_code, build_patch_code
from .transport import (CallableTransport, JsonFileTransport, McpClientTransport, McpTransport,
                        NotExecuted, RecordingTransport, TransportError)

__all__ = [
    "LayaAdapter", "LayaAnswer", "LayaRunner", "LayaUnavailable", "LayaMalformed",
    "build_laya_adapter",
    "RenderMcpAdapter", "RenderMcpError", "ApplyReceipt", "build_op_code", "build_patch_code",
    "McpTransport", "RecordingTransport", "JsonFileTransport", "McpClientTransport",
    "CallableTransport", "TransportError", "NotExecuted",
]

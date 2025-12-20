"""
Atlas MCP (Model Context Protocol) 模組

這個模組讓 Atlas 能連接外部 MCP servers，
獲得更多工具能力。
"""

from .client import MCPClient, MCPServer, MCPTool
from .bridge import MCPBridge, MCPToolWrapper

__all__ = [
    "MCPClient",
    "MCPServer", 
    "MCPTool",
    "MCPBridge",
    "MCPToolWrapper"
]
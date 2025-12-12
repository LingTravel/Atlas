"""
Atlas 工具註冊中心

自動發現、註冊、管理所有工具。
"""

from typing import Optional
from pathlib import Path
import time

from .base import Tool, ToolResult
from core.events import EventBus


class ToolRegistry:
    """
    工具註冊中心
    
    使用方式：
        registry = ToolRegistry(event_bus)
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        
        # 獲取所有工具定義（給 Gemini）
        definitions = registry.get_definitions()
        
        # 執行工具
        result = registry.execute("read_file", path="some/file.txt")
    """
    
    def __init__(self, event_bus: EventBus = None):
        self._tools: dict[str, Tool] = {}
        self._events = event_bus
    
    def register(self, tool: Tool):
        """
        註冊工具
        
        Args:
            tool: Tool 實例
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered")
        
        self._tools[tool.name] = tool
        
        if self._events:
            self._events.emit("tool.registered", {
                "name": tool.name,
                "description": tool.description
            }, source="ToolRegistry")
    
    def unregister(self, name: str):
        """移除工具"""
        if name in self._tools:
            del self._tools[name]
    
    def get(self, name: str) -> Optional[Tool]:
        """獲取工具"""
        return self._tools.get(name)
    
    def get_all(self) -> list[Tool]:
        """獲取所有工具"""
        return list(self._tools.values())
    
    def get_definitions(self) -> list[dict]:
        """
        獲取所有工具定義（Gemini function calling 格式）
        """
        return [tool.to_definition() for tool in self._tools.values()]
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """
        執行工具
        
        Args:
            name: 工具名稱
            **kwargs: 工具參數
        
        Returns:
            ToolResult: 執行結果
        """
        tool = self._tools.get(name)
        
        if not tool:
            result = ToolResult(
                success=False,
                error=f"Unknown tool: {name}"
            )
            if self._events:
                self._events.emit("tool.failure", {
                    "name": name,
                    "error": result.error
                }, source="ToolRegistry")
            return result
        
        # 發送調用事件
        if self._events:
            self._events.emit("tool.called", {
                "name": name,
                "args": kwargs
            }, source="ToolRegistry")
        
        # 執行並計時
        start = time.time()
        try:
            result = tool.execute(**kwargs)
            result.execution_time = time.time() - start
            
            # 發送結果事件
            if self._events:
                event_type = "tool.success" if result.success else "tool.failure"
                self._events.emit(event_type, {
                    "name": name,
                    "result": result.to_json()
                }, source="ToolRegistry")
            
            return result
            
        except Exception as e:
            result = ToolResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start
            )
            
            if self._events:
                self._events.emit("tool.failure", {
                    "name": name,
                    "error": str(e)
                }, source="ToolRegistry")
            
            return result
    
    def list_tools(self) -> list[str]:
        """列出所有工具名稱"""
        return list(self._tools.keys())
    
    def __contains__(self, name: str) -> bool:
        return name in self._tools
    
    def __len__(self) -> int:
        return len(self._tools)
"""
Atlas 工具基類

所有工具必須繼承這個類別。
工具會自動註冊到 ToolRegistry。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime


@dataclass
class ToolResult:
    """工具執行結果"""
    success: bool
    data: Any = None
    error: str = None
    execution_time: float = 0.0
    metadata: dict = field(default_factory=dict)
    
    def to_json(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time": self.execution_time,
            **self.metadata
        }


class Tool(ABC):
    """
    工具基類
    
    繼承此類別以創建新工具：
    
    class MyTool(Tool):
        @property
        def name(self) -> str:
            return "my_tool"
        
        @property
        def description(self) -> str:
            return "Does something cool"
        
        @property
        def parameters(self) -> dict:
            return {
                "type": "object",
                "properties": {
                    "input": {"type": "string", "description": "The input"}
                },
                "required": ["input"]
            }
        
        def execute(self, input: str) -> ToolResult:
            return ToolResult(success=True, data=f"Processed: {input}")
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名稱（唯一識別符）"""
        ...
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述（給 LLM 看）"""
        ...
    
    @property
    @abstractmethod
    def parameters(self) -> dict:
        """
        參數定義（JSON Schema 格式）
        
        Example:
            {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path"
                    }
                },
                "required": ["path"]
            }
        """
        ...
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        執行工具
        
        Args:
            **kwargs: 參數（與 parameters 定義對應）
        
        Returns:
            ToolResult: 執行結果
        """
        ...
    
    def to_definition(self) -> dict:
        """
        轉換為 Gemini function calling 格式
        
        自動生成，不需要覆寫。
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }
    
    def __repr__(self) -> str:
        return f"<Tool:{self.name}>"
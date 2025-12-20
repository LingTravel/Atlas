"""
Atlas 工具基類

所有工具必須繼承這個類別。

更新：支援同步和異步執行
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime
import asyncio


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
            "metadata": self.metadata
        }


class Tool(ABC):
    """
    工具基類
    
    支援兩種執行模式：
    1. 同步模式：實作 execute() 方法
    2. 異步模式：實作 execute_async() 方法（可選）
    
    如果只實作 execute()，系統會自動包裝成異步。
    
    範例：
    
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
        同步執行工具
        
        Args:
            **kwargs: 參數（與 parameters 定義對應）
        
        Returns:
            ToolResult: 執行結果
        """
        ...
    
    async def execute_async(self, **kwargs) -> ToolResult:
        """
        異步執行工具
        
        預設行為：在線程池中執行同步的 execute()
        
        如果你的工具本身是異步的（如網路請求），
        可以覆寫這個方法以獲得更好的性能。
        
        Args:
            **kwargs: 參數
        
        Returns:
            ToolResult: 執行結果
        """
        # 使用 asyncio.to_thread 在背景線程執行同步代碼
        # 這樣不會阻塞主事件循環
        return await asyncio.to_thread(self.execute, **kwargs)
    
    @property
    def is_async(self) -> bool:
        """
        檢查工具是否有自定義的異步實作
        
        如果子類覆寫了 execute_async，這會返回 True
        """
        # 檢查 execute_async 是否被覆寫
        return type(self).execute_async is not Tool.execute_async
    
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
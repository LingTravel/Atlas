"""
MCP Bridge - 將 MCP 工具橋接為 Atlas 工具

這是「轉接器」，讓 Atlas 的大腦不需要知道
工具是本地的還是遠端的。
"""

from typing import Optional
from tools.base import Tool, ToolResult
from .client import MCPClient, MCPTool


class MCPToolWrapper(Tool):
    """
    將 MCP 工具包裝為 Atlas Tool
    
    這讓 MCP 工具可以像本地工具一樣使用
    """
    
    def __init__(self, mcp_tool: MCPTool, client: MCPClient):
        self._tool = mcp_tool
        self._client = client
    
    @property
    def name(self) -> str:
        return self._tool.full_name
    
    @property
    def description(self) -> str:
        return self._tool.description
    
    @property
    def parameters(self) -> dict:
        """
        轉換 MCP input_schema 為 Gemini 兼容格式
        """
        schema = self._tool.input_schema
        
        # 如果沒有 schema，返回空物件
        if not schema:
            return {
                "type": "object",
                "properties": {}
            }
        
        # 確保有基本結構
        result = {
            "type": schema.get("type", "object"),
            "properties": schema.get("properties", {}),
        }
        
        # 只在有 required 時才加入
        if "required" in schema and schema["required"]:
            result["required"] = schema["required"]
        
        # 移除 Gemini 不支援的欄位
        for prop_name, prop_value in result.get("properties", {}).items():
            if isinstance(prop_value, dict):
                # 移除可能有問題的欄位
                prop_value.pop("$ref", None)
                prop_value.pop("allOf", None)
                prop_value.pop("anyOf", None)
                prop_value.pop("oneOf", None)
        
        return result
    
    def execute(self, **kwargs) -> ToolResult:
        """
        同步執行（不應該被直接調用）
        
        MCP 工具本質上是異步的，
        這個方法只是為了滿足介面要求
        """
        import asyncio
        
        # 如果在異步環境中，使用 execute_async
        try:
            loop = asyncio.get_running_loop()
            # 我們在異步環境中，不能直接調用
            raise RuntimeError(
                "MCPToolWrapper.execute() called in async context. "
                "Use execute_async() instead."
            )
        except RuntimeError:
            # 沒有運行中的 loop，創建一個新的
            return asyncio.run(self.execute_async(**kwargs))
    
    async def execute_async(self, **kwargs) -> ToolResult:
        """
        異步執行 MCP 工具
        
        這是主要的執行方法
        """
        try:
            result = await self._client.call_tool(
                self._tool.full_name,
                kwargs
            )
            
            # 檢查錯誤
            if "error" in result:
                return ToolResult(
                    success=False,
                    error=result["error"]
                )
            
            # 處理 MCP 回應格式
            content = result.get("content", [])
            
            # 檢查是否有圖片
            has_image = any(
                c.get("type") == "image" 
                for c in content
            )
            
            # 提取文字和圖片
            text_parts = []
            image_data = None
            
            for item in content:
                if item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif item.get("type") == "image":
                    image_data = item.get("data")
            
            return ToolResult(
                success=True,
                data={
                    "text": "\n".join(text_parts),
                    "screenshot": image_data,
                },
                metadata={"has_image": has_image}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )


class MCPBridge:
    """
    MCP 與 ToolRegistry 的橋接器
    
    使用方式：
        client = MCPClient()
        await client.start()
        
        bridge = MCPBridge(client)
        wrappers = bridge.create_wrappers()
        
        for wrapper in wrappers:
            registry.register(wrapper)
    """
    
    def __init__(self, client: MCPClient):
        self.client = client
        self.wrappers: dict[str, MCPToolWrapper] = {}
    
    def create_wrappers(self) -> list[Tool]:
        """
        為所有 MCP 工具創建 wrapper
        
        Returns:
            可以註冊到 ToolRegistry 的工具列表
        """
        wrappers = []
        
        for tool in self.client.list_tools():
            wrapper = MCPToolWrapper(tool, self.client)
            self.wrappers[tool.full_name] = wrapper
            wrappers.append(wrapper)
        
        return wrappers
    
    def get_wrapper(self, name: str) -> Optional[MCPToolWrapper]:
        """獲取特定工具的 wrapper"""
        return self.wrappers.get(name)
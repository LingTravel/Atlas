"""
MCP Client - 連接外部 MCP servers

這是 Atlas 與外部服務溝通的「手機」。

工作流程：
1. 讀取配置（哪些 servers 要連接）
2. 啟動 servers（作為子進程）
3. 透過 stdin/stdout 溝通
4. 呼叫遠端工具
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path


@dataclass
class MCPServer:
    """
    MCP Server 配置
    
    描述一個外部服務的連接方式
    """
    name: str                    # 服務名稱（如 "browser", "github"）
    command: str                 # 啟動命令（如 "npx", "python"）
    args: list[str] = field(default_factory=list)  # 命令參數
    env: dict = field(default_factory=dict)        # 環境變數
    auto_start: bool = True      # 是否自動啟動


@dataclass  
class MCPTool:
    """
    來自 MCP server 的工具
    
    這代表一個可以調用的遠端工具
    """
    server_name: str             # 來自哪個 server
    name: str                    # 工具名稱
    description: str             # 工具描述
    input_schema: dict           # 參數格式
    
    @property
    def full_name(self) -> str:
        """
        完整名稱（避免不同 server 的工具重名）
        
        例如："browser.navigate", "github.create_issue"
        """
        return f"{self.server_name}.{self.name}"


class MCPConnection:
    """
    單一 MCP Server 的連接
    
    管理與一個 server 的所有通訊
    """
    
    def __init__(self, server: MCPServer):
        self.server = server
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: dict[str, MCPTool] = {}
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._read_task: Optional[asyncio.Task] = None
    
    async def start(self) -> bool:
        """啟動 server 並完成初始化"""
        try:
            # 準備環境變數
            env = os.environ.copy()
            for key, value in self.server.env.items():
                if value.startswith("${") and value.endswith("}"):
                    var_name = value[2:-1]
                    env[key] = os.environ.get(var_name, "")
                else:
                    env[key] = value
            
            # Windows 兼容性處理
            import sys
            command = self.server.command
            args = self.server.args
            
            if sys.platform == "win32":
                if command in ["npx", "npm", "node"]:
                    args = ["/c", command] + list(args)
                    command = "cmd"
            
            # 啟動子進程
            self.process = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )
            
            print(f"[MCP] Started: {self.server.name}")
            
            # 啟動讀取任務
            self._read_task = asyncio.create_task(self._read_loop())

            # === 新增：讀取 stderr ===
            async def read_stderr():
                try:
                    while True:
                        line = await self.process.stderr.readline()
                        if not line:
                            break
                        print(f"[MCP STDERR] {line.decode().strip()}")
                except:
                    pass

            asyncio.create_task(read_stderr())
            
            # 給進程一點啟動時間
            await asyncio.sleep(0.3)
            
            # MCP 初始化握手（帶超時保護）
            try:
                await asyncio.wait_for(self._initialize(), timeout=10.0)
            except asyncio.TimeoutError:
                print(f"[MCP] Initialize timeout: {self.server.name}")
                return False
            
            # 獲取工具列表（帶超時保護）
            try:
                await asyncio.wait_for(self._list_tools(), timeout=10.0)
            except asyncio.TimeoutError:
                print(f"[MCP] List tools timeout: {self.server.name}")
                return False
            
            return True
            
        except Exception as e:
            print(f"[MCP] Failed to start {self.server.name}: {e}")
            return False
    
    async def stop(self):
        """關閉連接"""
        # 取消讀取任務
        if self._read_task:
            self._read_task.cancel()
            try:
                await asyncio.wait_for(self._read_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        
        # 終止進程
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                # 強制殺死
                self.process.kill()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=1.0)
                except:
                    pass
            
            print(f"[MCP] Stopped: {self.server.name}")
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        調用遠端工具
        
        Args:
            tool_name: 工具名稱（不含 server 前綴）
            arguments: 工具參數
        
        Returns:
            工具執行結果
        """
        response = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        return response.get("result", {})
    
    async def _initialize(self):
        """MCP 初始化握手"""
        # 發送 initialize 請求
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "atlas",
                "version": "0.1.0"
            }
        })
        
        # 發送 initialized 通知
        await self._send_notification("notifications/initialized", {})
    
    async def _list_tools(self):
        """獲取工具列表"""
        response = await self._send_request("tools/list", {})
        
        for tool_data in response.get("result", {}).get("tools", []):
            tool = MCPTool(
                server_name=self.server.name,
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {})
            )
            self.tools[tool.name] = tool
            print(f"[MCP]   Tool: {tool.full_name}")
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """發送 JSON-RPC 請求並等待回應"""
        self._request_id += 1
        request_id = self._request_id
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        
        data = json.dumps(request) + "\n"
        
        # === 調試 ===
        print(f"[MCP DEBUG] Sending: {method}", flush=True)
        
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()
        
        print(f"[MCP DEBUG] Waiting for response...", flush=True)
        
        try:
            response = await asyncio.wait_for(future, timeout=30.0)
            print(f"[MCP DEBUG] Got response", flush=True)
            return response
        except asyncio.TimeoutError:
            print(f"[MCP DEBUG] Timeout waiting for {method}", flush=True)
            del self._pending[request_id]
            return {"error": "Request timeout"}

    async def _read_loop(self):
        """持續讀取 server 的回應"""
        print("[MCP DEBUG] Read loop started", flush=True)
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    print("[MCP DEBUG] EOF received", flush=True)
                    break
                
                print(f"[MCP DEBUG] Received line: {line[:100]}", flush=True)
                
                try:
                    message = json.loads(line.decode())
                    
                    if "id" in message:
                        request_id = message["id"]
                        if request_id in self._pending:
                            self._pending[request_id].set_result(message)
                            del self._pending[request_id]
                    
                except json.JSONDecodeError as e:
                    print(f"[MCP DEBUG] JSON error: {e}", flush=True)
                    
        except asyncio.CancelledError:
            print("[MCP DEBUG] Read loop cancelled", flush=True)
        except Exception as e:
            print(f"[MCP DEBUG] Read loop error: {e}", flush=True)
    
    async def _send_notification(self, method: str, params: dict):
        """發送通知（不需要回應）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        
        data = json.dumps(notification) + "\n"
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

class MCPClient:
    """
    MCP 客戶端
    
    管理多個 MCP server 連接
    
    使用方式：
        client = MCPClient()
        await client.start()
        
        # 列出所有工具
        tools = client.list_tools()
        
        # 調用工具
        result = await client.call_tool("browser.navigate", {"url": "..."})
        
        await client.stop()
    """
    
    def __init__(self, config_path: Path = None):
        self.config_path = config_path or Path("config/mcp_servers.yaml")
        self.servers: dict[str, MCPServer] = {}
        self.connections: dict[str, MCPConnection] = {}
    
    async def start(self):
        """
        啟動所有配置的 servers
        
        1. 讀取配置
        2. 啟動每個 server
        3. 獲取工具列表
        """
        self._load_config()
        
        for name, server in self.servers.items():
            if server.auto_start:
                connection = MCPConnection(server)
                success = await connection.start()
                
                if success:
                    self.connections[name] = connection
    
    async def stop(self):
        """關閉所有連接"""
        for name, connection in self.connections.items():
            try:
                await asyncio.wait_for(connection.stop(), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"[MCP] Force stopped: {name}")
            except Exception as e:
                print(f"[MCP] Error stopping {name}: {e}")
        
        self.connections.clear()
    
    async def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        調用 MCP 工具
        
        Args:
            tool_name: 工具名稱
                - "server.tool" 格式：直接指定
                - "tool" 格式：自動尋找
            arguments: 工具參數
        
        Returns:
            工具執行結果
        """
        # 解析工具名稱
        if "." in tool_name:
            server_name, short_name = tool_name.split(".", 1)
        else:
            # 尋找第一個有這個工具的 server
            server_name, short_name = self._find_tool(tool_name)
            if not server_name:
                return {"error": f"Tool not found: {tool_name}"}
        
        # 獲取連接
        connection = self.connections.get(server_name)
        if not connection:
            return {"error": f"Server not connected: {server_name}"}
        
        # 調用工具
        return await connection.call_tool(short_name, arguments)
    
    def list_tools(self) -> list[MCPTool]:
        """列出所有可用工具"""
        tools = []
        for connection in self.connections.values():
            tools.extend(connection.tools.values())
        return tools
    
    def get_tool(self, name: str) -> Optional[MCPTool]:
        """獲取工具資訊"""
        if "." in name:
            server_name, short_name = name.split(".", 1)
            connection = self.connections.get(server_name)
            if connection:
                return connection.tools.get(short_name)
        else:
            for connection in self.connections.values():
                if name in connection.tools:
                    return connection.tools[name]
        return None
    
    def _find_tool(self, name: str) -> tuple[Optional[str], str]:
        """尋找工具所在的 server"""
        for server_name, connection in self.connections.items():
            if name in connection.tools:
                return server_name, name
        return None, name
    
    def _load_config(self):
        """載入配置"""
        if not self.config_path.exists():
            print(f"[MCP] Config not found: {self.config_path}")
            return
        
        try:
            import yaml
            
            # 使用 UTF-8 編碼讀取（修復 Windows cp950 問題）
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or 'servers' not in config:
                print("[MCP] No servers configured")
                return
            
            for server_data in config.get("servers", []):
                server = MCPServer(
                    name=server_data["name"],
                    command=server_data["command"],
                    args=server_data.get("args", []),
                    env=server_data.get("env", {}),
                    auto_start=server_data.get("auto_start", True)
                )
                self.servers[server.name] = server
                print(f"[MCP] Loaded config: {server.name}")
                
        except ImportError:
            print("[MCP] Warning: PyYAML not installed. Run: pip install pyyaml")
        except Exception as e:
            print(f"[MCP] Failed to load config: {e}")
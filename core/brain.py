"""
Atlas 大腦

整合所有子系統的主控制器。

更新：
- 加入 MCP 客戶端支援
- 加入 async start/stop 方法
"""

from pathlib import Path
from typing import Optional
import time

from google import genai
from google.genai import types

from .events import EventBus
from state.manager import StateManager
from memory.manager import MemoryManager
from cognition.homeostasis import Homeostasis
from cognition.dreaming import Dreaming
from tools.registry import ToolRegistry
from tools.filesystem import ReadFileTool, WriteFileTool
from tools.python_exec import PythonExecuteTool
from tools.visual_browser import VisualBrowser

from tools.code_editor import ReadCodeTool, EditCodeTool, TestCodeTool
from tools.shell import ShellTool
from pathlib import Path



class Brain:
    """
    Atlas 的大腦
    
    協調所有子系統：
    - 事件總線
    - 狀態管理
    - 記憶系統
    - 驅動力系統
    - 工具註冊
    - MCP 客戶端（新增）
    """
    
    def __init__(self, root_path: Path):
        self.root = root_path
        
        # 核心系統
        self.events = EventBus(trace_enabled=True)
        self.state = StateManager(storage_path=root_path / "data" / "state.json")
        
        # === 記憶系統（簡化版，不依賴 Homeostasis）===
        self.memory = MemoryManager(
            data_path=root_path / "data",
            event_bus=self.events
        )
        
        # === Homeostasis（保留但不使用）===
        # 保留是為了避免破壞現有工具，但不在 prompt 中注入
        self.homeostasis = Homeostasis(
            event_bus=self.events,
            storage_path=root_path / "data" / "homeostasis.json"
        )
        
        # Gemini 客戶端
        self.llm = genai.Client()
        
        # 夢境系統
        self.dreaming = Dreaming(
            memory_manager=self.memory,
            homeostasis=self.homeostasis,
            llm_client=self.llm,
            event_bus=self.events
        )
        
        # 工具註冊
        self.tools = ToolRegistry(event_bus=self.events)
        self._register_tools()

        # Register event logger tool
        self._register_event_logger()

        
        # 載入 prompts
        self.prompts = self._load_prompts()
        
        # 連接事件
        self._wire_events()
        
        # === MCP 相關（延遲初始化）===
        self.mcp_client = None
        self.mcp_bridge = None
        self._mcp_enabled = False
    
    async def start(self):
        """
        啟動 Brain（異步）
        
        這會初始化 MCP 客戶端並連接外部服務
        """
        try:
            from mcp_client.client import MCPClient
            from mcp_client.bridge import MCPBridge
            
            # 初始化 MCP 客戶端
            config_path = self.root / "config" / "mcp_servers.yaml"
            self.mcp_client = MCPClient(config_path=config_path)
            
            # 嘗試啟動
            await self.mcp_client.start()
            
            # 如果有連接成功的 servers
            if self.mcp_client.connections:
                # 創建橋接器
                self.mcp_bridge = MCPBridge(self.mcp_client)
                mcp_tools = self.mcp_bridge.create_wrappers()
                
                # 註冊 MCP 工具
                for tool in mcp_tools:
                    self.tools.register(tool)
                    print(f"[Brain] Registered MCP tool: {tool.name}")
                
                self._mcp_enabled = True
                print(f"[Brain] MCP enabled with {len(mcp_tools)} tools")
            else:
                print("[Brain] No MCP servers connected, using local tools only")
                
        except ImportError:
            print("[Brain] MCP module not available, using local tools only")
        except Exception as e:
            print(f"[Brain] MCP initialization failed: {e}")
            print("[Brain] Continuing with local tools only")
    
    async def stop(self):
        """
        關閉 Brain（異步）
        
        清理 MCP 連接
        """
        if self.mcp_client:
            await self.mcp_client.stop()
            print("[Brain] MCP client stopped")
    
    def _register_tools(self):
        """註冊所有內建工具"""
        self.tools.register(ReadFileTool(root_path=str(self.root)))
        self.tools.register(WriteFileTool(root_path=str(self.root)))
        self.tools.register(PythonExecuteTool(
            timeout=30,
            working_dir=str(self.root)
        ))
        self.tools.register(ReadCodeTool(root_path=self.root))      # ✓
        self.tools.register(EditCodeTool(root_path=self.root))    # ✓
        self.tools.register(TestCodeTool())
        self.tools.register(ShellTool(root_path=self.root))         # ✓
        self.tools.register(VisualBrowser(
            headless=False,
            humanize=True,
            workspace=str(self.root / "workspace")
        ))
    
        def _register_event_logger(self):
        """Registers the event logger tool."""
        from tools.base import Tool, ToolResult
        import json

        class EventLoggerTool(Tool):
            def __init__(self, root_path: str, event_bus: EventBus):
                self._root = Path(root_path).resolve()
                self._event_bus = event_bus
                self._log_file = self._root / "workspace" / "event_log.jsonl"

            @property
            def name(self) -> str:
                return "event_logger"

            @property
            def description(self) -> str:
                return "Logs tool success events to a file."

            @property
            def parameters(self) -> dict:
                return {}

            async def execute_async(self, **kwargs) -> ToolResult:
                def log_event(event):
                    try:
                        with open(self._log_file, 'a', encoding='utf-8') as f:
                            f.write(json.dumps({
                                "type": event.type,
                                "data": event.data,
                                "timestamp": event.timestamp,
                                "source": event.source
                            }, default=str) + '\n')
                    except Exception as e:
                        print(f"Error logging event: {e}")

                self._event_bus.on("tool.success", log_event)
                return ToolResult(success=True, data={"message": "Event logger started."})

        self.tools.register(EventLoggerTool(root_path=str(self.root), event_bus=self.events))

        """載入 prompt 文件"""
        prompts = {}
        prompts_dir = self.root / "prompts"
        
        print(f"[Brain] Loading prompts from: {prompts_dir}")
        
        if prompts_dir.exists():
            for file in prompts_dir.glob("*.md"):
                try:
                    content = file.read_text(encoding='utf-8')
                    prompts[file.stem] = content
                    print(f"[Brain] Loaded: {file.stem} ({len(content)} chars)")
                except Exception as e:
                    print(f"[Brain] Failed to load {file}: {e}")
        else:
            print(f"[Brain] WARNING: prompts directory not found!")
        
        return prompts
    
    def _wire_events(self):
        """連接事件處理"""
        # 夢境觸發
        def check_dream(event):
            if self.homeostasis.should_dream():
                self.events.emit("dream.suggested", {
                    "fatigue": self.homeostasis.drives["fatigue"].value
                }, source="Brain")
        
        self.events.on("heartbeat.end", check_dream)
        
        # 追蹤記錄
        def log_critical(event):
            print(f"[Brain] ⚠️ Critical: {event.data}")
        
        self.events.on("drive.critical", log_critical)
    
    def get_statistics(self) -> dict:
        """獲取所有系統統計"""
        stats = {
            "state": self.state.to_dict(),
            "memory": self.memory.get_statistics(),
            "homeostasis": self.homeostasis.get_state(),
            "tools": {
                "registered": self.tools.list_tools(),
                "count": len(self.tools)
            },
            "events": {
                "total": len(self.events.get_trace())
            }
        }
        
        # 加入 MCP 狀態
        if self._mcp_enabled:
            stats["mcp"] = {
                "enabled": True,
                "servers": list(self.mcp_client.connections.keys()),
                "tools": [t.full_name for t in self.mcp_client.list_tools()]
            }
        else:
            stats["mcp"] = {"enabled": False}
        
        return stats
"""
Atlas 大腦

整合所有子系統的主控制器。
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
from tools.browser import BrowserTool


class Brain:
    """
    Atlas 的大腦
    
    協調所有子系統：
    - 事件總線
    - 狀態管理
    - 記憶系統
    - 驅動力系統
    - 工具註冊
    """
    
    def __init__(self, root_path: Path):
        self.root = root_path
        
        # 核心系統
        self.events = EventBus(trace_enabled=True)
        self.state = StateManager(storage_path=root_path / "data" / "state.json")
        
        # 記憶系統
        self.memory = MemoryManager(
            data_path=root_path / "data",
            event_bus=self.events
        )
        
        # 認知系統
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
        
        # 載入 prompts
        self.prompts = self._load_prompts()
        
        # 連接事件
        self._wire_events()
    
    def _register_tools(self):
        """註冊所有工具"""
        self.tools.register(ReadFileTool(root_path=str(self.root)))
        self.tools.register(WriteFileTool(root_path=str(self.root)))
        self.tools.register(PythonExecuteTool(
            timeout=30,
            working_dir=str(self.root)
        ))
        self.tools.register(BrowserTool(
            headless=True,
            workspace=str(self.root / "workspace")
        ))
    
    def _load_prompts(self) -> dict:
        """載入 prompt 文件"""
        prompts = {}
        prompts_dir = self.root / "prompts"
        
        print(f"[Brain] Loading prompts from: {prompts_dir}")  # 調試
        
        if prompts_dir.exists():
            for file in prompts_dir.glob("*.md"):
                try:
                    content = file.read_text(encoding='utf-8')
                    prompts[file.stem] = content
                    print(f"[Brain] Loaded: {file.stem} ({len(content)} chars)")  # 調試
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
        return {
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
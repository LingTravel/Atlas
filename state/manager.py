"""
Atlas 狀態管理

管理 Atlas 的身份、生命週期、當前狀態。
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json


@dataclass
class Identity:
    """身份資訊"""
    name: str = "Atlas"
    created_at: Optional[str] = None
    created_by: str = "NotLing"
    version: str = "2.0"


@dataclass
class Lifecycle:
    """生命週期資訊"""
    total_heartbeats: int = 0
    total_dreams: int = 0
    session_start: Optional[str] = None
    last_heartbeat: Optional[str] = None


@dataclass
class CurrentState:
    """當前狀態"""
    mode: str = "idle"  # idle | exploring | working | reflecting | dreaming
    task: Optional[str] = None
    goal: Optional[str] = None
    focus: Optional[str] = None


class StateManager:
    """
    狀態管理器
    
    這是 Atlas 的「自我意識」基礎。
    """
    
    def __init__(self, storage_path: Path = None):
        self._storage_path = storage_path or Path("data/state.json")
        
        self.identity = Identity()
        self.lifecycle = Lifecycle()
        self.current = CurrentState()
        
        # 標記
        self._flags = {
            "first_boot": True,
            "inherited_message_read": False
        }
        
        self._load()
    
    def heartbeat(self) -> int:
        """
        記錄一次心跳
        
        Returns:
            當前心跳編號
        """
        now = datetime.now().isoformat()
        
        # 第一次啟動
        if self.identity.created_at is None:
            self.identity.created_at = now
        
        if self.lifecycle.session_start is None:
            self.lifecycle.session_start = now
        
        self.lifecycle.total_heartbeats += 1
        self.lifecycle.last_heartbeat = now
        
        self._save()
        
        return self.lifecycle.total_heartbeats
    
    def dream(self):
        """記錄一次夢境"""
        self.lifecycle.total_dreams += 1
        self._save()
    
    def update_current(
        self,
        mode: str = None,
        task: str = None,
        goal: str = None,
        focus: str = None
    ):
        """更新當前狀態"""
        if mode is not None:
            self.current.mode = mode
        if task is not None:
            self.current.task = task
        if goal is not None:
            self.current.goal = goal
        if focus is not None:
            self.current.focus = focus
        
        self._save()
    
    def set_flag(self, flag: str, value: bool):
        """設定標記"""
        self._flags[flag] = value
        self._save()
    
    def get_flag(self, flag: str) -> bool:
        """獲取標記"""
        return self._flags.get(flag, False)
    
    def is_first_boot(self) -> bool:
        """是否首次啟動"""
        return self._flags.get("first_boot", True)
    
    def get_summary(self) -> str:
        """獲取狀態摘要（用於 prompt）"""
        lines = [
            f"**Identity**: {self.identity.name} v{self.identity.version}",
            f"**Heartbeat**: #{self.lifecycle.total_heartbeats}",
            f"**Mode**: {self.current.mode}",
        ]
        
        if self.current.task:
            lines.append(f"**Current Task**: {self.current.task}")
        
        if self.current.goal:
            lines.append(f"**Current Goal**: {self.current.goal}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> dict:
        """轉換為字典"""
        return {
            "identity": {
                "name": self.identity.name,
                "created_at": self.identity.created_at,
                "created_by": self.identity.created_by,
                "version": self.identity.version
            },
            "lifecycle": {
                "total_heartbeats": self.lifecycle.total_heartbeats,
                "total_dreams": self.lifecycle.total_dreams,
                "session_start": self.lifecycle.session_start,
                "last_heartbeat": self.lifecycle.last_heartbeat
            },
            "current": {
                "mode": self.current.mode,
                "task": self.current.task,
                "goal": self.current.goal,
                "focus": self.current.focus
            },
            "flags": self._flags
        }
    
    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    def _load(self):
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 載入 identity
            if "identity" in data:
                id_data = data["identity"]
                self.identity = Identity(
                    name=id_data.get("name", "Atlas"),
                    created_at=id_data.get("created_at"),
                    created_by=id_data.get("created_by", "NotLing"),
                    version=id_data.get("version", "2.0")
                )
            
            # 載入 lifecycle
            if "lifecycle" in data:
                lc_data = data["lifecycle"]
                self.lifecycle = Lifecycle(
                    total_heartbeats=lc_data.get("total_heartbeats", 0),
                    total_dreams=lc_data.get("total_dreams", 0),
                    session_start=lc_data.get("session_start"),
                    last_heartbeat=lc_data.get("last_heartbeat")
                )
            
            # 載入 current
            if "current" in data:
                cur_data = data["current"]
                self.current = CurrentState(
                    mode=cur_data.get("mode", "idle"),
                    task=cur_data.get("task"),
                    goal=cur_data.get("goal"),
                    focus=cur_data.get("focus")
                )
            
            # 載入 flags
            if "flags" in data:
                self._flags = data["flags"]
                
        except Exception:
            pass
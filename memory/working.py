"""
Atlas 工作記憶

短期記憶，只保留最近 N 個心跳的記錄。
類似人類的工作記憶容量限制（7±2）。
"""

from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from core.events import EventBus


class WorkingMemory:
    """
    工作記憶 (FIFO)
    
    容量有限，舊的自動移除。
    這是 Atlas 的「當下意識」。
    
    新功能：追蹤已讀文件，防止重複閱讀。
    """
    
    def __init__(
        self,
        capacity: int = 5,
        storage_path: Path = None,
        event_bus: EventBus = None
    ):
        self._capacity = capacity
        self._storage_path = storage_path or Path("data/working_memory.json")
        self._events = event_bus
        self._memory: deque = deque(maxlen=capacity)
        
        # 已讀文件追蹤：{path: read_count}
        self._files_read: dict[str, int] = {}
        
        self._load()
    
    def add(
        self,
        heartbeat: int,
        thoughts: str = "",
        actions: list = None,
        summary: str = ""
    ):
        """
        添加一個心跳的記錄
        
        Args:
            heartbeat: 心跳編號
            thoughts: Atlas 的想法
            actions: 執行的動作列表
            summary: 心跳摘要
        """
        entry = {
            "heartbeat": heartbeat,
            "timestamp": datetime.now().isoformat(),
            "thoughts": thoughts,
            "actions": actions or [],
            "summary": summary
        }
        
        self._memory.append(entry)
        self._save()
        
        if self._events:
            self._events.emit("memory.working.add", entry, source="WorkingMemory")
    
    def get_recent(self, n: int = None) -> list[dict]:
        """
        獲取最近 n 個心跳的記錄
        
        Args:
            n: 數量（None = 全部）
        """
        if n is None:
            return list(self._memory)
        return list(self._memory)[-n:]
    
    def get_last(self) -> Optional[dict]:
        """獲取最後一個記錄"""
        if self._memory:
            return self._memory[-1]
        return None
    
    # ==========================================
    # 已讀文件追蹤功能
    # ==========================================
    
    def mark_read(self, path: str):
        """
        標記文件已讀
        
        Args:
            path: 文件路徑
        """
        self._files_read[path] = self._files_read.get(path, 0) + 1
        self._save()
        
        if self._events:
            self._events.emit("memory.file.read", {
                "path": path,
                "count": self._files_read[path]
            }, source="WorkingMemory")
    
    def get_read_count(self, path: str) -> int:
        """
        獲取文件讀取次數
        
        Args:
            path: 文件路徑
        
        Returns:
            讀取次數（0 = 從未讀過）
        """
        return self._files_read.get(path, 0)
    
    def has_read(self, path: str) -> bool:
        """檢查是否已讀過"""
        return path in self._files_read
    
    def get_files_read(self) -> dict[str, int]:
        """獲取所有已讀文件及其讀取次數"""
        return self._files_read.copy()
    
    def get_overread_files(self, threshold: int = 2) -> list[str]:
        """
        獲取讀取過多的文件
        
        Args:
            threshold: 閾值（超過此值視為過度閱讀）
        """
        return [
            path for path, count in self._files_read.items()
            if count >= threshold
        ]
    
    # ==========================================
    # 上下文生成
    # ==========================================
    
    def get_context_string(self, n: int = 3) -> str:
        """
        生成用於 prompt 的上下文字串
        
        Args:
            n: 包含最近幾個心跳
        """
        recent = self.get_recent(n)
        if not recent:
            return "No recent memories."
        
        lines = []
        for entry in recent:
            hb = entry.get("heartbeat", "?")
            thoughts = entry.get("thoughts", "")[:100]
            action_count = len(entry.get("actions", []))
            
            lines.append(f"- [HB{hb}] {thoughts}... ({action_count} actions)")
        
        return "\n".join(lines)
    
    def get_files_read_string(self) -> str:
        """生成已讀文件的 prompt 字串"""
        if not self._files_read:
            return ""
        
        lines = ["## Files I've Already Read"]
        
        # 按讀取次數排序（多的在前）
        sorted_files = sorted(
            self._files_read.items(),
            key=lambda x: -x[1]
        )
        
        for path, count in sorted_files[:15]:  # 最多顯示 15 個
            if count >= 3:
                lines.append(f"- 🚫 {path} (read {count}x - DO NOT read again!)")
            elif count >= 2:
                lines.append(f"- ⚠️ {path} (read {count}x - avoid re-reading)")
            else:
                lines.append(f"- ✓ {path}")
        
        lines.append("")
        lines.append("**Rule: Files marked 🚫 or ⚠️ should NOT be read again.**")
        
        return "\n".join(lines)
    
    # ==========================================
    # 清理與統計
    # ==========================================
    
    def clear(self):
        """清空工作記憶（保留已讀追蹤）"""
        self._memory.clear()
        self._save()
    
    def clear_all(self):
        """完全清空（包括已讀追蹤）"""
        self._memory.clear()
        self._files_read.clear()
        self._save()
    
    def get_statistics(self) -> dict:
        return {
            "capacity": self._capacity,
            "current_size": len(self._memory),
            "oldest_heartbeat": self._memory[0]["heartbeat"] if self._memory else None,
            "newest_heartbeat": self._memory[-1]["heartbeat"] if self._memory else None,
            "files_read_count": len(self._files_read),
            "total_reads": sum(self._files_read.values()),
            "overread_files": len(self.get_overread_files())
        }
    
    # ==========================================
    # 持久化
    # ==========================================
    
    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "memory": list(self._memory),
            "files_read": self._files_read
        }
        
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 兼容舊格式（純 list）
            if isinstance(data, list):
                self._memory = deque(data, maxlen=self._capacity)
                self._files_read = {}
            else:
                # 新格式
                self._memory = deque(
                    data.get("memory", []),
                    maxlen=self._capacity
                )
                self._files_read = data.get("files_read", {})
                
        except Exception:
            pass  # 載入失敗就用預設值
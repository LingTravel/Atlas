from collections import deque
import json
from pathlib import Path

class WorkingMemory:
    """
    短期記憶（工作記憶）
    
    只保留最近 N 個心跳的原始記錄。
    這是 FIFO 隊列，舊的會自動被移除。
    
    人類的工作記憶只能同時持有 7±2 個項目。
    我們讓 Atlas 保留 5 個心跳。
    """
    
    def __init__(self, capacity=5, storage_path="data/working_memory.json"):
        self.capacity = capacity
        self.storage_path = Path(storage_path)
        self.memory = deque(maxlen=capacity)
        
        # 載入已存在的記憶
        self._load()
    
    def add(self, heartbeat_number: int, log: dict):
        """
        添加一個心跳的記錄
        
        Args:
            heartbeat_number: 心跳編號
            log: 包含 thoughts, actions, results 的字典
        """
        entry = {
            "heartbeat": heartbeat_number,
            "timestamp": log.get("timestamp"),
            "thoughts": log.get("thoughts", ""),
            "actions": log.get("actions", []),
            "results": log.get("results", [])
        }
        
        self.memory.append(entry)
        self._save()
    
    def get_recent(self, n=None):
        """
        獲取最近 n 個心跳的記錄
        
        如果不指定 n，返回全部
        """
        if n is None:
            return list(self.memory)
        else:
            return list(self.memory)[-n:]
    
    def clear(self):
        """清空工作記憶（通常不需要，因為會自動 FIFO）"""
        self.memory.clear()
        self._save()
    
    def _save(self):
        """持久化到硬碟"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(list(self.memory), f, indent=2, ensure_ascii=False)
    
    def _load(self):
        """從硬碟載入"""
        if self.storage_path.exists():
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.memory = deque(data, maxlen=self.capacity)
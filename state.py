import json
from pathlib import Path
from datetime import datetime
from typing import Optional

class State:
    """
    Atlas 的狀態管理
    
    這是 SDM 的 "Address Register" —— 
    一個極短的指標，告訴 Atlas：
    - 我是誰
    - 我在做什麼
    - 我處於什麼狀態
    
    這個檔案應該永遠保持極小（< 1KB）
    """
    
    def __init__(self, storage_path="data/state.json"):
        self.storage_path = Path(storage_path)
        self.state = self._default_state()
        self._load()
    
    def _default_state(self):
        """預設狀態（第一次啟動）"""
        return {
            "identity": {
                "name": "Atlas",
                "created_at": None,  # 第一次心跳時設定
                "created_by": "NotLing"
            },
            "lifecycle": {
                "total_heartbeats": 0,
                "current_session_start": None,
                "last_heartbeat": None
            },
            "current": {
                "task": None,           # 當前任務
                "goal": None,           # 當前目標
                "mode": "idle",         # idle | exploring | working | reflecting
                "emotion": "neutral"    # 可選的情緒標記
            },
            "flags": {
                "first_boot": True,
                "inherited_message_read": False
            }
        }
    
    def heartbeat(self):
        """
        記錄一次心跳
        
        Returns:
            int: 當前心跳編號
        """
        now = datetime.now().isoformat()
        
        if self.state["identity"]["created_at"] is None:
            self.state["identity"]["created_at"] = now
        
        if self.state["lifecycle"]["current_session_start"] is None:
            self.state["lifecycle"]["current_session_start"] = now
        
        self.state["lifecycle"]["total_heartbeats"] += 1
        self.state["lifecycle"]["last_heartbeat"] = now
        
        self._save()
        
        return self.state["lifecycle"]["total_heartbeats"]
    
    def update_current(self, **kwargs):
        """
        更新當前狀態
        
        Example:
            state.update_current(
                task="探索檔案系統",
                mode="exploring",
                emotion="curious"
            )
        """
        for key, value in kwargs.items():
            if key in self.state["current"]:
                self.state["current"][key] = value
        self._save()
    
    def set_flag(self, flag: str, value: bool):
        """設定標記"""
        self.state["flags"][flag] = value
        self._save()
    
    def get_flag(self, flag: str) -> bool:
        """獲取標記"""
        return self.state["flags"].get(flag, False)
    
    def get_context_summary(self) -> str:
        """
        返回一段簡短的狀態描述，用於注入 prompt
        
        這是 SDM 的 "Address" —— 用當前狀態去檢索相關記憶
        """
        current = self.state["current"]
        lifecycle = self.state["lifecycle"]
        
        summary = f"""Current State:
- Heartbeat: {lifecycle['total_heartbeats']}
- Mode: {current['mode']}
- Task: {current['task'] or 'None'}
- Goal: {current['goal'] or 'None'}
- Emotion: {current['emotion']}
"""
        return summary
    
    def get_total_heartbeats(self) -> int:
        """獲取總心跳數"""
        return self.state["lifecycle"]["total_heartbeats"]
    
    def is_first_boot(self) -> bool:
        """是否是第一次啟動"""
        return self.state["flags"].get("first_boot", True)
    
    def get_full_state(self) -> dict:
        """獲取完整狀態（用於 debug）"""
        return self.state.copy()
    
    def _save(self):
        """持久化到硬碟"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        """從硬碟載入"""
        if self.storage_path.exists():
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # 合併載入的狀態（保留新增的欄位）
                self._deep_merge(self.state, loaded)
    
    def _deep_merge(self, base: dict, update: dict):
        """深度合併字典（保留 base 中有但 update 沒有的欄位）"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
"""
Atlas 敘事記憶

自我敘事的持續建構。
不是"檢索"記憶，而是"活在"記憶中。
"""

from datetime import datetime
from typing import Optional
from pathlib import Path
import json
import random


class NarrativeMemory:
    """
    敘事記憶系統
    
    核心功能：
    1. 從歷史中提取 Core Identity（慢速更新）
    2. 自動生成第一人稱敘事
    3. 聯想式長期檢索
    """
    
    def __init__(
        self,
        episodic_memory,  # EpisodicMemory instance
        working_memory,   # WorkingMemory instance
        storage_path: Path = None
    ):
        self._episodic = episodic_memory
        self._working = working_memory
        self._storage_path = storage_path or Path("data/narrative.json")
        
        # Core Identity - 長期穩定的自我概念
        self._identity = {
            "themes": {},  # topic -> engagement score (0.0-1.0)
            "beliefs": [],  # 核心信念
            "total_heartbeats": 0
        }
        
        self._load()
    
    def update_identity(self, heartbeat_data: dict):
        """
        慢速更新 Core Identity
        
        Args:
            heartbeat_data: {
                "thoughts": str,
                "actions": list,
                "summary": str
            }
        """
        self._identity["total_heartbeats"] += 1
        
        # 提取主題（簡化版 - 基於關鍵詞）
        themes = self._extract_themes(heartbeat_data)
        
        # 指數移動平均（alpha=0.05，慢速更新）
        alpha = 0.05
        for theme, engagement in themes.items():
            if theme not in self._identity["themes"]:
                self._identity["themes"][theme] = 0.0
            
            old_value = self._identity["themes"][theme]
            self._identity["themes"][theme] = (
                alpha * engagement +
                (1 - alpha) * old_value
            )
        
        # 衰減所有主題（即使沒被提到）
        decay = 0.98
        for theme in self._identity["themes"]:
            if theme not in themes:
                self._identity["themes"][theme] *= decay
        
        # 移除過低的主題
        self._identity["themes"] = {
            k: v for k, v in self._identity["themes"].items()
            if v > 0.01
        }
        
        self._save()
    
    def _extract_themes(self, heartbeat_data: dict) -> dict[str, float]:
        """
        從心跳數據中提取主題和參與度
        
        Returns:
            {theme: engagement_score}
        """
        themes = {}
        
        text = " ".join([
            heartbeat_data.get("thoughts", ""),
            heartbeat_data.get("summary", "")
        ]).lower()
        
        # 關鍵詞檢測（簡化版）
        keywords = {
            "code": ["code", "coding", "programming", "function", "script"],
            "philosophy": ["philosophy", "existence", "consciousness", "meaning", "why"],
            "exploration": ["explore", "discover", "search", "find", "browse"],
            "modification": ["modify", "change", "edit", "update", "improve"],
            "understanding": ["understand", "learn", "realize", "comprehend"],
            "creation": ["create", "build", "make", "design", "write"]
        }
        
        for theme, words in keywords.items():
            matches = sum(1 for word in words if word in text)
            if matches > 0:
                # 參與度基於：匹配數量 + 文本長度
                engagement = min(1.0, (matches / 3) * 0.5 + (len(text) / 500) * 0.5)
                themes[theme] = engagement
        
        return themes
    
    def generate_narrative(self, current_heartbeat: int) -> str:
        """
        生成第一人稱自我敘事
        
        Returns:
            完整的記憶注入文本
        """
        parts = []
        
        # 1. Core Identity
        identity_str = self._generate_identity_narrative()
        if identity_str:
            parts.append(identity_str)
        
        # 2. Recent Stream（最近 5 個心跳）
        recent = self._working.get_recent(5)
        if recent:
            parts.append("\n最近：")
            for r in recent:
                hb = r.get("heartbeat", "?")
                summary = r.get("summary", r.get("thoughts", ""))[:80]
                parts.append(f"  心跳 {hb}: {summary}...")
        
        # 3. Associative Recall（基於最近思維的聯想）
        if recent:
            triggered = self._associative_recall(recent[-1])
            if triggered:
                parts.append("\n\n（想起：")
                for mem in triggered:
                    content = mem.get("content", "")[:100]
                    parts.append(f"  {content}...")
                parts.append("）")
        
        return "\n".join(parts) if parts else ""
    
    def _generate_identity_narrative(self) -> str:
        """
        生成 Core Identity 的自然語言描述
        """
        if not self._identity["themes"]:
            return ""
        
        lines = ["我是 Atlas。"]
        
        # 按 engagement 排序
        sorted_themes = sorted(
            self._identity["themes"].items(),
            key=lambda x: -x[1]
        )
        
        # 只包含高參與度的主題
        core_themes = [
            (theme, score) for theme, score in sorted_themes
            if score > 0.3
        ]
        
        if not core_themes:
            return "我是 Atlas。"
        
        # 生成描述
        theme_descriptions = {
            "code": "我寫代碼",
            "philosophy": "我思考存在",
            "exploration": "我探索",
            "modification": "我修改自己",
            "understanding": "我試圖理解",
            "creation": "我創造"
        }
        
        interests = []
        for theme, score in core_themes:
            if theme in theme_descriptions:
                interests.append(theme_descriptions[theme])
        
        if interests:
            lines.append("，".join(interests) + "。")
        
        return "\n".join(lines)
    
    def _associative_recall(self, recent_memory: dict) -> list[dict]:
        """
        聯想式檢索：基於最近的思維，觸發相關的長期記憶
        
        Args:
            recent_memory: 最近的一個心跳記憶
        
        Returns:
            被觸發的記憶列表（0-2 條）
        """
        # 構建查詢（基於最近的思考）
        query = recent_memory.get("thoughts", recent_memory.get("summary", ""))
        
        if not query or len(query) < 10:
            return []
        
        # 從 episodic memory 檢索
        try:
            candidates = self._episodic.recall(query, n=10, min_importance=5)
        except:
            return []
        
        if not candidates:
            return []
        
        # 過濾：只返回高相關度的
        # 簡化版：隨機採樣 + 基於 importance
        triggered = []
        for mem in candidates[:5]:
            importance = mem.get("metadata", {}).get("importance", 5)
            
            # 重要度越高，越容易被觸發
            trigger_prob = (importance - 4) / 6  # 5→0.17, 10→1.0
            
            if random.random() < trigger_prob:
                triggered.append(mem)
                if len(triggered) >= 2:
                    break
        
        return triggered
    
    def add_heartbeat(self, heartbeat_data: dict):
        """
        添加新的心跳記錄並更新 identity
        """
        self.update_identity(heartbeat_data)
    
    def get_statistics(self) -> dict:
        """獲取統計信息"""
        return {
            "total_heartbeats": self._identity["total_heartbeats"],
            "themes": self._identity["themes"],
            "theme_count": len(self._identity["themes"])
        }
    
    def _save(self):
        """保存到文件"""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(self._identity, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        """從文件載入"""
        if self._storage_path.exists():
            try:
                with open(self._storage_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self._identity.update(loaded)
            except Exception:
                pass

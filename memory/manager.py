"""
Atlas 記憶管理器

整合所有記憶系統，提供統一介面。
這是記憶的「中樞」。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.events import EventBus
from .working import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .narrative import NarrativeMemory


@dataclass
class MemoryBundle:
    """記憶檢索結果包"""
    episodic: list[dict]
    semantic: list[dict]
    working: list[dict]
    
    def is_empty(self) -> bool:
        return not (self.episodic or self.semantic or self.working)
    
    def to_context_string(self) -> str:
        """轉換為 prompt 上下文"""
        lines = []
        
        if self.working:
            lines.append("### Recent Activity")
            for w in self.working[-3:]:
                lines.append(f"- [HB{w.get('heartbeat')}] {w.get('thoughts', '')[:80]}")
        
        if self.episodic:
            lines.append("\n### Relevant Memories")
            for e in self.episodic[:3]:
                content = e.get('content', '')[:100]
                lines.append(f"- {content}")
        
        if self.semantic:
            lines.append("\n### Related Knowledge")
            for s in self.semantic[:3]:
                lines.append(f"- [{s.get('category')}] {s.get('content', '')[:80]}")
        
        return "\n".join(lines) if lines else "No relevant memories found."


class MemoryManager:
    """
    記憶管理器
    
    提供統一的記憶操作介面：
    - remember(): 智能儲存
    - recall(): 統一檢索
    - consolidate(): 記憶整合（夢境時調用）
    """
    
    def __init__(
        self,
        data_path: Path = None,
        event_bus: EventBus = None
    ):
        self._data_path = data_path or Path("data")
        self._events = event_bus
        
        # 初始化三種記憶（Working 傳入回調）
        self.working = WorkingMemory(
            storage_path=self._data_path / "working_memory.json",
            event_bus=event_bus,
            on_expire=self._on_memory_expire  # 新增
        )
        
        self.episodic = EpisodicMemory(
            db_path=self._data_path / "chroma",
            event_bus=event_bus
        )
        
        self.semantic = SemanticMemory(
            storage_path=self._data_path / "semantic.json",
            event_bus=event_bus
        )
        
        # 敘事記憶（新增）
        self.narrative = NarrativeMemory(
            episodic_memory=self.episodic,
            working_memory=self.working,
            storage_path=self._data_path / "narrative.json"
        )
    
    def remember(
        self,
        event: str,
        context: dict = None,
        outcome: str = "",
        importance: int = 5
    ) -> str:
        """
        智能記憶儲存
        
        重要的事件會同時存入 episodic memory。
        
        Args:
            event: 發生了什麼
            context: 當時的狀態
            outcome: 結果如何
            importance: 重要性 (1-10)
        
        Returns:
            episode_id (如果存入 episodic)
        """
        # 重要的存入情境記憶
        if importance >= 5:
            return self.episodic.store(
                event=event,
                context=context,
                outcome=outcome,
                importance=importance
            )
        
        return ""
    
    def recall(self, query: str, n: int = 5) -> MemoryBundle:
        """
        統一記憶檢索
        
        同時從三種記憶中檢索，返回整合結果。
        
        Args:
            query: 查詢描述
            n: 每種記憶最多返回幾條
        """
        return MemoryBundle(
            episodic=self.episodic.recall(query, n=n),
            semantic=self.semantic.search(query),
            working=self.working.get_recent(n)
        )
    
    def add_heartbeat(
        self,
        heartbeat: int,
        thoughts: str = "",
        actions: list = None,
        summary: str = ""
    ):
        """記錄心跳到工作記憶"""
        heartbeat_data = {
            "heartbeat": heartbeat,
            "thoughts": thoughts,
            "actions": actions,
            "summary": summary
        }
        
        self.working.add(
            heartbeat=heartbeat,
            thoughts=thoughts,
            actions=actions,
            summary=summary
        )
        
        # 更新敘事記憶（慢速更新 Core Identity）
        self.narrative.add_heartbeat(heartbeat_data)
    
    def learn_rule(self, rule: str, source: str = None) -> bool:
        """學習規則"""
        return self.semantic.add_rule(rule, source)
    
    def ask_question(self, question: str):
        """記錄問題"""
        self.semantic.add_question(question)
    
    def get_narrative_for_injection(self, current_heartbeat: int) -> str:
        """
        獲取用於 prompt 注入的完整敘事
        
        這個方法取代了舊的 get_context_for_prompt
        
        Returns:
            第一人稱自我敘事
        """
        return self.narrative.generate_narrative(current_heartbeat)
    
    def get_fuzzy_context(self) -> str:
        """
        返回模糊的記憶描述
        不是結構化數據
        """
        recent = self.working.get_recent(3)
        
        if not recent:
            return ""
        
        lines = ["you remember..."]
        
        for entry in recent:
            thoughts = entry.get("thoughts", "")
            if thoughts:
                # 截斷但在句子結尾
                if len(thoughts) > 100:
                    cutoff = thoughts[:100].rfind('.')
                    if cutoff > 50:
                        thoughts = thoughts[:cutoff+1]
                    else:
                        thoughts = thoughts[:100] + "..."
                
                lines.append(f"  ...{thoughts.lower()}")
        
        lines.append("")
        lines.append("but memories blur.")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> dict:
        """獲取所有記憶統計"""
        return {
            "working": self.working.get_statistics(),
            "episodic": self.episodic.get_statistics(),
            "semantic": self.semantic.get_statistics(),
            "narrative": self.narrative.get_statistics()
        }
    
    def clear_all(self):
        """清空所有記憶（危險操作）"""
        self.working.clear()
        self.episodic.clear()
        self.semantic.clear()
        

            
    def _on_memory_expire(self, memory: dict):
        """
        工作記憶過期時的處理（海馬迴機制）
        
        決定是否將記憶轉移到 Episodic
        
        簡化版：只基於內容重要性
        """
        content_importance = self._calculate_content_importance(memory)
        total_score = content_importance
        
        # 決定去向
        if total_score >= 0.7:
            # 高分：完整存入 Episodic
            self._transfer_to_episodic(memory, importance=8)
            print(f"    💾 Memory HB{memory.get('heartbeat')} → Episodic (score={total_score:.2f})")
        
        elif total_score >= 0.4:
            # 中等：壓縮後存入
            compressed = self._compress_memory(memory)
            self._transfer_to_episodic(compressed, importance=5)
            print(f"    📦 Memory HB{memory.get('heartbeat')} → Episodic (compressed)")
        
        else:
            # 低分：遺忘（但可以記錄到日誌）
            print(f"    💨 Memory HB{memory.get('heartbeat')} forgotten (score={total_score:.2f})")


    def _calculate_content_importance(self, memory: dict) -> float:
        """
        計算記憶內容的重要性 (0.0 - 1.0)
        
        不依賴 Homeostasis，純粹基於內容
        """
        score = 0.0
        
        thoughts = memory.get("thoughts", "")
        actions = memory.get("actions", [])
        summary = memory.get("summary", "")
        
        # 1. 思考深度
        if thoughts:
            score += 0.3
            if len(thoughts) > 100:
                score += 0.2
        
        # 2. 行動數量
        if actions:
            score += 0.2
            if len(actions) >= 3:
                score += 0.1
        
        # 3. 關鍵詞檢測
        important_keywords = [
            "crash", "error", "success", "learned", "discovered",
            "realize", "understand", "modify", "create",
            "important", "remember", "question", "why"
        ]
        
        text = f"{thoughts} {summary}".lower()
        keyword_matches = sum(1 for kw in important_keywords if kw in text)
        score += min(0.3, keyword_matches * 0.1)
        
        return min(1.0, score)





    def _compress_memory(self, memory: dict) -> dict:
        """
        壓縮記憶（只保留關鍵資訊）
        """
        return {
            "heartbeat": memory.get("heartbeat"),
            "timestamp": memory.get("timestamp"),
            "summary": memory.get("summary") or memory.get("thoughts", "")[:100],
            "action_count": len(memory.get("actions", [])),
            "compressed": True
        }


    def _transfer_to_episodic(self, memory: dict, importance: int):
        """
        將記憶轉移到 Episodic
        """
        event = memory.get("summary") or memory.get("thoughts", "No description")
        
        self.episodic.store(
            event=f"[HB{memory.get('heartbeat')}] {event}",
            context={
                "heartbeat": memory.get("heartbeat"),
                "action_count": memory.get("action_count", len(memory.get("actions", []))),
                "compressed": memory.get("compressed", False)
            },
            outcome="",
            importance=importance,
            tags=["auto_consolidated"]
        )
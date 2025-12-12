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
        
        # 初始化三種記憶
        self.working = WorkingMemory(
            storage_path=self._data_path / "working_memory.json",
            event_bus=event_bus
        )
        
        self.episodic = EpisodicMemory(
            db_path=self._data_path / "chroma",
            event_bus=event_bus
        )
        
        self.semantic = SemanticMemory(
            storage_path=self._data_path / "semantic.json",
            event_bus=event_bus
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
        self.working.add(
            heartbeat=heartbeat,
            thoughts=thoughts,
            actions=actions,
            summary=summary
        )
    
    def learn_rule(self, rule: str, source: str = None) -> bool:
        """學習規則"""
        return self.semantic.add_rule(rule, source)
    
    def ask_question(self, question: str):
        """記錄問題"""
        self.semantic.add_question(question)
    
    def get_context_for_prompt(self) -> str:
        """
        獲取用於 prompt 的記憶上下文
        
        Returns:
            格式化的記憶摘要
        """
        lines = []
        
        # 最近的工作記憶
        recent = self.working.get_recent(3)
        if recent:
            lines.append("## Recent Activity")
            lines.append(self.working.get_context_string(3))
        
        # 規則
        rules = self.semantic.get_rules(limit=5)
        if rules:
            lines.append("\n## Known Rules")
            for r in rules:
                lines.append(f"- {r}")
        
        # 未解問題
        questions = self.semantic.get_open_questions()
        if questions:
            lines.append("\n## Open Questions")
            for q in questions[-3:]:
                lines.append(f"- {q}")
        
        return "\n".join(lines) if lines else ""
    
    def get_statistics(self) -> dict:
        """獲取所有記憶統計"""
        return {
            "working": self.working.get_statistics(),
            "episodic": self.episodic.get_statistics(),
            "semantic": self.semantic.get_statistics()
        }
    
    def clear_all(self):
        """清空所有記憶（危險操作）"""
        self.working.clear()
        self.episodic.clear()
        self.semantic.clear()
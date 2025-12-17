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
        event_bus: EventBus = None,
        homeostasis = None  # 新增：用於計算情緒權重
    ):
        self._data_path = data_path or Path("data")
        self._events = event_bus
        self._homeostasis = homeostasis  # 新增
        
        # === 追蹤情緒變化（用於計算衝擊）===
        self._last_drive_snapshot = None  # 新增
        
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
        
    def snapshot_drives(self):
        """
        記錄當前驅動力狀態（每個心跳開始時調用）
        用於計算情緒衝擊
        """
        if self._homeostasis:
            self._last_drive_snapshot = {
                name: drive.value 
                for name, drive in self._homeostasis.drives.items()
            }
            
    def _on_memory_expire(self, memory: dict):
        """
        工作記憶過期時的處理（海馬迴機制）
        
        決定是否將記憶轉移到 Episodic
        """
        # 計算內容重要性（基礎分）
        content_importance = self._calculate_content_importance(memory)
        
        # 計算情緒衝擊（Gemini 的建議！）
        emotional_impact = self._calculate_emotional_impact()
        
        # 綜合分數
        total_score = content_importance + emotional_impact * 0.5
        
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
        """
        score = 0.0
        
        thoughts = memory.get("thoughts", "")
        actions = memory.get("actions", [])
        summary = memory.get("summary", "")
        
        # 有思考內容
        if thoughts:
            score += 0.2
            # 思考內容豐富
            if len(thoughts) > 100:
                score += 0.1
        
        # 有執行動作
        if actions:
            score += 0.2
            # 多個動作
            if len(actions) >= 3:
                score += 0.1
        
        # 有摘要
        if summary:
            score += 0.2
        
        # 關鍵字檢測
        important_keywords = ["error", "success", "learned", "discovered", "important", "remember"]
        text = f"{thoughts} {summary}".lower()
        for keyword in important_keywords:
            if keyword in text:
                score += 0.1
                break
        
        return min(1.0, score)


    def _calculate_emotional_impact(self) -> float:
        """
        計算情緒衝擊 (0.0 - 1.0)
        
        基於驅動力的變化幅度
        """
        if not self._homeostasis or not self._last_drive_snapshot:
            return 0.0
        
        total_delta = 0.0
        
        for name, drive in self._homeostasis.drives.items():
            old_value = self._last_drive_snapshot.get(name, drive.value)
            delta = abs(drive.value - old_value)
            
            # 某些驅動力的變化更重要
            if name == "satisfaction":
                delta *= 1.5  # 滿意度變化權重更高
            elif name == "anxiety":
                delta *= 1.3  # 焦慮變化也重要
            
            total_delta += delta
        
        # 正規化（4 個驅動力，每個最大變化 1.0）
        normalized = total_delta / 4.0
        
        return min(1.0, normalized * 2)  # 放大效果


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
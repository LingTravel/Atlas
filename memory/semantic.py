"""
Atlas 語義記憶

知識、規則、信念的儲存。
這是 Atlas 的「智慧結晶」。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from core.events import EventBus


class SemanticMemory:
    """
    語義記憶 (Knowledge Base)
    
    儲存的不是事件，而是從事件中提煉的知識：
    - rules: 行為規則
    - beliefs: 信念/理解
    - facts: 已確認的事實
    - questions: 未解之謎
    """
    
    def __init__(
        self,
        storage_path: Path = None,
        event_bus: EventBus = None
    ):
        self._storage_path = storage_path or Path("data/semantic.json")
        self._events = event_bus
        
        self._knowledge = {
            "rules": [],
            "beliefs": [],
            "facts": [],
            "questions": []
        }
        
        self._load()
    
    def add_rule(self, rule: str, source: str = None) -> bool:
        """
        添加行為規則
        
        Args:
            rule: 規則內容
            source: 來源（經驗/夢境/教導）
        
        Returns:
            是否成功（重複則失敗）
        """
        # 避免重複
        if any(r["content"] == rule for r in self._knowledge["rules"]):
            return False
        
        entry = {
            "content": rule,
            "source": source or "experience",
            "created_at": datetime.now().isoformat()
        }
        
        self._knowledge["rules"].append(entry)
        self._save()
        
        if self._events:
            self._events.emit("memory.semantic.learn", {
                "type": "rule",
                "content": rule[:50]
            }, source="SemanticMemory")
        
        return True
    
    def add_belief(self, belief: str, confidence: float = 0.5) -> None:
        """
        添加信念（可以有多個相似的，信心度不同）
        
        Args:
            belief: 信念內容
            confidence: 信心程度 (0.0-1.0)
        """
        entry = {
            "content": belief,
            "confidence": max(0.0, min(1.0, confidence)),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        self._knowledge["beliefs"].append(entry)
        self._save()
    
    def add_fact(self, fact: str, source: str = "system") -> bool:
        """添加已驗證的事實"""
        if any(f["content"] == fact for f in self._knowledge["facts"]):
            return False
        
        entry = {
            "content": fact,
            "source": source,
            "verified": True,
            "created_at": datetime.now().isoformat()
        }
        
        self._knowledge["facts"].append(entry)
        self._save()
        return True
    
    def add_question(self, question: str) -> None:
        """記錄未解的問題"""
        entry = {
            "content": question,
            "status": "open",
            "created_at": datetime.now().isoformat()
        }
        
        self._knowledge["questions"].append(entry)
        self._save()
    
    def resolve_question(self, question: str, answer: str) -> bool:
        """回答一個問題"""
        for q in self._knowledge["questions"]:
            if q["content"] == question and q["status"] == "open":
                q["status"] = "resolved"
                q["answer"] = answer
                q["resolved_at"] = datetime.now().isoformat()
                self._save()
                
                # 同時添加為事實
                self.add_fact(f"{question} → {answer}", source="resolution")
                return True
        return False
    
    def get_all(self, category: str = None) -> list | dict:
        """
        獲取知識
        
        Args:
            category: "rules" | "beliefs" | "facts" | "questions" | None (全部)
        """
        if category:
            return self._knowledge.get(category, [])
        return self._knowledge
    
    def get_rules(self, limit: int = None) -> list[str]:
        """獲取規則列表（純文字）"""
        rules = [r["content"] for r in self._knowledge["rules"]]
        if limit:
            rules = rules[-limit:]
        return rules
    
    def get_open_questions(self) -> list[str]:
        """獲取未解問題"""
        return [
            q["content"] 
            for q in self._knowledge["questions"] 
            if q["status"] == "open"
        ]
    
    def search(self, keyword: str) -> list[dict]:
        """關鍵字搜尋"""
        results = []
        for category, items in self._knowledge.items():
            for item in items:
                if keyword.lower() in item.get("content", "").lower():
                    results.append({
                        "category": category,
                        **item
                    })
        return results
    
    def get_statistics(self) -> dict:
        return {
            "rules": len(self._knowledge["rules"]),
            "beliefs": len(self._knowledge["beliefs"]),
            "facts": len(self._knowledge["facts"]),
            "open_questions": len(self.get_open_questions()),
            "resolved_questions": len([
                q for q in self._knowledge["questions"]
                if q["status"] == "resolved"
            ])
        }
    
    def clear(self):
        """清空所有知識"""
        self._knowledge = {
            "rules": [],
            "beliefs": [],
            "facts": [],
            "questions": []
        }
        self._save()
    
    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(self._knowledge, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        if self._storage_path.exists():
            try:
                with open(self._storage_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                # 合併（保留新增的類別）
                for key in self._knowledge:
                    if key in loaded:
                        self._knowledge[key] = loaded[key]
            except Exception:
                pass
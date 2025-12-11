import json
from pathlib import Path
from datetime import datetime

class SemanticMemory:
    """
    語義記憶（Semantic Memory）
    
    這裡存的不是「某次發生了什麼」（那是 episodic），
    而是「我知道什麼」—— 規則、知識、信念。
    
    例如：
    - "永遠不要在沒有 import 的情況下使用 numpy"
    - "NotLing 創造了我，但不會主動出現"
    - "當我感到困惑時，應該先檢查 facts.md"
    
    這些是提煉出來的智慧，不綁定特定事件。
    """
    
    def __init__(self, storage_path="data/semantic.json"):
        self.storage_path = Path(storage_path)
        self.knowledge = {
            "rules": [],      # 行為規則
            "beliefs": [],    # 信念/理解
            "facts": [],      # 已確認的事實
            "questions": []   # 未解之謎
        }
        self._load()
    
    def add_rule(self, rule: str, learned_from: str = None):
        """
        添加一條規則
        
        Args:
            rule: 規則內容
            learned_from: 從哪個經驗學到的（可選）
        """
        entry = {
            "content": rule,
            "type": "rule",
            "learned_from": learned_from,
            "created_at": datetime.now().isoformat()
        }
        
        # 避免重複
        if not any(r["content"] == rule for r in self.knowledge["rules"]):
            self.knowledge["rules"].append(entry)
            self._save()
            return True
        return False
    
    def add_belief(self, belief: str, confidence: float = 0.5):
        """
        添加一個信念（不一定是絕對真理）
        
        Args:
            belief: 信念內容
            confidence: 信心程度（0.0 - 1.0）
        """
        entry = {
            "content": belief,
            "type": "belief",
            "confidence": confidence,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        self.knowledge["beliefs"].append(entry)
        self._save()
    
    def add_fact(self, fact: str, source: str = "system"):
        """
        添加一個已驗證的事實
        
        Args:
            fact: 事實內容
            source: 來源（system/experience/external）
        """
        entry = {
            "content": fact,
            "type": "fact",
            "source": source,
            "verified": True,
            "created_at": datetime.now().isoformat()
        }
        
        if not any(f["content"] == fact for f in self.knowledge["facts"]):
            self.knowledge["facts"].append(entry)
            self._save()
            return True
        return False
    
    def add_question(self, question: str):
        """
        記錄一個未解的問題
        
        這些問題可以驅動 Atlas 的探索行為
        """
        entry = {
            "content": question,
            "type": "question",
            "status": "open",
            "created_at": datetime.now().isoformat()
        }
        
        self.knowledge["questions"].append(entry)
        self._save()
    
    def resolve_question(self, question: str, answer: str):
        """
        回答一個問題（將其轉為 fact 或 belief）
        """
        for q in self.knowledge["questions"]:
            if q["content"] == question and q["status"] == "open":
                q["status"] = "resolved"
                q["answer"] = answer
                q["resolved_at"] = datetime.now().isoformat()
                self._save()
                
                # 同時添加到 facts
                self.add_fact(f"{question} → {answer}", source="experience")
                return True
        return False
    
    def get_all(self, category: str = None):
        """
        獲取所有知識，或特定類別
        
        Args:
            category: "rules" | "beliefs" | "facts" | "questions"
        """
        if category:
            return self.knowledge.get(category, [])
        return self.knowledge
    
    def search(self, keyword: str):
        """
        簡單的關鍵字搜尋（之後可以用 embedding 改進）
        """
        results = []
        for category, items in self.knowledge.items():
            for item in items:
                if keyword.lower() in item["content"].lower():
                    results.append({
                        "category": category,
                        **item
                    })
        return results
    
    def get_statistics(self):
        """返回知識庫統計"""
        return {
            "rules": len(self.knowledge["rules"]),
            "beliefs": len(self.knowledge["beliefs"]),
            "facts": len(self.knowledge["facts"]),
            "open_questions": len([q for q in self.knowledge["questions"] if q["status"] == "open"]),
            "resolved_questions": len([q for q in self.knowledge["questions"] if q["status"] == "resolved"])
        }
    
    def _save(self):
        """持久化到硬碟"""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            json.dump(self.knowledge, f, indent=2, ensure_ascii=False)
    
    def _load(self):
        """從硬碟載入"""
        if self.storage_path.exists():
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                self.knowledge = json.load(f)
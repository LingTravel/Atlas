import chromadb
from chromadb.config import Settings
import json
from datetime import datetime
from pathlib import Path

class EpisodicMemory:
    """
    情境記憶系統（SDM 實現）
    
    記憶不是日誌，而是可檢索的經驗。
    每個 episode 包含：
    - 發生了什麼（what）
    - 當時的狀態（context）
    - 結果如何（outcome）
    - 重要性（importance）
    """
    
    def __init__(self, db_path="data/chroma"):
        Path(db_path).mkdir(parents=True, exist_ok=True)
        
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 創建或獲取 collection
        self.episodes = self.client.get_or_create_collection(
            name="episodes",
            metadata={"description": "Episodic memories"}
        )
        
    def store(self, 
              event: str, 
              context: dict, 
              outcome: str,
              importance: int = 5,  # 1-10
              verified: bool = False):
        """
        儲存一段經驗
        
        Args:
            event: 發生了什麼（自然語言）
            context: 當時的狀態（JSON）
            outcome: 結果如何
            importance: 重要性（1-10，決定是否優先檢索）
            verified: 是否經過系統驗證（區分真實 vs 想像）
        """
        
        timestamp = datetime.now().isoformat()
        episode_id = f"ep_{timestamp}"
        
        # 組合成完整的記憶描述（用於 embedding）
        memory_text = f"""
        Event: {event}
        Context: {json.dumps(context)}
        Outcome: {outcome}
        """
        
        self.episodes.add(
            documents=[memory_text],
            metadatas=[{
                "timestamp": timestamp,
                "importance": importance,
                "verified": verified,
                "outcome_type": outcome,
                **context  # 展開 context 作為可搜尋的 metadata
            }],
            ids=[episode_id]
        )
        
        return episode_id
    
    def recall(self, 
               query: str, 
               n_results: int = 5,
               min_importance: int = 3,
               verified_only: bool = False):
        """
        根據當前情境檢索相關記憶
        
        這是 SDM 的核心：用當前狀態作為 Address，
        從 Hard Locations 中激活相關記憶
        
        Args:
            query: 當前情境的描述
            n_results: 最多返回幾條記憶
            min_importance: 最低重要性門檻
            verified_only: 是否只返回已驗證的記憶
        """
        
        # 構建 where 條件
        where = {"importance": {"$gte": min_importance}}
        if verified_only:
            where["verified"] = True
        
        results = self.episodes.query(
            query_texts=[query],
            n_results=n_results,
            where=where
        )
        
        # 整理返回格式
        memories = []
        if results['documents'] and results['documents'][0]:
            for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
                memories.append({
                    "content": doc,
                    "metadata": meta
                })
        
        return memories
    
    def get_statistics(self):
        """返回記憶統計資訊"""
        count = self.episodes.count()
        return {
            "total_episodes": count,
            "collection": "episodes"
        }
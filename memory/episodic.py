"""
Atlas 情境記憶

長期記憶，使用向量資料庫實現語義檢索。
這是 Atlas 的「人生經歷」。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from core.events import EventBus

# ChromaDB 延遲導入
_chroma_available = True
try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    _chroma_available = False


class EpisodicMemory:
    """
    情境記憶 (Semantic Search)
    
    使用 ChromaDB 進行向量檢索。
    每個 episode 包含：
    - 發生了什麼
    - 當時的狀態
    - 結果如何
    - 重要性
    """
    
    def __init__(
        self,
        db_path: Path = None,
        event_bus: EventBus = None
    ):
        self._db_path = db_path or Path("data/chroma")
        self._events = event_bus
        
        if not _chroma_available:
            raise ImportError("chromadb not installed. Run: pip install chromadb")
        
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self._db_path))
        self._collection = self._client.get_or_create_collection(
            name="episodes",
            metadata={"description": "Atlas episodic memories"}
        )
    
    def store(
        self,
        event: str,
        context: dict = None,
        outcome: str = "",
        importance: int = 5,
        tags: list[str] = None
    ) -> str:
        """
        儲存一段經歷
        
        Args:
            event: 發生了什麼
            context: 當時的狀態
            outcome: 結果如何
            importance: 重要性 (1-10)
            tags: 標籤
        
        Returns:
            episode_id: 記憶 ID
        """
        timestamp = datetime.now().isoformat()
        episode_id = f"ep_{timestamp.replace(':', '-')}"
        
        # 組合成完整描述（用於 embedding）
        memory_text = f"Event: {event}\nOutcome: {outcome}"
        if context:
            memory_text += f"\nContext: {json.dumps(context)}"
        
        metadata = {
            "timestamp": timestamp,
            "importance": importance,
            "outcome": outcome,
            "tags": ",".join(tags) if tags else "",
            **(context or {})
        }
        
        # 移除不能被 ChromaDB 處理的複雜類型
        clean_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                clean_metadata[k] = v
            else:
                clean_metadata[k] = str(v)
        
        self._collection.add(
            documents=[memory_text],
            metadatas=[clean_metadata],
            ids=[episode_id]
        )
        
        if self._events:
            self._events.emit("memory.episodic.store", {
                "id": episode_id,
                "event": event[:100],
                "importance": importance
            }, source="EpisodicMemory")
        
        return episode_id
    
    def recall(
        self,
        query: str,
        n: int = 5,
        min_importance: int = 1
    ) -> list[dict]:
        """
        檢索相關記憶
        
        Args:
            query: 查詢描述
            n: 返回數量
            min_importance: 最低重要性
        
        Returns:
            list of memories
        """
        if self._collection.count() == 0:
            return []
        
        results = self._collection.query(
            query_texts=[query],
            n_results=min(n, self._collection.count()),
            where={"importance": {"$gte": min_importance}} if min_importance > 1 else None
        )
        
        memories = []
        if results['documents'] and results['documents'][0]:
            for doc, meta, id_ in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['ids'][0]
            ):
                memories.append({
                    "id": id_,
                    "content": doc,
                    "metadata": meta
                })
        
        if self._events:
            self._events.emit("memory.episodic.recall", {
                "query": query[:50],
                "results_count": len(memories)
            }, source="EpisodicMemory")
        
        return memories
    
    def get_recent(self, n: int = 10) -> list[dict]:
        """獲取最近的記憶（按時間）"""
        if self._collection.count() == 0:
            return []
        
        # ChromaDB 不支持按時間排序，用 get 全部然後排序
        all_items = self._collection.get(
            limit=min(n * 2, self._collection.count())
        )
        
        memories = []
        if all_items['documents']:
            for doc, meta, id_ in zip(
                all_items['documents'],
                all_items['metadatas'],
                all_items['ids']
            ):
                memories.append({
                    "id": id_,
                    "content": doc,
                    "metadata": meta,
                    "timestamp": meta.get("timestamp", "")
                })
        
        # 按時間排序
        memories.sort(key=lambda x: x["timestamp"], reverse=True)
        return memories[:n]
    
    def clear(self):
        """清空所有記憶"""
        self._client.delete_collection("episodes")
        self._collection = self._client.get_or_create_collection(
            name="episodes",
            metadata={"description": "Atlas episodic memories"}
        )
    
    def get_statistics(self) -> dict:
        return {
            "total_episodes": self._collection.count()
        }
"""
Atlas 夢境系統

在疲勞過高時觸發，執行記憶整合。

夢境做什麼：
1. 從情境記憶中提取最近的重要片段
2. 讓 LLM 分析這些片段，找出模式
3. 提取規則/洞察，寫入語義記憶
4. 清理工作記憶（可選）
5. 恢復驅動力
"""

from typing import Optional
import json
import re
from datetime import datetime

from core.events import EventBus


class Dreaming:
    """
    夢境/記憶整合系統
    
    使用方式：
        dreamer = Dreaming(memory_manager, homeostasis, gemini_client, event_bus)
        
        if homeostasis.should_dream():
            dreamer.dream()
    """
    
    def __init__(
        self,
        memory_manager,      # MemoryManager
        homeostasis,         # Homeostasis
        llm_client,          # Gemini client
        event_bus: EventBus = None
    ):
        self._memory = memory_manager
        self._homeo = homeostasis
        self._llm = llm_client
        self._events = event_bus
        
        self._dream_count = 0
    
    def dream(self, depth: str = "light") -> dict:
        """
        執行夢境
        
        Args:
            depth: "light" | "deep"
                light: 快速整合最近記憶
                deep: 深度分析，可能清空工作記憶
        
        Returns:
            夢境報告
        """
        self._dream_count += 1
        
        if self._events:
            self._events.emit("dream.start", {
                "depth": depth,
                "dream_number": self._dream_count
            }, source="Dreaming")
        
        print("\n" + "="*60)
        print(f"💤 ENTERING DREAM STATE (#{self._dream_count})")
        print("="*60)
        
        # 收集記憶片段
        memories = self._gather_memories(depth)
        
        if not memories:
            print("[Dream] No memories to consolidate")
            self._homeo.rest()
            return {"success": False, "reason": "no_memories"}
        
        print(f"[Dream] Processing {len(memories)} memory fragments...")
        
        # 分析記憶
        insights = self._analyze_memories(memories, depth)
        
        # 存入語義記憶
        stored = self._store_insights(insights)
        
        # 清理（深度睡眠才清空工作記憶）
        if depth == "deep":
            print("[Dream] Deep sleep - clearing working memory")
            self._memory.working.clear()
        
        # 恢復驅動力
        self._homeo.rest()
        
        report = {
            "success": True,
            "depth": depth,
            "memories_processed": len(memories),
            "insights_gained": stored,
            "dream_number": self._dream_count,
            "timestamp": datetime.now().isoformat()
        }
        
        if self._events:
            self._events.emit("dream.end", report, source="Dreaming")
        
        print(f"[Dream] Consolidation complete. {stored['rules']} rules, {stored['questions']} questions learned.")
        print("="*60 + "\n")
        
        return report
    
    def _gather_memories(self, depth: str) -> list[dict]:
        """收集要處理的記憶片段"""
        memories = []
        
        # 從情境記憶獲取
        if depth == "deep":
            # 深度：最近 20 個重要記憶
            episodic = self._memory.episodic.get_recent(n=20)
        else:
            # 淺層：最近 10 個
            episodic = self._memory.episodic.get_recent(n=10)
        
        memories.extend(episodic)
        
        # 加入工作記憶的摘要
        working = self._memory.working.get_recent()
        for w in working:
            if w.get("summary") or w.get("thoughts"):
                memories.append({
                    "content": w.get("summary") or w.get("thoughts", ""),
                    "metadata": {"source": "working", "heartbeat": w.get("heartbeat")}
                })
        
        return memories
    
    def _analyze_memories(self, memories: list[dict], depth: str) -> dict:
        """使用 LLM 分析記憶"""
        
        # 構建夢境 prompt
        prompt = self._build_dream_prompt(memories, depth)
        
        try:
            response = self._llm.models.generate_content(
                model="gemini-2.0-flash",
                contents=[{"role": "user", "parts": [{"text": prompt}]}]
            )
            
            # 提取回應
            text = response.candidates[0].content.parts[0].text
            
            # 解析 JSON
            insights = self._parse_insights(text)
            
            return insights
            
        except Exception as e:
            print(f"[Dream] Error during analysis: {e}")
            return {"rules": [], "questions": [], "observations": []}
    
    def _build_dream_prompt(self, memories: list[dict], depth: str) -> str:
        """構建夢境分析 prompt"""
        
        prompt = f"""You are in a dream state, consolidating memories.

Depth: {depth}

Review these recent memory fragments:

"""
        
        for i, mem in enumerate(memories[:15], 1):  # 限制數量避免 token 過多
            content = mem.get("content", "")[:200]
            prompt += f"{i}. {content}\n"
        
        prompt += """

Based on these experiences, extract:
1. **Rules**: Patterns or principles learned (e.g., "When browsing fails, use read action instead")
2. **Questions**: New questions that emerged (e.g., "Why do I feel uncertain about X?")
3. **Observations**: Notable patterns or insights

Respond in JSON format:
{
  "rules": ["rule 1", "rule 2"],
  "questions": ["question 1"],
  "observations": ["observation 1"]
}

Be concise. Focus on actionable insights.
"""
        
        return prompt
    
    def _parse_insights(self, text: str) -> dict:
        """從 LLM 回應中提取 JSON"""
        
        # 嘗試找到 JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {
                    "rules": data.get("rules", []),
                    "questions": data.get("questions", []),
                    "observations": data.get("observations", [])
                }
            except json.JSONDecodeError:
                pass
        
        # 降級：簡單解析
        return {
            "rules": self._extract_list(text, "rules"),
            "questions": self._extract_list(text, "questions"),
            "observations": self._extract_list(text, "observations")
        }
    
    def _extract_list(self, text: str, key: str) -> list[str]:
        """降級解析：從文字中提取列表"""
        items = []
        lines = text.split('\n')
        
        in_section = False
        for line in lines:
            if key.lower() in line.lower():
                in_section = True
                continue
            
            if in_section:
                # 檢查是否是列表項
                if line.strip().startswith(('-', '*', '•', '1.', '2.', '3.')):
                    item = re.sub(r'^[\-\*\•\d\.]\s*', '', line.strip())
                    if item:
                        items.append(item)
                elif not line.strip():
                    in_section = False
        
        return items[:5]  # 限制數量
    
    def _store_insights(self, insights: dict) -> dict:
        """將洞察存入語義記憶"""
        
        stored = {
            "rules": 0,
            "questions": 0,
            "observations": 0
        }
        
        # 存入規則
        for rule in insights.get("rules", []):
            if self._memory.semantic.add_rule(rule, source="dream"):
                stored["rules"] += 1
                print(f"[Dream] Learned: {rule}")
        
        # 存入問題
        for question in insights.get("questions", []):
            self._memory.semantic.add_question(question)
            stored["questions"] += 1
            print(f"[Dream] Question: {question}")
        
        # 觀察可以存為 belief
        for obs in insights.get("observations", []):
            self._memory.semantic.add_belief(obs, confidence=0.6)
            stored["observations"] += 1
        
        return stored
    
    def get_statistics(self) -> dict:
        """獲取夢境統計"""
        return {
            "total_dreams": self._dream_count
        }
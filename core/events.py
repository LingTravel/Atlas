"""
Atlas 事件系統

事件命名規範：
─────────────────────────────────────────
A. 生命週期 (Lifecycle)
   - system.boot            系統啟動
   - system.shutdown        系統關閉
   - heartbeat.start        心跳開始
   - heartbeat.end          心跳結束

B. 感知 (Perception)
   - input.visual           看到圖像
   - input.text             收到文字

C. 認知 (Cognition)
   - thought.start          開始思考
   - thought.end            思考結束
   - decision.made          做出決定

D. 行動 (Action)
   - tool.called            工具被調用
   - tool.success           工具成功
   - tool.failure           工具失敗

E. 記憶 (Memory)
   - memory.working.add     加入工作記憶
   - memory.episodic.store  儲存情境記憶
   - memory.episodic.recall 檢索情境記憶
   - memory.semantic.learn  學習語義知識

F. 恆定 (Homeostasis)
   - drive.update           驅動力變化
   - drive.critical         驅動力臨界
   - dream.start            進入夢境
   - dream.end              夢境結束
─────────────────────────────────────────
"""

from typing import Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import json


@dataclass
class Event:
    """單一事件"""
    type: str
    data: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "unknown"


class EventBus:
    """
    事件總線
    
    使用方式：
        bus = EventBus()
        bus.on("tool.success", lambda e: print(f"Tool worked: {e.data}"))
        bus.emit("tool.success", {"tool": "read_file", "result": "..."})
    """
    
    def __init__(self, trace_enabled: bool = True):
        self._handlers: dict[str, list[Callable[[Event], None]]] = defaultdict(list)
        self._trace: list[Event] = []
        self._trace_enabled = trace_enabled
        self._max_trace = 1000  # 最多保留 1000 個事件
    
    def on(self, event_type: str, handler: Callable[[Event], None]):
        """
        註冊事件處理器
        
        Args:
            event_type: 事件類型（支持通配符 * 監聽所有）
            handler: 處理函數，接收 Event 對象
        """
        self._handlers[event_type].append(handler)
    
    def off(self, event_type: str, handler: Callable[[Event], None] = None):
        """
        移除事件處理器
        
        Args:
            event_type: 事件類型
            handler: 要移除的處理器（None = 移除所有）
        """
        if handler is None:
            self._handlers[event_type] = []
        else:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]
    
    def emit(self, event_type: str, data: Any = None, source: str = "unknown"):
        """
        發送事件
        
        Args:
            event_type: 事件類型
            data: 事件數據
            source: 事件來源
        """
        event = Event(type=event_type, data=data, source=source)
        
        # 記錄到 trace
        if self._trace_enabled:
            self._trace.append(event)
            if len(self._trace) > self._max_trace:
                self._trace.pop(0)
        
        # 調用特定處理器
        for handler in self._handlers[event_type]:
            try:
                handler(event)
            except Exception as e:
                # 發送錯誤事件（避免遞迴）
                if event_type != "error.handler":
                    self.emit("error.handler", {
                        "original_event": event_type,
                        "error": str(e)
                    }, source="EventBus")
        
        # 調用通配符處理器
        for handler in self._handlers["*"]:
            try:
                handler(event)
            except Exception:
                pass  # 通配符處理器錯誤靜默
    
    def get_trace(self, last_n: int = None, event_type: str = None) -> list[Event]:
        """
        獲取事件追蹤
        
        Args:
            last_n: 只返回最近 n 個
            event_type: 只返回特定類型
        """
        trace = self._trace
        
        if event_type:
            trace = [e for e in trace if e.type == event_type]
        
        if last_n:
            trace = trace[-last_n:]
        
        return trace
    
    def clear_trace(self):
        """清空追蹤記錄"""
        self._trace = []
    
    def export_trace(self, filepath: str = None) -> str:
        """
        導出追蹤記錄為 JSON
        
        Args:
            filepath: 可選，寫入檔案
        """
        data = [
            {
                "type": e.type,
                "data": e.data,
                "timestamp": e.timestamp,
                "source": e.source
            }
            for e in self._trace
        ]
        
        json_str = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(json_str)
        
        return json_str


# 全局事件總線（可選）
_global_bus: EventBus = None

def get_event_bus() -> EventBus:
    """獲取全局事件總線"""
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus
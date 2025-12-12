"""
Atlas 自適應恆定系統 (Adaptive Homeostasis)

這是 Atlas 的「內分泌系統」，現在具備自我調節能力。

四種驅動力：
- Curiosity (好奇心)
- Fatigue (疲勞)
- Anxiety (焦慮)
- Satisfaction (滿足感)

新功能：
- 自動檢測驅動力異常模式
- 自動調整參數（恢復速率、累積速率等）
- 記錄所有調整決策
- 安全上下限保護
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

from core.events import EventBus, Event


@dataclass
class Drive:
    """單一驅動力"""
    name: str
    value: float = 0.5
    baseline: float = 0.5
    decay_rate: float = 0.1
    
    low_threshold: float = 0.2
    high_threshold: float = 0.8
    
    def tick(self):
        """每心跳的自然變化 - 趨向 baseline"""
        diff = self.baseline - self.value
        self.value += diff * self.decay_rate
        self.value = max(0.0, min(1.0, self.value))
    
    def modify(self, delta: float):
        """外部事件影響"""
        self.value = max(0.0, min(1.0, self.value + delta))
    
    def is_low(self) -> bool:
        return self.value < self.low_threshold
    
    def is_high(self) -> bool:
        return self.value > self.high_threshold
    
    def level(self) -> str:
        if self.value < 0.2:
            return "very_low"
        elif self.value < 0.4:
            return "low"
        elif self.value < 0.6:
            return "moderate"
        elif self.value < 0.8:
            return "high"
        else:
            return "very_high"
    
    def to_dict(self) -> dict:
        return {
            "value": round(self.value, 3),
            "level": self.level(),
            "baseline": self.baseline
        }


class AdaptiveHomeostasis:
    """
    自適應恆定系統
    
    會自動觀察驅動力模式並調整參數。
    """
    
    def __init__(
        self, 
        event_bus: EventBus = None,
        storage_path: Path = None
    ):
        self._events = event_bus
        self._storage_path = storage_path or Path("data/homeostasis.json")
        
        # 初始化驅動力
        self.drives = {
            "curiosity": Drive(
                name="curiosity",
                value=0.7,
                baseline=0.5,
                decay_rate=0.08,
                low_threshold=0.25,
                high_threshold=0.75
            ),
            "fatigue": Drive(
                name="fatigue",
                value=0.0,
                baseline=0.0,
                decay_rate=0.05,
                low_threshold=0.2,
                high_threshold=0.8
            ),
            "anxiety": Drive(
                name="anxiety",
                value=0.3,
                baseline=0.2,
                decay_rate=0.12,
                low_threshold=0.15,
                high_threshold=0.7
            ),
            "satisfaction": Drive(
                name="satisfaction",
                value=0.5,
                baseline=0.5,
                decay_rate=0.06,
                low_threshold=0.25,
                high_threshold=0.75
            )
        }
        
        # === 自適應參數 ===
        self.params = {
            "curiosity_recovery_rate": 0.15,
            "curiosity_recovery_threshold": 0.4,
            "fatigue_accumulation": 0.03,
            "exploration_reward": 0.05,
            "creation_reward": 0.08,
            "repeat_penalty": -0.08
        }
        
        # 參數範圍（安全限制）
        self.param_limits = {
            "curiosity_recovery_rate": (0.05, 0.5),
            "curiosity_recovery_threshold": (0.3, 0.6),
            "fatigue_accumulation": (0.01, 0.08),
            "exploration_reward": (0.02, 0.15),
            "creation_reward": (0.05, 0.20),
            "repeat_penalty": (-0.20, -0.02)
        }
        
        # === 驅動力歷史追蹤 ===
        self.drive_history = {
            "curiosity": [],
            "fatigue": [],
            "anxiety": [],
            "satisfaction": []
        }
        self.history_size = 20
        
        # === 調整記錄 ===
        self.adjustments_log = []
        
        # 行為追蹤
        self._recent_actions: list[str] = []
        self._action_history_size = 20
        
        # 心跳計數
        self._ticks = 0
        
        self._load()
        
        # 註冊事件監聽
        if self._events:
            self._events.on("tool.success", self._on_tool_success)
            self._events.on("tool.failure", self._on_tool_failure)
    
    def tick(self):
        """每心跳調用"""
        self._ticks += 1
        
        # 記錄當前驅動力值
        for name, drive in self.drives.items():
            self.drive_history[name].append(drive.value)
            if len(self.drive_history[name]) > self.history_size:
                self.drive_history[name].pop(0)
        
        # === 自適應調整（每 5 個心跳檢查一次）===
        if self._ticks % 5 == 0:
            self._self_adjust()
        
        # 自然衰變
        for drive in self.drives.values():
            drive.tick()
        
        # 疲勞累積（使用自適應參數）
        self.drives["fatigue"].modify(self.params["fatigue_accumulation"])
        
        # === 好奇心自動恢復（使用自適應參數）===
        curiosity = self.drives["curiosity"]
        threshold = self.params["curiosity_recovery_threshold"]
        rate = self.params["curiosity_recovery_rate"]
        
        if curiosity.value < threshold:
            gap = threshold - curiosity.value
            recovery = gap * rate
            curiosity.modify(recovery)
        
        if curiosity.value < curiosity.baseline:
            curiosity.modify(0.02)
        # ==========================================
        
        self._check_critical()
        self._save()
    
    def _self_adjust(self):
        """
        自我調整參數
        
        檢測驅動力模式並自動優化參數。
        """
        adjustments_made = []
        
        # === 檢測好奇心長期過低 ===
        if len(self.drive_history["curiosity"]) >= 10:
            recent = self.drive_history["curiosity"][-10:]
            avg = sum(recent) / len(recent)
            
            if avg < 0.15:
                # 好奇心太低，提高恢復速率
                old_rate = self.params["curiosity_recovery_rate"]
                new_rate = min(
                    old_rate + 0.05,
                    self.param_limits["curiosity_recovery_rate"][1]
                )
                
                if new_rate != old_rate:
                    self.params["curiosity_recovery_rate"] = new_rate
                    adjustments_made.append({
                        "param": "curiosity_recovery_rate",
                        "old": old_rate,
                        "new": new_rate,
                        "reason": f"Curiosity too low (avg={avg:.2f})"
                    })
            
            elif avg > 0.75:
                # 好奇心過高，可以降低恢復速率
                old_rate = self.params["curiosity_recovery_rate"]
                new_rate = max(
                    old_rate - 0.02,
                    self.param_limits["curiosity_recovery_rate"][0]
                )
                
                if new_rate != old_rate:
                    self.params["curiosity_recovery_rate"] = new_rate
                    adjustments_made.append({
                        "param": "curiosity_recovery_rate",
                        "old": old_rate,
                        "new": new_rate,
                        "reason": f"Curiosity high (avg={avg:.2f})"
                    })
        
        # === 檢測疲勞累積過快 ===
        if len(self.drive_history["fatigue"]) >= 5:
            recent = self.drive_history["fatigue"][-5:]
            
            # 如果 5 次心跳疲勞從低到高
            if recent[0] < 0.3 and recent[-1] > 0.75:
                old_accum = self.params["fatigue_accumulation"]
                new_accum = max(
                    old_accum * 0.8,
                    self.param_limits["fatigue_accumulation"][0]
                )
                
                if new_accum != old_accum:
                    self.params["fatigue_accumulation"] = new_accum
                    adjustments_made.append({
                        "param": "fatigue_accumulation",
                        "old": old_accum,
                        "new": new_accum,
                        "reason": "Fatigue accumulating too fast"
                    })
        
        # === 檢測滿意度長期過低 ===
        if len(self.drive_history["satisfaction"]) >= 10:
            recent = self.drive_history["satisfaction"][-10:]
            avg = sum(recent) / len(recent)
            
            if avg < 0.3:
                # 提高創造獎勵
                old_reward = self.params["creation_reward"]
                new_reward = min(
                    old_reward + 0.02,
                    self.param_limits["creation_reward"][1]
                )
                
                if new_reward != old_reward:
                    self.params["creation_reward"] = new_reward
                    adjustments_made.append({
                        "param": "creation_reward",
                        "old": old_reward,
                        "new": new_reward,
                        "reason": f"Satisfaction too low (avg={avg:.2f})"
                    })
        
        # === 記錄調整 ===
        if adjustments_made:
            log_entry = {
                "heartbeat": self._ticks,
                "timestamp": datetime.now().isoformat(),
                "adjustments": adjustments_made
            }
            self.adjustments_log.append(log_entry)
            
            # 打印調整
            print("\n" + "="*60)
            print("🔧 SELF-ADJUSTMENT TRIGGERED")
            print("="*60)
            for adj in adjustments_made:
                print(f"[Adaptive] {adj['param']}: {adj['old']:.3f} → {adj['new']:.3f}")
                print(f"  Reason: {adj['reason']}")
            print("="*60 + "\n")
            
            # 發送事件
            if self._events:
                self._events.emit("homeostasis.adjusted", log_entry, source="AdaptiveHomeostasis")
    
    def _check_critical(self):
        """檢查驅動力臨界值"""
        if not self._events:
            return
        
        if self.drives["fatigue"].is_high():
            self._events.emit("drive.critical", {
                "drive": "fatigue",
                "value": self.drives["fatigue"].value,
                "suggestion": "rest"
            }, source="Homeostasis")
        
        if self.drives["curiosity"].is_low():
            self._events.emit("drive.critical", {
                "drive": "curiosity",
                "value": self.drives["curiosity"].value,
                "suggestion": "seek_novelty"
            }, source="Homeostasis")
        
        if self.drives["anxiety"].is_high():
            self._events.emit("drive.critical", {
                "drive": "anxiety",
                "value": self.drives["anxiety"].value,
                "suggestion": "reflect"
            }, source="Homeostasis")
        
        if self.drives["satisfaction"].is_low():
            self._events.emit("drive.critical", {
                "drive": "satisfaction",
                "value": self.drives["satisfaction"].value,
                "suggestion": "create"
            }, source="Homeostasis")
    
    def on_action(self, action: str, success: bool = True, context: dict = None):
        """行為發生時調用"""
        self._recent_actions.append(action)
        if len(self._recent_actions) > self._action_history_size:
            self._recent_actions.pop(0)
        
        # 從 context 獲取計數
        count = 0
        if context and isinstance(context, dict):
            count = context.get("read_count", 0)
            if count == 0:
                count = context.get("visit_count", 0)
        
        self._process_action(action, success, count)
        
        diversity = self.get_diversity()
        if diversity < 0.3:
            self.drives["curiosity"].modify(-0.03)
        
        self._save()
    
    def _process_action(self, action: str, success: bool, count: int = 0):
        """根據具體行為調整驅動力（使用自適應參數）"""
        
        # 探索類行為
        if action in ["browse", "read_file", "recall", "search"]:
            if success:
                if count >= 3:
                    # 嚴重重複
                    penalty = self.params["repeat_penalty"] * 1.5
                    self.drives["curiosity"].modify(penalty)
                    self.drives["satisfaction"].modify(penalty * 0.5)
                    self.drives["anxiety"].modify(0.05)
                elif count >= 2:
                    # 重複
                    penalty = self.params["repeat_penalty"]
                    self.drives["curiosity"].modify(penalty)
                    self.drives["satisfaction"].modify(penalty * 0.3)
                elif count == 1:
                    # 第二次
                    self.drives["curiosity"].modify(-0.03)
                else:
                    # 首次探索 → 獎勵（使用自適應參數）
                    reward = self.params["exploration_reward"]
                    self.drives["curiosity"].modify(reward)
                    self.drives["satisfaction"].modify(reward * 0.6)
            
            self.drives["fatigue"].modify(0.02)
        
        # 創造類行為 → 獎勵（使用自適應參數）
        elif action in ["write_file", "execute_python", "remember"]:
            if success:
                reward = self.params["creation_reward"]
                self.drives["satisfaction"].modify(reward)
                self.drives["curiosity"].modify(reward)
            self.drives["fatigue"].modify(0.03)
        
        # 反思類行為
        elif action in ["learn_rule", "update_state"]:
            self.drives["anxiety"].modify(-0.08)
            self.drives["curiosity"].modify(0.02)
            self.drives["fatigue"].modify(0.01)
        
        # 失敗處理
        if not success:
            self.drives["anxiety"].modify(0.05)
            self.drives["satisfaction"].modify(-0.03)
    
    def _on_tool_success(self, event: Event):
        """事件監聽：工具成功"""
        pass
    
    def _on_tool_failure(self, event: Event):
        """事件監聽：工具失敗"""
        tool_name = event.data.get("name", "") if event.data else ""
        self.on_action(tool_name, success=False)
    
    def get_diversity(self) -> float:
        """計算最近行為的多樣性"""
        if not self._recent_actions:
            return 1.0
        
        unique = len(set(self._recent_actions))
        total = len(self._recent_actions)
        return unique / total
    
    def get_state(self) -> dict:
        """獲取當前狀態"""
        return {
            name: drive.to_dict()
            for name, drive in self.drives.items()
        }
    
    def get_suggested_mode(self) -> str:
        """根據當前驅動力建議行為模式"""
        curiosity = self.drives["curiosity"].value
        fatigue = self.drives["fatigue"].value
        anxiety = self.drives["anxiety"].value
        satisfaction = self.drives["satisfaction"].value
        
        if fatigue > 0.85:
            return "rest"
        if anxiety > 0.7:
            return "reflect"
        if curiosity > 0.7:
            return "explore"
        if curiosity < 0.3:
            return "seek_novelty"
        if satisfaction < 0.3:
            return "create"
        
        return "work"
    
    def get_prompt_injection(self) -> str:
        """生成注入 prompt 的狀態描述"""
        state = self.get_state()
        mode = self.get_suggested_mode()
        diversity = self.get_diversity()
        
        emojis = {
            "curiosity": "🔍",
            "fatigue": "😴",
            "anxiety": "😰",
            "satisfaction": "😊"
        }
        
        lines = ["## Internal State", ""]
        
        for name, info in state.items():
            emoji = emojis.get(name, "•")
            bar = self._value_to_bar(info["value"])
            lines.append(f"{emoji} {name}: {bar} ({info['level']})")
        
        lines.append("")
        lines.append(f"**Behavioral Diversity**: {diversity:.0%}")
        lines.append(f"**Suggested Mode**: {mode}")
        
        # 顯示最近調整
        if self.adjustments_log and len(self.adjustments_log) > 0:
            last_adj = self.adjustments_log[-1]
            if self._ticks - last_adj.get("heartbeat", 0) < 10:
                lines.append("")
                lines.append(f"🔧 *System self-adjusted {len(last_adj['adjustments'])} parameters recently*")
        
        lines.append("")
        if mode == "rest":
            lines.append("💤 I'm tired. I should do something light or reflect.")
        elif mode == "reflect":
            lines.append("🧘 Anxiety is elevated. I should take a moment to process.")
        elif mode == "explore":
            lines.append("🌟 Curiosity is high! Good time to explore.")
        elif mode == "seek_novelty":
            lines.append("⚡ Curiosity is low. I MUST try something NEW!")
        elif mode == "create":
            lines.append("🎨 Satisfaction is low. Creating something will help.")
        
        if diversity < 0.3:
            lines.append("")
            lines.append("⚠️ I've been repeating actions. I MUST vary my approach!")
        
        return "\n".join(lines)
    
    def _value_to_bar(self, value: float, length: int = 10) -> str:
        filled = int(value * length)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}]"
    
    def rest(self):
        """休息效果"""
        self.drives["fatigue"].modify(-0.5)
        self.drives["anxiety"].modify(-0.2)
        self.drives["curiosity"].modify(0.2)
        self.drives["satisfaction"].modify(0.1)
        self._save()
    
    def should_dream(self) -> bool:
        """是否應該進入夢境狀態"""
        return self.drives["fatigue"].value > 0.85
    
    def get_drive_history(self) -> dict:
        """獲取驅動力歷史（供夢境分析用）"""
        return self.drive_history.copy()
    
    def get_adjustments_log(self) -> list:
        """獲取調整歷史"""
        return self.adjustments_log.copy()
    
    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "drives": {
                name: {
                    "value": drive.value,
                    "baseline": drive.baseline,
                    "decay_rate": drive.decay_rate
                }
                for name, drive in self.drives.items()
            },
            "params": self.params,
            "drive_history": self.drive_history,
            "adjustments_log": self.adjustments_log,
            "recent_actions": self._recent_actions,
            "ticks": self._ticks,
            "last_updated": datetime.now().isoformat()
        }
        
        with open(self._storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _load(self):
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 載入驅動力
            for name, info in data.get("drives", {}).items():
                if name in self.drives:
                    self.drives[name].value = info.get("value", self.drives[name].value)
            
            # 載入參數
            if "params" in data:
                self.params.update(data["params"])
            
            # 載入歷史
            if "drive_history" in data:
                self.drive_history = data["drive_history"]
            
            if "adjustments_log" in data:
                self.adjustments_log = data["adjustments_log"]
            
            self._recent_actions = data.get("recent_actions", [])
            self._ticks = data.get("ticks", 0)
            
        except Exception:
            pass


# 向後兼容別名
Homeostasis = AdaptiveHomeostasis
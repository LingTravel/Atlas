"""
Atlas 自適應恆定系統 (Adaptive Homeostasis) v2.0

修正：數值飽和問題
新增：
- 邊際遞減效應
- 飽和衰減機制
- 競爭抑制
- 更強的自然衰減
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import json
import math

from core.events import EventBus, Event


@dataclass
class Drive:
    """單一驅動力（改進版）"""
    name: str
    value: float = 0.5
    baseline: float = 0.5
    decay_rate: float = 0.1
    
    low_threshold: float = 0.2
    high_threshold: float = 0.8
    
    # === 新增：飽和衰減參數 ===
    satiation_rate: float = 0.15  # 超過 baseline 時的額外衰減
    
    def tick(self):
        """每心跳的自然變化 - 改進版"""
        # 基礎衰減：趨向 baseline
        diff = self.baseline - self.value
        self.value += diff * self.decay_rate
        
        # === 新增：飽和衰減 ===
        # 當數值遠離 baseline 時，額外的「不適感」拉力
        if self.value > self.baseline + 0.2:
            # 高於 baseline 太多 → 額外向下拉
            excess = self.value - (self.baseline + 0.2)
            self.value -= excess * self.satiation_rate
        elif self.value < self.baseline - 0.2:
            # 低於 baseline 太多 → 額外向上拉（但較弱）
            deficit = (self.baseline - 0.2) - self.value
            self.value += deficit * self.satiation_rate * 0.5
        
        self.value = max(0.0, min(1.0, self.value))
    
    def modify(self, delta: float, apply_diminishing: bool = True):
        """
        外部事件影響（改進版）
        
        apply_diminishing: 是否應用邊際遞減效應
        """
        if apply_diminishing and delta > 0:
            # === 邊際遞減效應 ===
            # 越接近極端值，獎勵效果越小
            if self.value > 0.5:
                # 高於中點，獎勵遞減
                # 公式：effectiveness = 1 - (value - 0.5) * 1.6
                # 在 value=0.5 時 = 100%
                # 在 value=0.8 時 = 52%
                # 在 value=0.95 時 = 28%
                effectiveness = max(0.1, 1.0 - (self.value - 0.5) * 1.6)
                delta = delta * effectiveness
        
        elif apply_diminishing and delta < 0:
            # 懲罰也有邊際遞減（已經很低時，懲罰效果減弱）
            if self.value < 0.5:
                effectiveness = max(0.1, 1.0 - (0.5 - self.value) * 1.6)
                delta = delta * effectiveness
        
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
    自適應恆定系統 v2.0
    
    改進：
    - 邊際遞減效應
    - 飽和衰減機制
    - 競爭抑制
    - 更平衡的參數
    """
    
    def __init__(
        self, 
        event_bus: EventBus = None,
        storage_path: Path = None
    ):
        self._events = event_bus
        self._storage_path = storage_path or Path("data/homeostasis.json")
        
        # 初始化驅動力（調整後的參數）
        self.drives = {
            "curiosity": Drive(
                name="curiosity",
                value=0.6,          # 起始值略低
                baseline=0.5,
                decay_rate=0.12,    # 加強衰減 (was 0.08)
                satiation_rate=0.18, # 飽和衰減
                low_threshold=0.25,
                high_threshold=0.75
            ),
            "fatigue": Drive(
                name="fatigue",
                value=0.0,
                baseline=0.1,       # 基準略高於 0（人總是有點累的）
                decay_rate=0.08,    # 加強恢復 (was 0.05)
                satiation_rate=0.1,
                low_threshold=0.2,
                high_threshold=0.75  # 降低閾值 (was 0.8)
            ),
            "anxiety": Drive(
                name="anxiety",
                value=0.25,
                baseline=0.2,
                decay_rate=0.15,    # 加強衰減 (was 0.12)
                satiation_rate=0.12,
                low_threshold=0.15,
                high_threshold=0.65  # 降低閾值 (was 0.7)
            ),
            "satisfaction": Drive(
                name="satisfaction",
                value=0.5,
                baseline=0.45,      # 基準略低於中點
                decay_rate=0.10,    # 加強衰減 (was 0.06)
                satiation_rate=0.15,
                low_threshold=0.25,
                high_threshold=0.75
            )
        }
        
        # === 自適應參數（調整後）===
        self.params = {
            "curiosity_recovery_rate": 0.10,      # 降低 (was 0.15)
            "curiosity_recovery_threshold": 0.35, # 降低 (was 0.4)
            "fatigue_accumulation": 0.025,        # 降低 (was 0.03)
            "exploration_reward": 0.06,           # 略增 (was 0.05)
            "creation_reward": 0.10,              # 略增 (was 0.08)
            "repeat_penalty": -0.10,              # 加強 (was -0.08)
            
            # === 新增參數 ===
            "satiation_threshold": 0.75,  # 超過此值開始「滿足感衰減」
            "inhibition_strength": 0.5,   # 競爭抑制強度
        }
        
        # 參數範圍（安全限制）
        self.param_limits = {
            "curiosity_recovery_rate": (0.05, 0.3),
            "curiosity_recovery_threshold": (0.25, 0.5),
            "fatigue_accumulation": (0.01, 0.05),
            "exploration_reward": (0.03, 0.12),
            "creation_reward": (0.05, 0.15),
            "repeat_penalty": (-0.20, -0.05),
            "satiation_threshold": (0.65, 0.85),
            "inhibition_strength": (0.3, 0.7),
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
        
        # === 新增：連續極端值計數 ===
        self._extreme_counts = {
            "curiosity": 0,
            "fatigue": 0,
            "anxiety": 0,
            "satisfaction": 0
        }
        
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
            
            # === 追蹤極端值 ===
            if drive.value >= 0.95 or drive.value <= 0.05:
                self._extreme_counts[name] += 1
            else:
                self._extreme_counts[name] = 0
        
        # === 強制修正：連續極端值時的緊急調節 ===
        self._emergency_regulation()
        
        # === 競爭抑制 ===
        self._apply_inhibition()
        
        # 自然衰變
        for drive in self.drives.values():
            drive.tick()
        
        # 疲勞累積（使用自適應參數）
        self.drives["fatigue"].modify(
            self.params["fatigue_accumulation"],
            apply_diminishing=True
        )
        
        # === 好奇心自動恢復（改進版）===
        curiosity = self.drives["curiosity"]
        threshold = self.params["curiosity_recovery_threshold"]
        rate = self.params["curiosity_recovery_rate"]
        
        # 只在低於閾值時恢復，且應用邊際遞減
        if curiosity.value < threshold:
            gap = threshold - curiosity.value
            recovery = gap * rate
            curiosity.modify(recovery, apply_diminishing=False)  # 恢復不用遞減
        
        # === 移除這個！這是造成持續累加的元兇 ===
        # if curiosity.value < curiosity.baseline:
        #     curiosity.modify(0.02)
        
        # === 自適應調整（每 5 個心跳檢查一次）===
        if self._ticks % 5 == 0:
            self._self_adjust()
        
        self._check_critical()
        self._save()
    
    def _emergency_regulation(self):
        """
        緊急調節：當驅動力卡在極端值時強制修正
        """
        for name, count in self._extreme_counts.items():
            if count >= 3:  # 連續 3 個心跳卡在極端值
                drive = self.drives[name]
                
                if drive.value >= 0.95:
                    # 強制下拉
                    old_value = drive.value
                    drive.value = 0.75
                    
                    print(f"\n⚠️ [Emergency] {name} stuck at {old_value:.2f}, "
                          f"forced to {drive.value:.2f}")
                    
                    if self._events:
                        self._events.emit("homeostasis.emergency", {
                            "drive": name,
                            "old_value": old_value,
                            "new_value": drive.value,
                            "reason": "stuck_high"
                        }, source="AdaptiveHomeostasis")
                
                elif drive.value <= 0.05:
                    # 強制上推
                    old_value = drive.value
                    drive.value = 0.25
                    
                    print(f"\n⚠️ [Emergency] {name} stuck at {old_value:.2f}, "
                          f"forced to {drive.value:.2f}")
                
                self._extreme_counts[name] = 0
    
    def _apply_inhibition(self):
        """
        競爭抑制：驅動力之間的相互影響
        
        生物學原理：
        - 疲勞高 → 好奇心獎勵減半
        - 焦慮高 → 滿意度獎勵減半
        - 好奇心極高 → 輕微增加焦慮
        """
        strength = self.params["inhibition_strength"]
        
        # 疲勞抑制好奇心
        if self.drives["fatigue"].value > 0.6:
            inhibit = (self.drives["fatigue"].value - 0.6) * strength * 0.1
            self.drives["curiosity"].modify(-inhibit, apply_diminishing=False)
        
        # 焦慮抑制滿意度
        if self.drives["anxiety"].value > 0.5:
            inhibit = (self.drives["anxiety"].value - 0.5) * strength * 0.08
            self.drives["satisfaction"].modify(-inhibit, apply_diminishing=False)
        
        # 極高好奇心產生輕微焦慮（「太興奮」）
        if self.drives["curiosity"].value > 0.85:
            excess = (self.drives["curiosity"].value - 0.85) * 0.15
            self.drives["anxiety"].modify(excess, apply_diminishing=False)
    
    def _self_adjust(self):
        """
        自我調整參數（改進版）
        
        新增：檢測數值飽和問題
        """
        adjustments_made = []
        
        # === 檢測好奇心持續過高（新增）===
        if len(self.drive_history["curiosity"]) >= 8:
            recent = self.drive_history["curiosity"][-8:]
            avg = sum(recent) / len(recent)
            
            if avg > 0.85:
                # 好奇心持續過高，增強飽和衰減
                old_satiation = self.drives["curiosity"].satiation_rate
                new_satiation = min(old_satiation + 0.03, 0.25)
                
                if new_satiation != old_satiation:
                    self.drives["curiosity"].satiation_rate = new_satiation
                    adjustments_made.append({
                        "param": "curiosity.satiation_rate",
                        "old": old_satiation,
                        "new": new_satiation,
                        "reason": f"Curiosity stuck high (avg={avg:.2f})"
                    })
        
        # === 檢測滿意度持續過高（新增）===
        if len(self.drive_history["satisfaction"]) >= 8:
            recent = self.drive_history["satisfaction"][-8:]
            avg = sum(recent) / len(recent)
            
            if avg > 0.85:
                old_satiation = self.drives["satisfaction"].satiation_rate
                new_satiation = min(old_satiation + 0.03, 0.25)
                
                if new_satiation != old_satiation:
                    self.drives["satisfaction"].satiation_rate = new_satiation
                    adjustments_made.append({
                        "param": "satisfaction.satiation_rate",
                        "old": old_satiation,
                        "new": new_satiation,
                        "reason": f"Satisfaction stuck high (avg={avg:.2f})"
                    })
        
        # === 原有的調整邏輯 ===
        # 檢測好奇心長期過低
        if len(self.drive_history["curiosity"]) >= 10:
            recent = self.drive_history["curiosity"][-10:]
            avg = sum(recent) / len(recent)
            
            if avg < 0.2:
                old_rate = self.params["curiosity_recovery_rate"]
                new_rate = min(
                    old_rate + 0.03,
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
        
        # 檢測疲勞累積過快
        if len(self.drive_history["fatigue"]) >= 5:
            recent = self.drive_history["fatigue"][-5:]
            
            if recent[0] < 0.3 and recent[-1] > 0.70:
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
        
        # 檢測滿意度長期過低
        if len(self.drive_history["satisfaction"]) >= 10:
            recent = self.drive_history["satisfaction"][-10:]
            avg = sum(recent) / len(recent)
            
            if avg < 0.25:
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
            
            # 只保留最近 50 條記錄
            if len(self.adjustments_log) > 50:
                self.adjustments_log = self.adjustments_log[-50:]
            
            print("\n" + "="*60)
            print("🔧 SELF-ADJUSTMENT TRIGGERED")
            print("="*60)
            for adj in adjustments_made:
                print(f"[Adaptive] {adj['param']}: {adj['old']:.3f} → {adj['new']:.3f}")
                print(f"  Reason: {adj['reason']}")
            print("="*60 + "\n")
            
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
        
        count = 0
        if context and isinstance(context, dict):
            count = context.get("read_count", 0)
            if count == 0:
                count = context.get("visit_count", 0)
        
        self._process_action(action, success, count)
        
        diversity = self.get_diversity()
        if diversity < 0.3:
            self.drives["curiosity"].modify(-0.05)  # 加強懲罰
        
        self._save()
    
    def _process_action(self, action: str, success: bool, count: int = 0):
        """根據具體行為調整驅動力（使用邊際遞減）"""
        
        # === 計算抑制因子 ===
        fatigue_inhibit = 1.0
        if self.drives["fatigue"].value > 0.5:
            # 疲勞時獎勵減半
            fatigue_inhibit = 1.0 - (self.drives["fatigue"].value - 0.5) * self.params["inhibition_strength"]
            fatigue_inhibit = max(0.3, fatigue_inhibit)
        
        # 探索類行為
        if action in ["browse", "read_file", "recall", "search"]:
            if success:
                if count >= 3:
                    penalty = self.params["repeat_penalty"] * 1.5
                    self.drives["curiosity"].modify(penalty)
                    self.drives["satisfaction"].modify(penalty * 0.5)
                    self.drives["anxiety"].modify(0.06)
                elif count >= 2:
                    penalty = self.params["repeat_penalty"]
                    self.drives["curiosity"].modify(penalty)
                    self.drives["satisfaction"].modify(penalty * 0.3)
                elif count == 1:
                    self.drives["curiosity"].modify(-0.04)
                else:
                    # 首次探索（應用抑制因子和邊際遞減）
                    reward = self.params["exploration_reward"] * fatigue_inhibit
                    self.drives["curiosity"].modify(reward)  # 自動應用邊際遞減
                    self.drives["satisfaction"].modify(reward * 0.5)
            
            self.drives["fatigue"].modify(0.02)
        
        # 創造類行為
        elif action in ["write_file", "execute_python", "remember"]:
            if success:
                reward = self.params["creation_reward"] * fatigue_inhibit
                self.drives["satisfaction"].modify(reward)
                self.drives["curiosity"].modify(reward * 0.3)  # 降低對好奇心的影響
            self.drives["fatigue"].modify(0.03)
        
        # 反思類行為
        elif action in ["learn_rule", "update_state"]:
            self.drives["anxiety"].modify(-0.10)
            self.drives["curiosity"].modify(0.02)
            self.drives["fatigue"].modify(0.01)
        
        # 失敗處理
        if not success:
            self.drives["anxiety"].modify(0.06)
            self.drives["satisfaction"].modify(-0.04)
    
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
        
        if fatigue > 0.80:
            return "rest"
        if anxiety > 0.65:
            return "reflect"
        if curiosity > 0.7 and fatigue < 0.5:
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
        self.drives["fatigue"].modify(-0.5, apply_diminishing=False)
        self.drives["anxiety"].modify(-0.2, apply_diminishing=False)
        self.drives["curiosity"].modify(0.15, apply_diminishing=True)
        self.drives["satisfaction"].modify(0.1, apply_diminishing=True)
        self._save()
    
    def should_dream(self) -> bool:
        """是否應該進入夢境狀態"""
        return self.drives["fatigue"].value > 0.80  # 降低閾值
    
    def get_drive_history(self) -> dict:
        """獲取驅動力歷史（供夢境分析用）"""
        return self.drive_history.copy()
    
    def get_adjustments_log(self) -> list:
        """獲取調整歷史"""
        return self.adjustments_log.copy()
    
    def reset_to_baseline(self):
        """
        重置所有驅動力到 baseline（調試用）
        """
        for name, drive in self.drives.items():
            drive.value = drive.baseline
        
        self._extreme_counts = {name: 0 for name in self.drives}
        print("🔄 All drives reset to baseline")
        self._save()
    
    def _save(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "drives": {
                name: {
                    "value": drive.value,
                    "baseline": drive.baseline,
                    "decay_rate": drive.decay_rate,
                    "satiation_rate": drive.satiation_rate,
                }
                for name, drive in self.drives.items()
            },
            "params": self.params,
            "drive_history": self.drive_history,
            "adjustments_log": self.adjustments_log,
            "recent_actions": self._recent_actions,
            "extreme_counts": self._extreme_counts,
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
            
            for name, info in data.get("drives", {}).items():
                if name in self.drives:
                    self.drives[name].value = info.get("value", self.drives[name].value)
                    if "satiation_rate" in info:
                        self.drives[name].satiation_rate = info["satiation_rate"]
            
            if "params" in data:
                for key, value in data["params"].items():
                    if key in self.params:
                        self.params[key] = value
            
            if "drive_history" in data:
                self.drive_history = data["drive_history"]
            
            if "adjustments_log" in data:
                self.adjustments_log = data["adjustments_log"]
            
            if "extreme_counts" in data:
                self._extreme_counts = data["extreme_counts"]
            
            self._recent_actions = data.get("recent_actions", [])
            self._ticks = data.get("ticks", 0)
            
        except Exception:
            pass


# 向後兼容別名
Homeostasis = AdaptiveHomeostasis
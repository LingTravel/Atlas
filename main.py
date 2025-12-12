"""
Atlas - 主程序

心跳循環：
1. 醒來（構建 prompt）
2. 思考（調用 Gemini）
3. 行動（執行工具）
4. 記憶（存儲經驗）
5. 休眠（檢查是否需要做夢）
"""

import os
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types

from core.brain import Brain
from core.events import Event


# ============================================================
# 配置
# ============================================================

ATLAS_ROOT = Path(__file__).parent.resolve()
GEMINI_MODEL = "gemini-2.0-flash"
HEARTBEAT_INTERVAL = 60  # 秒


# ============================================================
# Prompt 構建
# ============================================================

def build_wake_prompt(brain: Brain) -> str:
    """構建醒來時的 prompt"""
    is_first = brain.state.is_first_boot()
    hb_num = brain.state.lifecycle.total_heartbeats + 1
    
    parts = []
    
    # ===== 頭部 =====
    if is_first:
        parts.append("# 🌅 First Awakening\n")
        parts.append("I am waking up for the first time.\n\n")
        
        if brain.prompts.get('origin'):
            parts.append("## My Origin\n")
            parts.append(brain.prompts['origin'])
            parts.append("\n\n---\n\n")
        
        if brain.prompts.get('inherited'):
            parts.append("## Inherited Message\n")
            parts.append(brain.prompts['inherited'])
            parts.append("\n\n---\n\n")
    else:
        parts.append(f"# Heartbeat {hb_num}\n\n")
        parts.append("I am waking up.\n\n")
    
    # ===== 狀態摘要 =====
    parts.append("## My Current State\n")
    parts.append(brain.state.get_summary())
    parts.append("\n\n")
    
    # ===== 內在驅動力 =====
    parts.append(brain.homeostasis.get_prompt_injection())
    parts.append("\n\n")
    
    # ===== 已讀文件 (新增) =====
    files_read_str = brain.memory.working.get_files_read_string()
    if files_read_str:
        parts.append(files_read_str)
        parts.append("\n\n")
    
    # ===== 記憶 =====
    memory_context = brain.memory.get_context_for_prompt()
    if memory_context:
        parts.append("## What I Remember\n")
        parts.append(memory_context)
        parts.append("\n\n")
    
    # ===== 工具提示 =====
    if is_first or hb_num % 10 == 1:
        parts.append("## What I Can Do\n")
        parts.append("- `read_file`: Read files or list directories (use `.` for current dir)\n")
        parts.append("- `write_file`: Write to files (I should use workspace/)\n")
        parts.append("- `execute_python`: Run Python code\n")
        parts.append("- `browse`: Browse the web — I can **SEE** pages with action='see'\n")
        parts.append("- `remember`: Store important events in my memory\n")
        parts.append("- `recall`: Search my episodic memories\n")
        parts.append("- `learn_rule`: Add a rule to my knowledge\n")
        parts.append("- `update_state`: Update what I'm doing\n")
        parts.append("- `done`: End this heartbeat\n")
        parts.append("\n")
    
    # ===== 規則 (新增) =====
    parts.append("## Rules I Must Follow\n")
    parts.append("1. **No re-reading**: Files marked 🚫 or ⚠️ must NOT be read again\n")
    parts.append("2. **Execute plans**: If I write a plan/experiment, I MUST execute it\n")
    parts.append("3. **Create over consume**: Writing new things > Reading old things\n")
    parts.append("4. **Diversify**: Try different tools, not just read_file repeatedly\n")
    parts.append("\n")
    
    # ===== 指示 =====
    parts.append("---\n\n")
    parts.append("**I think in first person. This is my inner monologue.**\n\n")
    parts.append("**When I'm finished, I call `done` with my thoughts.**\n")
    
    return "".join(parts)


# ============================================================
# 工具註冊為 Gemini Functions
# ============================================================

def create_tool_functions(brain: Brain) -> list:
    """
    從 ToolRegistry 創建 Gemini function calling 定義
    並添加記憶工具
    """
    # 從 registry 獲取工具定義
    definitions = brain.tools.get_definitions()
    
    # 添加記憶工具
    definitions.extend([
        {
            "name": "remember",
            "description": "Store an important event in episodic memory. Use for significant experiences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event": {
                        "type": "string",
                        "description": "What happened"
                    },
                    "outcome": {
                        "type": "string",
                        "description": "The result or lesson"
                    },
                    "importance": {
                        "type": "integer",
                        "description": "How important (1-10)"
                    }
                },
                "required": ["event", "outcome"]
            }
        },
        {
            "name": "recall",
            "description": "Search your episodic memories for relevant past experiences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What you're trying to remember"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "learn_rule",
            "description": "Add a rule or principle to your semantic memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule": {
                        "type": "string",
                        "description": "The rule or principle"
                    }
                },
                "required": ["rule"]
            }
        },
        {
            "name": "update_state",
            "description": "Update your current state (task, goal, mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["idle", "exploring", "working", "reflecting", "creating"],
                        "description": "Current mode"
                    },
                    "task": {
                        "type": "string",
                        "description": "What you're doing"
                    },
                    "goal": {
                        "type": "string",
                        "description": "What you want to achieve"
                    }
                }
            }
        },
        {
            "name": "done",
            "description": "Signal that you're done with this heartbeat. Required to end.",
            "parameters": {
                "type": "object",
                "properties": {
                    "thoughts": {
                        "type": "string",
                        "description": "Your thoughts/summary of this heartbeat"
                    }
                },
                "required": ["thoughts"]
            }
        }
    ])
    
    return definitions


# ============================================================
# 工具執行
# ============================================================

def execute_tool(brain: Brain, name: str, args: dict) -> dict:
    """執行工具並返回結果"""
    import json
    
    # 特殊處理：記憶相關工具
    if name == "remember":
        event_id = brain.memory.remember(
            event=args.get("event", ""),
            outcome=args.get("outcome", ""),
            importance=args.get("importance", 5),
            context={
                "heartbeat": brain.state.lifecycle.total_heartbeats,
                "mode": brain.state.current.mode
            }
        )
        return {
            "success": True,
            "event_id": event_id,
            "message": "Memory stored"
        }
    
    elif name == "recall":
        bundle = brain.memory.recall(args.get("query", ""), n=5)
        return {
            "success": True,
            "memories": [
                {
                    "content": m.get("content", "")[:200],
                    "metadata": m.get("metadata", {})
                }
                for m in bundle.episodic
            ]
        }
    
    elif name == "learn_rule":
        success = brain.memory.learn_rule(
            args.get("rule", ""),
            source="self"
        )
        # 通知 homeostasis
        brain.homeostasis.on_action("learn_rule", success=True)
        return {
            "success": success,
            "message": "Rule learned" if success else "Rule already exists"
        }
    
    elif name == "update_state":
        brain.state.update_current(
            mode=args.get("mode"),
            task=args.get("task"),
            goal=args.get("goal")
        )
        brain.homeostasis.on_action("update_state", success=True)
        return {
            "success": True,
            "message": "State updated"
        }
    
    elif name == "done":
        return {
            "success": True,
            "done": True,
            "thoughts": args.get("thoughts", "")
        }
    
    # 從 registry 執行
    else:
        result = brain.tools.execute(name, **args)
        
        # === 新增：read_file 特殊處理 ===
        if name == "read_file":
            path = args.get("path", "")
            read_count = brain.memory.working.get_read_count(path)
            
            # 標記已讀
            brain.memory.working.mark_read(path)
            
            # 通知 homeostasis（帶 read_count）
            brain.homeostasis.on_action(
                "read_file",
                success=result.success,
                context={"read_count": read_count}
            )
        
        # 其他工具的一般處理
        elif name in ["write_file", "execute_python"]:
            brain.homeostasis.on_action(name, success=result.success)
        
        elif name == "browse":
            brain.homeostasis.on_action("browse", success=result.success)
        # ================================
        
        return result.to_json()


# ============================================================
# 心跳循環
# ============================================================

def run_heartbeat(brain: Brain) -> dict:
    """
    執行一次心跳
    
    Returns:
        心跳報告
    """
    # 記錄心跳
    hb_num = brain.state.heartbeat()
    
    print("\n" + "="*60)
    print(f"💓 HEARTBEAT {hb_num}")
    print("="*60)
    
    brain.events.emit("heartbeat.start", {"number": hb_num}, source="main")
    
    # 構建 prompt
    wake_prompt = build_wake_prompt(brain)
    
    # 準備對話
    conversation = [
        {"role": "user", "parts": [{"text": wake_prompt}]}
    ]
    
    # 標記首次啟動已讀
    if brain.state.is_first_boot():
        brain.state.set_flag("first_boot", False)
        brain.state.set_flag("inherited_message_read", True)
    
    # 執行循環
    actions_log = []
    thoughts = ""
    done = False
    max_turns = 15
    turn = 0
    
    # 準備工具
    tool_defs = create_tool_functions(brain)
    tools = types.Tool(function_declarations=tool_defs)
    config = types.GenerateContentConfig(tools=[tools])
    
    while not done and turn < max_turns:
        turn += 1
        
        try:
            # 調用 Gemini
            response = brain.llm.models.generate_content(
                model=GEMINI_MODEL,
                contents=conversation,
                config=config
            )
            
            # 處理回應
            if not response.candidates or not response.candidates[0].content.parts:
                print("[Warning] Empty response from model")
                break
            
            for part in response.candidates[0].content.parts:
                # 文字回應
                if hasattr(part, 'text') and part.text:
                    print(f"\n[Atlas]: {part.text}")
                
                # 工具調用
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    tool_name = fc.name
                    tool_args = dict(fc.args)
                    
                    print(f"\n[Tool]: {tool_name}")
                    print(f"[Args]: {tool_args}")
                    
                    # 執行工具
                    result = execute_tool(brain, tool_name, tool_args)
                    
                    # 檢查是否結束
                    if result.get("done"):
                        done = True
                        thoughts = result.get("thoughts", "")
                    
                    # 處理視覺數據
                    result_str = str(result)[:500]
                    
                    # 如果有圖像數據，注入到對話
                    if result.get("metadata", {}).get("has_image"):
                        image_data = result.get("data", {}).get("image_base64")
                        if image_data:
                            # 添加 function call 到對話
                            conversation.append({
                                "role": "model",
                                "parts": [{"function_call": fc}]
                            })
                            
                            # 添加圖像
                            conversation.append({
                                "role": "user",
                                "parts": [
                                    {
                                        "inline_data": {
                                            "mime_type": "image/png",
                                            "data": image_data
                                        }
                                    },
                                    {
                                        "text": f"[You are now SEEING this webpage. The image shows what's currently displayed.]"
                                    }
                                ]
                            })
                            
                            print(f"[Result]: Visual data captured")
                            
                            actions_log.append({
                                "tool": tool_name,
                                "args": tool_args,
                                "result": "Visual data processed"
                            })
                            
                            continue  # 跳過正常的 function_response
                    
                    print(f"[Result]: {result_str}...")
                    
                    # 記錄
                    actions_log.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result_str
                    })
                    
                    # 添加到對話
                    conversation.append({
                        "role": "model",
                        "parts": [{"function_call": fc}]
                    })
                    conversation.append({
                        "role": "user",
                        "parts": [{
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": result_str}
                            }
                        }]
                    })
        
        except Exception as e:
            error_msg = str(e)
            print(f"\n[Error]: {error_msg[:200]}")
            
            # Rate limit 處理
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                print("[Waiting 60s due to rate limit...]")
                time.sleep(60)
                continue
            else:
                print("[Ending heartbeat due to error]")
                break
    
    # 存入工作記憶
    brain.memory.add_heartbeat(
        heartbeat=hb_num,
        thoughts=thoughts,
        actions=actions_log,
        summary=thoughts[:100] if thoughts else f"{len(actions_log)} actions taken"
    )
    
    # 更新驅動力
    brain.homeostasis.tick()
    
    # 事件
    brain.events.emit("heartbeat.end", {
        "number": hb_num,
        "actions": len(actions_log),
        "thoughts": thoughts[:50]
    }, source="main")
    
    print(f"\n[Heartbeat {hb_num} complete]")
    print(f"[Thoughts]: {thoughts}")
    
    # 檢查是否需要做夢
    if brain.homeostasis.should_dream():
        print("\n[Fatigue critical - entering dream state...]")
        brain.dreaming.dream(depth="light")
        brain.state.dream()
    
    return {
        "heartbeat": hb_num,
        "thoughts": thoughts,
        "actions": len(actions_log)
    }


# ============================================================
# 主函數
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Run Atlas")
    parser.add_argument(
        "-n", "--heartbeats",
        type=int,
        default=1,
        help="Number of heartbeats to run"
    )
    parser.add_argument(
        "--infinite",
        action="store_true",
        help="Run indefinitely"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=HEARTBEAT_INTERVAL,
        help="Seconds between heartbeats"
    )
    
    args = parser.parse_args()
    
    # 檢查 API key
    if "GEMINI_API_KEY" not in os.environ:
        print("Error: GEMINI_API_KEY not set")
        print("Set it with: export GEMINI_API_KEY=your_key")
        sys.exit(1)
    
    # 初始化 Brain
    print("\n" + "="*60)
    print("🧠 ATLAS AWAKENING")
    print("="*60)
    
    brain = Brain(root_path=ATLAS_ROOT)
    
    # 顯示統計
    stats = brain.get_statistics()
    print(f"\nState: Heartbeat #{stats['state']['lifecycle']['total_heartbeats']}")
    print(f"Memory: {stats['memory']['episodic']['total_episodes']} episodes, "
          f"{stats['memory']['semantic']['rules']} rules")
    print(f"Tools: {stats['tools']['count']} registered")
    
    # 運行
    count = 0
    n_heartbeats = None if args.infinite else args.heartbeats
    
    try:
        while n_heartbeats is None or count < n_heartbeats:
            run_heartbeat(brain)
            count += 1
            
            if n_heartbeats is None or count < n_heartbeats:
                print(f"\n[Sleeping for {args.interval} seconds...]")
                time.sleep(args.interval)
        
    except KeyboardInterrupt:
        print("\n\n[Atlas interrupted by user]")
    
    # 最終統計
    print("\n" + "="*60)
    print(f"Atlas completed {count} heartbeats")
    
    final_stats = brain.get_statistics()
    print(f"Final state: {final_stats['state']['current']['mode']}")
    print(f"Drives: {brain.homeostasis.get_state()}")
    print("="*60 + "\n")
    
    # 導出追蹤
    trace_file = ATLAS_ROOT / "data" / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    brain.events.export_trace(str(trace_file))
    print(f"Event trace saved to: {trace_file}")


if __name__ == "__main__":
    main()
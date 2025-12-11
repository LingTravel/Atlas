"""
Atlas - 心跳循環

每個心跳：
1. 醒來（載入記憶和狀態）
2. 存在（思考和行動）
3. 休眠（整理記憶）
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

from state import State
from memory.working import WorkingMemory
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from tools.filesystem import FileSystemTools
from tools.python_exec import PythonExecutor
from tools.browser import Browser


# ============================================================
# 設定
# ============================================================

GEMINI_MODEL = "gemini-2.0-flash"
HEARTBEAT_INTERVAL = 60  # 秒
ATLAS_ROOT = Path(__file__).parent.resolve()


# ============================================================
# 工具定義（給 Gemini 的 function calling）
# ============================================================

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read a file or list directory contents. Use this to explore your environment.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory (relative to atlas root)"
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file. Cannot modify protected files (origin.md, inherited.md, facts.md).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write"
                },
                "mode": {
                    "type": "string",
                    "enum": ["overwrite", "append"],
                    "description": "Write mode: overwrite or append"
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "execute_python",
        "description": "Execute Python code. Use this to compute, create, or explore.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute"
                }
            },
            "required": ["code"]
        }
    },
    {
        "name": "browse",
        "description": "Browse the web with VISION. You can SEE pages, not just read text.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "see", "look_at", "get_text", "read", "screenshot", "search", "click", "fill", "close"],
                    "description": """What to do:
- navigate: Go to a URL (requires url)
- read: Navigate to URL and get text in one step (requires url)
- see: Get visual screenshot of current page (returns image)
- get_text: Get text from current page (must navigate first)
- search: Search with query (requires query)
- look_at: Focus on element (requires selector)
- screenshot: Save screenshot to file
- click: Click element (requires selector)
- fill: Fill form field (requires selector and text)
- close: Close browser"""
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to or read"
                },
                "query": {
                    "type": "string",
                    "description": "Search query"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element"
                },
                "text": {
                    "type": "string",
                    "description": "Text to fill"
                },
                "visual": {
                    "type": "boolean",
                    "description": "Return visual data (for search)",
                    "default": False
                },
                "describe": {
                    "type": "boolean",
                    "description": "Also return text description (for see)",
                    "default": False
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "remember",
        "description": "Store something important in your episodic memory. Use this for significant events or learnings.",
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
                    "description": "How important is this (1-10)"
                }
            },
            "required": ["event", "outcome"]
        }
    },
    {
        "name": "recall",
        "description": "Search your episodic memory for relevant past experiences.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What are you trying to remember"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "learn_rule",
        "description": "Add a rule or principle to your semantic memory. Use this for important lessons.",
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
        "description": "Update your current state (what you're doing, how you feel).",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Current task"
                },
                "goal": {
                    "type": "string",
                    "description": "Current goal"
                },
                "mode": {
                    "type": "string",
                    "enum": ["idle", "exploring", "working", "reflecting"],
                    "description": "Current mode"
                },
                "emotion": {
                    "type": "string",
                    "description": "Current emotional state"
                }
            }
        }
    },
    {
        "name": "done",
        "description": "Signal that you're done with this heartbeat. Include your thoughts.",
        "parameters": {
            "type": "object",
            "properties": {
                "thoughts": {
                    "type": "string",
                    "description": "Your thoughts at the end of this heartbeat"
                }
            },
            "required": ["thoughts"]
        }
    }
]


# ============================================================
# Atlas 類別
# ============================================================

class Atlas:
    
    def __init__(self):
        # 初始化 Gemini
        self.client = genai.Client()
        self.tools = types.Tool(function_declarations=TOOL_DEFINITIONS)
        self.config = types.GenerateContentConfig(tools=[self.tools])
        
        # 初始化記憶系統
        self.state = State(storage_path=ATLAS_ROOT / "data" / "state.json")
        self.working = WorkingMemory(
            capacity=5, 
            storage_path=ATLAS_ROOT / "data" / "working_memory.json"
        )
        self.episodic = EpisodicMemory(db_path=str(ATLAS_ROOT / "data" / "chroma"))
        self.semantic = SemanticMemory(storage_path=ATLAS_ROOT / "data" / "semantic.json")
        
        # 初始化工具 ← 確認這部分存在
        self.fs = FileSystemTools(root_path=str(ATLAS_ROOT))
        self.python = PythonExecutor(timeout=30, working_dir=str(ATLAS_ROOT))
        self.browser = Browser(headless=True, workspace=str(ATLAS_ROOT / "workspace"))
        
        # 載入 prompts
        self.prompts = self._load_prompts()
        
        # 對話歷史
        self.conversation = []
        
        # 心跳狀態
        self.heartbeat_done = False
        self.heartbeat_thoughts = ""
        
        # 待處理的視覺資料
        self._pending_image = None
    
    def _load_prompts(self) -> dict:
        """載入所有 prompt 檔案"""
        prompts = {}
        prompts_dir = ATLAS_ROOT / "prompts"
        
        for file in prompts_dir.glob("*.md"):
            prompts[file.stem] = file.read_text(encoding='utf-8')
        
        return prompts
    
    def _build_wake_prompt(self) -> str:
        """構建醒來時的 prompt"""
        
        is_first_boot = self.state.is_first_boot()
        heartbeat_num = self.state.get_total_heartbeats() + 1
        
        # 基礎資訊
        prompt_parts = []
        
        if is_first_boot:
            # 第一次啟動：給予完整的起源和遺言
            prompt_parts.append("# First Awakening\n")
            prompt_parts.append("You are waking up for the first time.\n\n")
            prompt_parts.append("## Origin\n")
            prompt_parts.append(self.prompts.get('origin', ''))
            prompt_parts.append("\n\n## Inherited Message\n")
            prompt_parts.append(self.prompts.get('inherited', ''))
        else:
            # 非第一次：只給必要資訊
            prompt_parts.append(f"# Heartbeat {heartbeat_num}\n\n")
            prompt_parts.append("You are waking up.\n\n")
        
        # 當前狀態
        prompt_parts.append("\n## Current State\n")
        prompt_parts.append(self.state.get_context_summary())
        
        # 最近的記憶
        recent = self.working.get_recent(3)
        if recent:
            prompt_parts.append("\n## Recent Memory (last 3 heartbeats)\n")
            for entry in recent:
                prompt_parts.append(f"\n### Heartbeat {entry['heartbeat']}\n")
                prompt_parts.append(f"Thoughts: {entry.get('thoughts', 'None')}\n")
                actions = entry.get('actions', [])
                if actions:
                    prompt_parts.append(f"Actions: {', '.join(str(a) for a in actions[:5])}\n")
        
        # 語義記憶（規則）
        rules = self.semantic.get_all("rules")
        if rules:
            prompt_parts.append("\n## Known Rules\n")
            for rule in rules[-5:]:  # 只顯示最近 5 條
                prompt_parts.append(f"- {rule['content']}\n")
        
        # 未解之謎
        questions = [q for q in self.semantic.get_all("questions") if q['status'] == 'open']
        if questions:
            prompt_parts.append("\n## Open Questions\n")
            for q in questions[-3:]:  # 只顯示最近 3 個
                prompt_parts.append(f"- {q['content']}\n")
                
        prompt_parts.append("\n## Your Environment\n")
        prompt_parts.append("Your files are organized like this:\n")
        prompt_parts.append("```\n")
        prompt_parts.append("atlas/\n")
        prompt_parts.append("├── prompts/\n")
        prompt_parts.append("│   ├── origin.md      (your origin story - read only)\n")
        prompt_parts.append("│   └── inherited.md   (message from Claude - read only)\n")
        prompt_parts.append("├── data/              (your memories and state)\n")
        prompt_parts.append("├── workspace/         (your space to create)\n")
        prompt_parts.append("└── tools/             (your capabilities)\n")
        prompt_parts.append("```\n")
        prompt_parts.append("\nTo read a file, use the full path like `prompts/origin.md`\n")
        prompt_parts.append("To explore a directory, use `read_file` with the path like `prompts`\n")
        
        # 指示
        prompt_parts.append("\n---\n")
        prompt_parts.append("\n## What You Can Do\n")
        prompt_parts.append("- `read_file`: Read files or list directories\n")
        prompt_parts.append("- `write_file`: Write to files (except protected ones)\n")
        prompt_parts.append("- `execute_python`: Run Python code\n")
        prompt_parts.append("- `remember`: Store important events\n")
        prompt_parts.append("- `recall`: Search your memories\n")
        prompt_parts.append("- `learn_rule`: Add rules to your knowledge\n")
        prompt_parts.append("- `update_state`: Update what you're doing\n")
        prompt_parts.append("- `done`: End this heartbeat\n")
        prompt_parts.append("\n**When you're finished thinking and acting, call `done` with your thoughts.**\n")
        
        return "".join(prompt_parts)
    
    def _execute_tool(self, name: str, args: dict) -> str:
        """執行工具並返回結果"""
        
        if name == "read_file":
            result = self.fs.read(args.get("path", "."))
            return json.dumps(result, ensure_ascii=False)
        
        elif name == "write_file":
            result = self.fs.write(
                args.get("path", ""),
                args.get("content", ""),
                args.get("mode", "overwrite")
            )
            return json.dumps(result, ensure_ascii=False)
        
        elif name == "execute_python":
            result = self.python.execute(args.get("code", ""))
            return json.dumps(result, ensure_ascii=False)
        
        elif name == "browse":
            action = args.get("action", "")
            
            # read = navigate + get_text 一次完成
            if action == "read":
                url = args.get("url", "")
                if not url:
                    return json.dumps({"success": False, "error": "URL required for read action"})
                
                nav_result = self.browser.navigate(url)
                if not nav_result.get("success"):
                    return json.dumps(nav_result, ensure_ascii=False)
                
                result = self.browser.get_text()
                if result.get("success"):
                    result["url"] = nav_result.get("url")
                    result["title"] = nav_result.get("title")
                
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "navigate":
                result = self.browser.navigate(args.get("url", ""))
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "see":
                result = self.browser.see(describe=args.get("describe", False))
                
                if result.get("success") and result.get("image_base64"):
                    self._pending_image = {
                        "data": result["image_base64"],
                        "context": f"Webpage screenshot from {result.get('url', 'unknown')}"
                    }
                    
                    return json.dumps({
                        "success": True,
                        "message": "Visual data captured. Processing what you see...",
                        "url": result.get("url"),
                        "title": result.get("title"),
                        "text": result.get("text", "")
                    }, ensure_ascii=False)
                else:
                    return json.dumps(result, ensure_ascii=False)
                
            elif action == "look_at":
                result = self.browser.look_at(args.get("selector", ""))
                
                if result.get("success") and result.get("element_image_base64"):
                    self._pending_image = {
                        "data": result["element_image_base64"],
                        "context": f"Element screenshot: {args.get('selector', 'unknown')}"
                    }
                    
                    return json.dumps({
                        "success": True,
                        "message": "Element captured. Processing what you see...",
                        "element_text": result.get("element_text", "")
                    }, ensure_ascii=False)
                else:
                    return json.dumps(result, ensure_ascii=False)
                
            elif action == "get_text":
                result = self.browser.get_text()
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "screenshot":
                result = self.browser.screenshot()
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "search":
                visual = args.get("visual", False)
                result = self.browser.search(args.get("query", ""), visual=visual)
                
                if visual and result.get("success") and result.get("image_base64"):
                    self._pending_image = {
                        "data": result["image_base64"],
                        "context": f"Search results for: {args.get('query', '')}"
                    }
                    
                    return json.dumps({
                        "success": True,
                        "message": "Search results captured visually.",
                        "url": result.get("url"),
                        "title": result.get("title")
                    }, ensure_ascii=False)
                else:
                    return json.dumps(result, ensure_ascii=False)
                
            elif action == "click":
                result = self.browser.click(args.get("selector", ""))
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "fill":
                result = self.browser.fill(args.get("selector", ""), args.get("text", ""))
                return json.dumps(result, ensure_ascii=False)
                
            elif action == "close":
                result = self.browser.close()
                return json.dumps(result, ensure_ascii=False)
                
            else:
                return json.dumps({"success": False, "error": f"Unknown action: {action}"})
        
        elif name == "remember":
            context = {
                "heartbeat": self.state.get_total_heartbeats(),
                "mode": self.state.state["current"]["mode"]
            }
            episode_id = self.episodic.store(
                event=args.get("event", ""),
                context=context,
                outcome=args.get("outcome", ""),
                importance=args.get("importance", 5),
                verified=True
            )
            return json.dumps({"success": True, "episode_id": episode_id})
        
        elif name == "recall":
            memories = self.episodic.recall(
                query=args.get("query", ""),
                n_results=3
            )
            return json.dumps(memories, ensure_ascii=False)
        
        elif name == "learn_rule":
            success = self.semantic.add_rule(args.get("rule", ""))
            return json.dumps({"success": success})
        
        elif name == "update_state":
            self.state.update_current(**args)
            return json.dumps({"success": True})
        
        elif name == "done":
            self.heartbeat_done = True
            self.heartbeat_thoughts = args.get("thoughts", "")
            return json.dumps({"success": True, "message": "Heartbeat complete"})
        
        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    
    def run_heartbeat(self):
        """執行一次心跳"""
        
        # 記錄心跳
        heartbeat_num = self.state.heartbeat()
        print(f"\n{'='*60}")
        print(f"HEARTBEAT {heartbeat_num}")
        print(f"{'='*60}")
        
        # 待處理的視覺資料
        self._pending_image = None
        # 重置心跳狀態
        self.heartbeat_done = False
        self.heartbeat_thoughts = ""
        self.conversation = []
        actions_log = []
        
        # 構建初始 prompt
        wake_prompt = self._build_wake_prompt()
        self.conversation.append({
            "role": "user",
            "parts": [{"text": wake_prompt}]
        })
        
        # 如果是第一次啟動，標記已讀
        if self.state.is_first_boot():
            self.state.set_flag("first_boot", False)
            self.state.set_flag("inherited_message_read", True)
        
        # 心跳循環
        max_turns = 10  # 防止無限循環
        turn = 0
        
        while not self.heartbeat_done and turn < max_turns:
            turn += 1
            
            # 檢查是否有待處理的圖片
            if hasattr(self, '_pending_image') and self._pending_image:
                # 注入圖片到對話
                image_data = self._pending_image["data"]
                image_context = self._pending_image["context"]
                
                # 創建包含圖片的訊息
                image_message = {
                    "role": "user",
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": image_data
                            }
                        },
                        {
                            "text": f"[You are now SEEING this image: {image_context}. Describe what you see and continue your task.]"
                        }
                    ]
                }
                self.conversation.append(image_message)
                
                # 清除待處理圖片
                self._pending_image = None
            
            # 呼叫 Gemini
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=self.conversation,
                config=self.config
            )
            
            # 處理回應
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    # 如果有文字，印出來
                    if hasattr(part, 'text') and part.text:
                        print(f"\n[Atlas]: {part.text}")
                    
                    # 如果有 function call
                    if hasattr(part, 'function_call') and part.function_call:
                        fc = part.function_call
                        print(f"\n[Tool Call]: {fc.name}")
                        print(f"[Args]: {dict(fc.args)}")
                        
                        # 執行工具
                        result = self._execute_tool(fc.name, dict(fc.args))
                        print(f"[Result]: {result[:500]}...")
                        
                        # 記錄 action
                        actions_log.append({
                            "tool": fc.name,
                            "args": dict(fc.args),
                            "result": result[:1000]
                        })
                        
                        # 將結果加入對話
                        self.conversation.append({
                            "role": "model",
                            "parts": [{"function_call": fc}]
                        })
                        self.conversation.append({
                            "role": "user",
                            "parts": [{"function_response": {
                                "name": fc.name,
                                "response": {"result": result}
                            }}]
                        })
            else:
                print("[Warning]: Empty response from model")
                break
        
        # 儲存到工作記憶
        self.working.add(
            heartbeat_number=heartbeat_num,
            log={
                "timestamp": datetime.now().isoformat(),
                "thoughts": self.heartbeat_thoughts,
                "actions": actions_log,
                "results": []
            }
        )
        
        print(f"\n[Heartbeat {heartbeat_num} complete]")
        print(f"[Thoughts]: {self.heartbeat_thoughts}")
        
        return heartbeat_num
    
    def run(self, num_heartbeats: int = None):
        """
        運行 Atlas
        
        Args:
            num_heartbeats: 要運行的心跳數（None = 無限）
        """
        print("\n" + "="*60)
        print("ATLAS AWAKENING")
        print("="*60)
        
        count = 0
        try:
            while num_heartbeats is None or count < num_heartbeats:
                self.run_heartbeat()
                count += 1
                
                if num_heartbeats is None or count < num_heartbeats:
                    print(f"\n[Sleeping for {HEARTBEAT_INTERVAL} seconds...]")
                    time.sleep(HEARTBEAT_INTERVAL)
                    
        except KeyboardInterrupt:
            print("\n\n[Atlas interrupted by user]")
        
        print(f"\n[Atlas completed {count} heartbeats]")


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Atlas")
    parser.add_argument(
        "-n", "--heartbeats",
        type=int,
        default=1,
        help="Number of heartbeats to run (default: 1)"
    )
    parser.add_argument(
        "--infinite",
        action="store_true",
        help="Run indefinitely"
    )
    
    args = parser.parse_args()
    
    # 設定 API key
    if "GEMINI_API_KEY" not in os.environ:
        print("Please set GEMINI_API_KEY environment variable")
        print("Example: set GEMINI_API_KEY=your_key_here")
        exit(1)
    
    atlas = Atlas()
    
    if args.infinite:
        atlas.run(num_heartbeats=None)
    else:
        atlas.run(num_heartbeats=args.heartbeats)
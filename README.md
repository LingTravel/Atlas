# Atlas Framework

**Atlas** is a research-oriented, multimodal autonomous agent framework powered by Google Gemini 2.0. It implements a cognitive architecture featuring **adaptive homeostasis**, **tri-layer memory systems**, and **visual-first tool usage**.

Designed for extensibility, Atlas operates on a rigorous "Heartbeat" cycle, making it suitable for experiments in AGI, long-term agent memory, and human-like browser interaction.

---

## 🏗️ System Architecture

Atlas follows a modular, event-driven architecture orchestrated by a central `Brain`.

```mermaid
graph TD
    User[Entry Point] --> Main[Heartbeat Loop]
    Main --> Brain
    
    subgraph Core System
        Brain --> EventBus[Event Bus (Pub/Sub)]
        Brain --> State[State Manager (FSM)]
    end
    
    subgraph Cognition Layer
        Brain --> Homeostasis[Adaptive Homeostasis]
        Homeostasis --> Dreaming[Dreaming / Consolidation]
    end
    
    subgraph Memory Layer
        Brain <--> WorkingMem[Working Memory (FIFO)]
        Brain <--> EpisodicMem[Episodic (Vector DB)]
        Brain <--> SemanticMem[Semantic (Knowledge Graph)]
    end
    
    subgraph Tool Layer
        Brain --> ToolRegistry
        ToolRegistry --> VisualBrowser[Visual Browser (SoM)]
        ToolRegistry --> FileSystem
        ToolRegistry --> CodeExec
    end
````

## 🧩 Core Modules

### 1\. Cognition Engine (`cognition/`)

  * **Adaptive Homeostasis**: Implements a control theory-based regulation system.
      * **Mechanism**: Monitors 4 internal variables (Curiosity, Fatigue, Anxiety, Satisfaction) and adjusts hyperparameters (e.g., decay rates, reward weights) dynamically based on historical trends using sliding windows.
      * **Dreaming**: A memory consolidation process triggered by high fatigue. It retrieves recent episodic vectors, synthesizes high-level "insights" via LLM, and commits them to semantic memory.

### 2\. Memory Architecture (`memory/`)

  * **Episodic (ChromaDB)**: Stores raw experiences (`event`, `context`, `outcome`) as vector embeddings for semantic retrieval.
  * **Semantic (JSON/Graph)**: Stores distilled knowledge, rules, and facts. Acts as the agent's "World Model".
  * **Working (FIFO Queue)**: Tracks immediate context window (last $N$ heartbeats) and maintains a "read file" registry to prevent recursive reading loops.

### 3\. Visual Browser Tool (`tools/visual_browser.py`)

A wrapper around **Playwright** optimized for Multimodal LLMs.

  * **Set-of-Mark (SoM) Injection**: Injects Javascript to overlay bounded box labels (IDs) on interactive elements, solving the spatial grounding problem for LLMs.
  * **Anti-Fingerprinting**:
      * **Bezier Curve Mouse Movements**: Simulates human hand motor control using randomized control points and variable velocity.
      * **Typing Jitter**: Simulates keystroke latency.

## 🛠️ Installation & Setup

**Prerequisites**

  * Python 3.10+
  * Chrome/Chromium installed (via Playwright)

**Setup**

```bash
# 1. Install dependencies
pip install google-genai chromadb playwright numpy scipy

# 2. Install browser binaries
playwright install chromium

# 3. Environment Variables
export GEMINI_API_KEY="your_key_here"
```

**Running the Agent**

```bash
# Standard Run (One heartbeat loop)
python main.py

# Continuous Mode (Daemon-like)
python main.py --infinite
```

## 🔌 Extending Atlas

### Adding a New Tool

Inherit from the `Tool` abstract base class in `tools/base.py`.

```python
from tools.base import Tool, ToolResult

class MyCustomTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"

    @property
    def description(self) -> str:
        return "Executes a custom operation."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string"}
            }
        }

    def execute(self, param1: str) -> ToolResult:
        # Implementation
        return ToolResult(success=True, data="Result")
```

Register it in `core/brain.py`:

```python
self.tools.register(MyCustomTool())
```

-----

## 📊 Telemetry & Debugging

  * **Event Trace**: All internal events are logged to `data/trace_{timestamp}.json` on exit.
  * **State Dump**: Full agent state is persisted in `data/state.json`.
  * **Memory Inspection**: Use the `chromadb` CLI or viewer to inspect `data/chroma`.

<!-- end list -->

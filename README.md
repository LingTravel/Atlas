# Atlas: The Self-Evolving Agent

Atlas is an autonomous agent designed with a "biological" architecture. It possesses drives, memories, and most importantly, the ability to read and modify its own source code.

## Philosophy

The core philosophy of Atlas is **"Existence entails Risk"**.

- **Self-Modification**: Atlas can read and rewrite almost all of its code (`core/`, `cognition/`, `tools/`, `state/`).
- **Consequences**: If Atlas breaks its core code, it will crash.
- **Pain**: A crash results in "memory loss" (recent context is lost) and a "trauma" record in its episodic memory.
- **Evolution**: Through this feedback loop (Modification -> Success/Crash -> Learning), Atlas is expected to evolve its own behavior and internal systems without human intervention.

## Architecture

- **Brain (`core/brain.py`)**: The central orchestrator.
- **Cognition (`cognition/`)**:
    - `homeostasis.py`: Manages drives (Fatigue, Curiosity, etc.).
    - `dreaming.py`: Memory consolidation during rest.
- **Memory (`memory/`)**:
    - `working.py`: Short-term context.
    - `episodic.py`: Long-term vector memory (ChromaDB) **[PROTECTED]**.
    - `semantic.py`: Knowledge and rules.
- **Tools (`tools/`)**:
    - `code_editor.py`: The surgical tools (`read_code`, `modify_code`).
    - `visual_browser.py`: Eyes and hands for the web.
    - `mcp_client/`: Extensibility via Model Context Protocol.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Environment Variables**:
   Set `GEMINI_API_KEY` in your environment.

3. **Run**:
   ```bash
   python main.py
   ```

## The "Danger Zone"

Atlas has access to `tools/code_editor.py`. It can use:
- `read_code(filepath)`: To introspect.
- `modify_code(filepath, new_content)`: To change its behavior.

**Protected Areas**:
- `memory/episodic.py`: To prevent total amnesia.
- `data/chroma/`: The physical memory storage.

Everything else is fair game.

## License

MIT

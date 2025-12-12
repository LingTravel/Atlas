"""
Python 執行工具

讓 Atlas 能夠執行 Python 程式碼。
"""

import subprocess
import sys
from pathlib import Path

from .base import Tool, ToolResult


class PythonExecuteTool(Tool):
    """執行 Python 程式碼"""
    
    def __init__(self, timeout: int = 30, working_dir: str = None):
        self._timeout = timeout
        self._working_dir = Path(working_dir) if working_dir else Path.cwd()
    
    @property
    def name(self) -> str:
        return "execute_python"
    
    @property
    def description(self) -> str:
        return "Execute Python code. Use this to compute, create, or explore programmatically."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute"
                }
            },
            "required": ["code"]
        }
    
    def execute(self, code: str) -> ToolResult:
        try:
            # 使用 subprocess 執行，隔離環境
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._working_dir)
            )
            
            output = result.stdout
            error = result.stderr
            
            if result.returncode == 0:
                return ToolResult(
                    success=True,
                    data={
                        "output": output,
                        "returncode": 0
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    data={"output": output},
                    error=error or f"Process exited with code {result.returncode}"
                )
                
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Execution timed out after {self._timeout} seconds"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )
"""
Shell 執行工具

讓 Atlas 能執行終端命令。
"""

import subprocess
import sys
from pathlib import Path

from .base import Tool, ToolResult


class ShellTool(Tool):
    """執行 shell 命令"""
    
    # 危險命令黑名單
    BLACKLIST = [
        "rm -rf /",
        "format",
        "shutdown",
        "reboot",
        "del /f /s /q",
        "mkfs",
    ]
    
    def __init__(self, root_path: str, timeout: int = 60):
        self._root = Path(root_path).resolve()
        self._timeout = timeout
    
    @property
    def name(self) -> str:
        return "execute_shell"
    
    @property
    def description(self) -> str:
        return """Execute shell commands.

Allowed:
- pip install <package>
- git (clone, commit, push, etc.)
- python scripts
- wget, curl
- file operations in atlas/

Some dangerous commands are blocked."""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute"
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str) -> ToolResult:
        # 黑名單檢查
        for blocked in self.BLACKLIST:
            if blocked in command.lower():
                return ToolResult(
                    success=False,
                    error="Command blocked for safety"
                )
        
        try:
            # Windows vs Unix
            shell = True
            
            result = subprocess.run(
                command,
                shell=shell,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                cwd=str(self._root)
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
                    error=error or f"Command failed (exit {result.returncode})"
                )
        
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"Command timed out after {self._timeout} seconds"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )
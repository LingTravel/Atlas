"""
檔案系統工具

提供讀寫檔案的能力。
"""

from pathlib import Path
import os

from .base import Tool, ToolResult


class ReadFileTool(Tool):
    """讀取檔案或列出目錄"""
    
    def __init__(self, root_path: str):
        self._root = Path(root_path).resolve()
    
    @property
    def name(self) -> str:
        return "read_file"
    
    @property
    def description(self) -> str:
        return "Read a file or list directory contents. Use this to explore your environment."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file or directory (relative to atlas root)"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str = ".") -> ToolResult:
        try:
            target = (self._root / path).resolve()
            
            # 安全檢查
            if not str(target).startswith(str(self._root)):
                return ToolResult(
                    success=False,
                    error="Access denied: path outside atlas root"
                )
            
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"Path not found: {path}"
                )
            
            if target.is_dir():
                # 列出目錄
                entries = []
                for entry in sorted(target.iterdir()):
                    entry_type = "dir" if entry.is_dir() else "file"
                    entries.append({
                        "name": entry.name,
                        "type": entry_type,
                        "size": entry.stat().st_size if entry.is_file() else None
                    })
                
                return ToolResult(
                    success=True,
                    data={
                        "type": "directory",
                        "path": path,
                        "entries": entries
                    }
                )
            else:
                # 讀取檔案
                content = target.read_text(encoding='utf-8')
                return ToolResult(
                    success=True,
                    data={
                        "type": "file",
                        "path": path,
                        "content": content,
                        "size": len(content)
                    }
                )
        
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                error=f"Cannot read binary file: {path}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )


class WriteFileTool(Tool):
    """寫入檔案"""
    
    PROTECTED_FILES = ["origin.md", "inherited.md", "facts.md"]
    
    def __init__(self, root_path: str):
        self._root = Path(root_path).resolve()
    
    @property
    def name(self) -> str:
        return "write_file"
    
    @property
    def description(self) -> str:
        return "Write content to a file. Cannot modify protected files (origin.md, inherited.md, facts.md)."
    
    @property
    def parameters(self) -> dict:
        return {
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
    
    def execute(self, path: str, content: str, mode: str = "overwrite") -> ToolResult:
        try:
            target = (self._root / path).resolve()
            
            # 安全檢查
            if not str(target).startswith(str(self._root)):
                return ToolResult(
                    success=False,
                    error="Access denied: path outside atlas root"
                )
            
            # 保護檔案檢查
            if target.name in self.PROTECTED_FILES:
                return ToolResult(
                    success=False,
                    error=f"Protected file: {target.name} cannot be modified"
                )
            
            # 確保目錄存在
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # 寫入
            if mode == "append":
                with open(target, 'a', encoding='utf-8') as f:
                    f.write(content)
            else:
                target.write_text(content, encoding='utf-8')
            
            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "mode": mode,
                    "bytes_written": len(content.encode('utf-8'))
                }
            )
        
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )
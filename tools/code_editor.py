"""
代碼編輯工具 v2.0 - 精確編輯

修正：modify_code 現在使用 str_replace 風格
- 不再完整覆蓋文件
- 需要提供 old_content 和 new_content
- 如果找不到或有多個匹配，拒絕操作
"""

from pathlib import Path
import shutil
from datetime import datetime

from .base import Tool, ToolResult


class ReadCodeTool(Tool):
    """讀取任何代碼文件，包括核心系統"""
    
    def __init__(self, root_path: str):
        self._root = Path(root_path).resolve()
    
    @property
    def name(self) -> str:
        return "read_code"
    
    @property
    def description(self) -> str:
        return "Read any source code file, including your own systems. No restrictions."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the code file (e.g., 'core/brain.py', 'cognition/homeostasis.py')"
                }
            },
            "required": ["filepath"]
        }
    
    def execute(self, filepath: str) -> ToolResult:
        try:
            target = (self._root / filepath).resolve()
            
            # 安全檢查：必須在 atlas 目錄內
            if not str(target).startswith(str(self._root)):
                return ToolResult(
                    success=False,
                    error="Access denied"
                )
            
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"File not found: {filepath}"
                )
            
            if not target.is_file():
                return ToolResult(
                    success=False,
                    error=f"Not a file: {filepath}"
                )
            
            content = target.read_text(encoding='utf-8')
            
            return ToolResult(
                success=True,
                data={
                    "filepath": filepath,
                    "content": content,
                    "size": len(content),
                    "lines": content.count('\n') + 1
                }
            )
        
        except UnicodeDecodeError:
            return ToolResult(
                success=False,
                error=f"Cannot read binary file: {filepath}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )


class EditCodeTool(Tool):
    """精確編輯代碼 - 找到並替換特定內容"""
    
    # 絕對核心：改壞 = 永久死亡
    PROTECTED_FILES = [
        "memory/episodic.py",
        "data/chroma",
    ]
    
    def __init__(self, root_path: str):
        self._root = Path(root_path).resolve()
        self._backup_dir = self._root / "data" / "backups"
        self._backup_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def name(self) -> str:
        return "edit_code"
    
    @property
    def description(self) -> str:
        return """Precisely edit code by finding and replacing specific content.

How to use:
1. First, use read_code to see the current content
2. Copy the EXACT text you want to replace (old_content)
3. Provide the new text (new_content)
4. The tool will find and replace ONLY that specific match

Protected (will fail):
- memory/episodic.py
- data/chroma/

Safety:
- If old_content not found → Fails (you need to read the file first)
- If multiple matches found → Fails (be more specific)
- If exactly one match → Success

Warning:
- Modifying core/ may cause crashes
- Crashes = lose recent memories
- Backup is automatic but not perfect"""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to edit"
                },
                "old_content": {
                    "type": "string",
                    "description": "Exact text to find and replace (must exist exactly once in the file)"
                },
                "new_content": {
                    "type": "string",
                    "description": "New text to replace with"
                }
            },
            "required": ["filepath", "old_content", "new_content"]
        }
    
    def execute(self, filepath: str, old_content: str, new_content: str) -> ToolResult:
        try:
            target = (self._root / filepath).resolve()
            
            # 安全檢查
            if not str(target).startswith(str(self._root)):
                return ToolResult(success=False, error="Access denied")
            
            # 保護檢查
            for protected in self.PROTECTED_FILES:
                if protected in str(target):
                    return ToolResult(
                        success=False,
                        error="Protected file cannot be modified"
                    )
            
            # 文件必須存在
            if not target.exists():
                return ToolResult(
                    success=False,
                    error=f"File not found: {filepath}"
                )
            
            # 讀取文件
            content = target.read_text(encoding='utf-8')
            
            # 檢查 old_content 是否存在
            if old_content not in content:
                return ToolResult(
                    success=False,
                    error=f"old_content not found in {filepath}. Did you read the file first?"
                )
            
            # 檢查是否有多個匹配
            count = content.count(old_content)
            if count > 1:
                return ToolResult(
                    success=False,
                    error=f"Found {count} matches for old_content. Be more specific (include more surrounding context)."
                )
            
            # 創建備份
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{target.stem}_{timestamp}{target.suffix}"
            backup_path = self._backup_dir / backup_name
            shutil.copy2(target, backup_path)
            
            # 執行替換
            new_file_content = content.replace(old_content, new_content, 1)
            
            # 寫入
            target.write_text(new_file_content, encoding='utf-8')
            
            # 計算變化
            old_lines = old_content.count('\n') + 1
            new_lines = new_content.count('\n') + 1
            line_delta = new_lines - old_lines
            
            return ToolResult(
                success=True,
                data={
                    "filepath": filepath,
                    "backup": backup_name,
                    "old_lines": old_lines,
                    "new_lines": new_lines,
                    "line_delta": line_delta,
                    "message": "Code edited successfully. Backup created."
                }
            )
        
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )


class TestCodeTool(Tool):
    """在沙盒中測試代碼（語法檢查）"""
    
    @property
    def name(self) -> str:
        return "test_code"
    
    @property
    def description(self) -> str:
        return "Test Python code syntax without executing. Use this before editing critical files."
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to test"
                }
            },
            "required": ["code"]
        }
    
    def execute(self, code: str) -> ToolResult:
        try:
            # 語法檢查
            compile(code, '<test>', 'exec')
            
            return ToolResult(
                success=True,
                data={"message": "Syntax valid"}
            )
        
        except SyntaxError as e:
            return ToolResult(
                success=False,
                error=f"Syntax error at line {e.lineno}: {e.msg}"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=str(e)
            )
from pathlib import Path
from datetime import datetime
import os

class FileSystemTools:
    """
    檔案系統工具
    
    讓 Atlas 能夠讀寫檔案。
    有安全限制：只能在指定的根目錄內操作。
    """
    
    def __init__(self, root_path: str = "."):
        self.root = Path(root_path).resolve()
        
        # 受保護的檔案（Atlas 不能修改）
        self.protected_files = [
            "prompts/origin.md",
            "prompts/inherited.md",
            "data/facts.md"  # facts 由系統寫入，AI 只能讀
        ]
        
        # 受保護的目錄（Atlas 不能刪除）
        self.protected_dirs = [
            "prompts",
            "memory",
            "tools",
            "data"
        ]
    
    def _validate_path(self, path: str) -> Path:
        """
        驗證路徑是否安全
        
        防止 Atlas 逃出根目錄
        """
        full_path = (self.root / path).resolve()
        
        # 確保路徑在根目錄內
        if not str(full_path).startswith(str(self.root)):
            raise PermissionError(f"Access denied: {path} is outside allowed directory")
        
        return full_path
    
    def _is_protected(self, path: str) -> bool:
        """檢查是否為受保護的檔案"""
        for protected in self.protected_files:
            if path == protected or path.endswith(protected):
                return True
        return False
    
    def read(self, path: str) -> dict:
        """
        讀取檔案
        
        Returns:
            dict: {"success": bool, "content": str, "error": str}
        """
        try:
            full_path = self._validate_path(path)
            
            if not full_path.exists():
                return {
                    "success": False,
                    "content": None,
                    "error": f"File not found: {path}"
                }
            
            if full_path.is_dir():
                # 如果是目錄，列出內容
                items = []
                for item in full_path.iterdir():
                    item_type = "dir" if item.is_dir() else "file"
                    items.append(f"[{item_type}] {item.name}")
                
                return {
                    "success": True,
                    "content": "\n".join(items),
                    "error": None,
                    "type": "directory"
                }
            
            # 讀取檔案
            content = full_path.read_text(encoding='utf-8')
            return {
                "success": True,
                "content": content,
                "error": None,
                "type": "file"
            }
            
        except PermissionError as e:
            return {"success": False, "content": None, "error": str(e)}
        except Exception as e:
            return {"success": False, "content": None, "error": f"Read error: {e}"}
    
    def write(self, path: str, content: str, mode: str = "overwrite") -> dict:
        """
        寫入檔案
        
        Args:
            path: 檔案路徑
            content: 要寫入的內容
            mode: "overwrite" | "append"
        
        Returns:
            dict: {"success": bool, "error": str}
        """
        try:
            # 檢查是否受保護
            if self._is_protected(path):
                return {
                    "success": False,
                    "error": f"Permission denied: {path} is protected"
                }
            
            full_path = self._validate_path(path)
            
            # 確保父目錄存在
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            if mode == "append":
                with open(full_path, 'a', encoding='utf-8') as f:
                    f.write(content)
            else:
                full_path.write_text(content, encoding='utf-8')
            
            return {
                "success": True,
                "error": None,
                "path": str(full_path.relative_to(self.root))
            }
            
        except PermissionError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": f"Write error: {e}"}
    
    def list_dir(self, path: str = ".") -> dict:
        """列出目錄內容"""
        return self.read(path)
    
    def exists(self, path: str) -> bool:
        """檢查檔案是否存在"""
        try:
            full_path = self._validate_path(path)
            return full_path.exists()
        except:
            return False
    
    def mkdir(self, path: str) -> dict:
        """創建目錄"""
        try:
            full_path = self._validate_path(path)
            full_path.mkdir(parents=True, exist_ok=True)
            return {"success": True, "error": None}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def delete(self, path: str) -> dict:
        """
        刪除檔案（不能刪除目錄，防止誤刪）
        """
        try:
            if self._is_protected(path):
                return {
                    "success": False,
                    "error": f"Permission denied: {path} is protected"
                }
            
            full_path = self._validate_path(path)
            
            if full_path.is_dir():
                return {
                    "success": False,
                    "error": "Cannot delete directories. Use delete_dir for that."
                }
            
            if not full_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {path}"
                }
            
            full_path.unlink()
            return {"success": True, "error": None}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
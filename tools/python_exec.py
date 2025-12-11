import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime

class PythonExecutor:
    """
    Python 程式碼執行器
    
    讓 Atlas 能夠執行 Python 程式碼。
    有安全限制：超時、輸出長度限制。
    """
    
    def __init__(self, 
                 timeout: int = 30,
                 max_output_length: int = 10000,
                 working_dir: str = "."):
        self.timeout = timeout
        self.max_output_length = max_output_length
        self.working_dir = Path(working_dir).resolve()
    
    def execute(self, code: str) -> dict:
        """
        執行 Python 程式碼
        
        Args:
            code: Python 程式碼字串
        
        Returns:
            dict: {
                "success": bool,
                "stdout": str,
                "stderr": str,
                "error": str,
                "execution_time": float
            }
        """
        start_time = datetime.now()
        
        try:
            # 創建臨時檔案
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(code)
                temp_file = f.name
            
            try:
                # 執行程式碼
                result = subprocess.run(
                    [sys.executable, temp_file],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    cwd=str(self.working_dir)
                )
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                # 截斷過長的輸出
                stdout = result.stdout[:self.max_output_length]
                stderr = result.stderr[:self.max_output_length]
                
                if len(result.stdout) > self.max_output_length:
                    stdout += "\n... (output truncated)"
                if len(result.stderr) > self.max_output_length:
                    stderr += "\n... (output truncated)"
                
                return {
                    "success": result.returncode == 0,
                    "stdout": stdout,
                    "stderr": stderr,
                    "return_code": result.returncode,
                    "error": None,
                    "execution_time": execution_time
                }
                
            finally:
                # 清理臨時檔案
                Path(temp_file).unlink(missing_ok=True)
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"Execution timed out after {self.timeout} seconds",
                "execution_time": self.timeout
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"Execution error: {e}",
                "execution_time": (datetime.now() - start_time).total_seconds()
            }
    
    def execute_file(self, filepath: str) -> dict:
        """
        執行 Python 檔案
        
        Args:
            filepath: Python 檔案路徑
        
        Returns:
            dict: 同 execute()
        """
        try:
            full_path = (self.working_dir / filepath).resolve()
            
            if not full_path.exists():
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": "",
                    "error": f"File not found: {filepath}",
                    "execution_time": 0
                }
            
            code = full_path.read_text(encoding='utf-8')
            return self.execute(code)
            
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "error": f"Error reading file: {e}",
                "execution_time": 0
            }
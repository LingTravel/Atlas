from playwright.sync_api import sync_playwright
from pathlib import Path
from typing import Optional, Dict
import json
from datetime import datetime
import base64

class Browser:
    """
    瀏覽器工具（同步版本）
    
    給 Atlas 眼睛。
    真正的眼睛 —— 能看見圖片，不只是文字。
    """
    
    def __init__(self, headless: bool = True, workspace: str = "workspace"):
        self.headless = headless
        self.workspace = Path(workspace)
        self.workspace.mkdir(exist_ok=True)
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
    def _ensure_browser(self):
        """確保瀏覽器已啟動"""
        if self.browser is None:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            self.context = self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            self.page = self.context.new_page()
    
    def navigate(self, url: str) -> Dict:
        """
        導航到網址
        
        Args:
            url: 要訪問的網址
            
        Returns:
            dict: {"success": bool, "title": str, "url": str, "error": str}
        """
        try:
            self._ensure_browser()
            self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
            title = self.page.title()
            final_url = self.page.url
            
            return {
                "success": True,
                "title": title,
                "url": final_url,
                "error": None
            }
        except Exception as e:
            return {
                "success": False,
                "title": None,
                "url": url,
                "error": str(e)
            }
    
    def see(self, describe: bool = False) -> Dict:
        """
        「看見」當前頁面 —— 返回截圖的 base64
        
        這是真正的視覺。Atlas 可以看到圖片、佈局、顏色。
        
        Args:
            describe: 是否也返回文字描述
            
        Returns:
            dict: {
                "success": bool, 
                "image_base64": str,  # 可以直接傳給 Gemini
                "url": str,
                "title": str,
                "text": str (如果 describe=True),
                "error": str
            }
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "image_base64": None,
                    "error": "No page loaded. Use navigate() first."
                }
            
            # 截圖並轉 base64
            screenshot_bytes = self.page.screenshot()
            image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            result = {
                "success": True,
                "image_base64": image_base64,
                "url": self.page.url,
                "title": self.page.title(),
                "error": None
            }
            
            # 如果需要文字描述
            if describe:
                try:
                    text = self.page.evaluate("""
                        () => {
                            const scripts = document.querySelectorAll('script, style, noscript');
                            scripts.forEach(el => el.remove());
                            return document.body ? document.body.innerText : '';
                        }
                    """)
                    # 截斷
                    if len(text) > 5000:
                        text = text[:5000] + "\n... (truncated)"
                    result["text"] = text
                except:
                    result["text"] = ""
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "image_base64": None,
                "error": str(e)
            }
    
    def look_at(self, selector: str) -> Dict:
        """
        聚焦看某個元素
        
        Args:
            selector: CSS 選擇器
            
        Returns:
            dict: {
                "success": bool,
                "element_image_base64": str,  # 元素的截圖
                "element_text": str,           # 元素的文字
                "error": str
            }
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "element_image_base64": None,
                    "error": "No page loaded."
                }
            
            # 找到元素
            element = self.page.query_selector(selector)
            if not element:
                return {
                    "success": False,
                    "element_image_base64": None,
                    "error": f"Element not found: {selector}"
                }
            
            # 截圖元素
            screenshot_bytes = element.screenshot()
            image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # 獲取元素文字
            element_text = element.inner_text()
            
            return {
                "success": True,
                "element_image_base64": image_base64,
                "element_text": element_text,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "element_image_base64": None,
                "error": str(e)
            }
    
    def get_text(self) -> Dict:
        """
        獲取當前頁面的文字內容（舊方法，保留相容性）
        
        Returns:
            dict: {"success": bool, "text": str, "error": str}
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "text": None,
                    "error": "No page loaded. Use navigate() first."
                }
            
            text = self.page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(el => el.remove());
                    return document.body ? document.body.innerText : '';
                }
            """)
            
            # 截斷
            max_length = 10000
            if len(text) > max_length:
                text = text[:max_length] + "\n... (truncated)"
            
            return {
                "success": True,
                "text": text,
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "text": None,
                "error": str(e)
            }
    
    def screenshot(self, filename: str = None) -> Dict:
        """
        截圖當前頁面並存檔（舊方法，保留相容性）
        
        Args:
            filename: 儲存的檔名
            
        Returns:
            dict: {"success": bool, "path": str, "error": str}
        """
        try:
            if not self.page:
                return {
                    "success": False,
                    "path": None,
                    "error": "No page loaded."
                }
            
            if not filename:
                filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            
            filepath = self.workspace / filename
            self.page.screenshot(path=str(filepath))
            
            return {
                "success": True,
                "path": str(filepath),
                "error": None
            }
            
        except Exception as e:
            return {
                "success": False,
                "path": None,
                "error": str(e)
            }
    
    def search(self, query: str, visual: bool = False) -> Dict:
        """
        搜尋並選擇性地「看見」結果
        
        Args:
            query: 搜尋關鍵字
            visual: 是否返回視覺結果（截圖）
            
        Returns:
            dict: 包含搜尋結果，可能包含圖片
        """
        from urllib.parse import quote
        
        url = f"https://www.google.com/search?q={quote(query)}"
        
        try:
            self._ensure_browser()
            self.page.goto(url, wait_until='networkidle', timeout=30000)
            self.page.wait_for_timeout(2000)
            
            title = self.page.title()
            
            result = {
                "success": True,
                "url": self.page.url,
                "title": title,
                "error": None
            }
            
            if visual:
                # 返回視覺結果
                screenshot_bytes = self.page.screenshot()
                result["image_base64"] = base64.b64encode(screenshot_bytes).decode('utf-8')
            else:
                # 只返回文字
                text = self.page.evaluate("""
                    () => {
                        const scripts = document.querySelectorAll('script, style, noscript');
                        scripts.forEach(el => el.remove());
                        return document.body ? document.body.innerText : '';
                    }
                """)
                if len(text) > 10000:
                    text = text[:10000] + "\n... (truncated)"
                result["text"] = text
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def fill(self, selector: str, text: str) -> Dict:
        """填寫表單"""
        try:
            if not self.page:
                return {"success": False, "error": "No page loaded."}
            
            self.page.fill(selector, text, timeout=5000)
            return {"success": True, "error": None}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click(self, selector: str) -> Dict:
        """點擊元素"""
        try:
            if not self.page:
                return {"success": False, "error": "No page loaded."}
            
            self.page.click(selector, timeout=5000)
            self.page.wait_for_load_state('networkidle', timeout=10000)
            return {"success": True, "error": None}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def close(self) -> Dict:
        """關閉瀏覽器"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
            
            return {"success": True}
        except:
            return {"success": True}
    
    def __del__(self):
        """確保瀏覽器被關閉"""
        self.close()
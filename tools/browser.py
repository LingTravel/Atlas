"""
瀏覽器工具

讓 Atlas 能夠瀏覽網頁、看見圖像。
這是 Atlas 的「眼睛」。
"""

import base64
from pathlib import Path
from typing import Optional

from .base import Tool, ToolResult

# Playwright 延遲導入（可能未安裝）
_playwright_available = True
try:
    from playwright.sync_api import sync_playwright, Browser as PWBrowser, Page
except ImportError:
    _playwright_available = False


class BrowserTool(Tool):
    """
    網頁瀏覽工具
    
    支援的 action：
    - navigate: 前往 URL
    - read: 前往 URL 並獲取文字（合併操作）
    - see: 截圖並返回圖像（視覺）
    - get_text: 獲取當前頁面文字
    - search: 搜尋（使用 DuckDuckGo）
    - click: 點擊元素
    - fill: 填寫表單
    - close: 關閉瀏覽器
    """
    
    def __init__(self, headless: bool = True, workspace: str = None):
        self._headless = headless
        self._workspace = Path(workspace) if workspace else Path.cwd() / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)
        
        # 延遲初始化
        self._playwright = None
        self._browser: Optional[PWBrowser] = None
        self._page: Optional[Page] = None
    
    @property
    def name(self) -> str:
        return "browse"
    
    @property
    def description(self) -> str:
        return """Browse the web with VISION. You can SEE pages, not just read text.

Actions:
- search: Search the web (returns list of URLs - pick one to read)
- read: Go to URL and get text (use this after search)
- navigate: Go to a URL
- see: Get visual screenshot of current page
- get_text: Get text from current page
- click: Click an element
- fill: Fill a form field
- close: Close the browser

**Workflow**: search → pick a URL from results → read that URL"""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "read", "see", "get_text", "search", "click", "fill", "close"],
                    "description": "What action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL for navigate/read actions"
                },
                "query": {
                    "type": "string",
                    "description": "Search query for search action"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for click/fill actions"
                },
                "text": {
                    "type": "string",
                    "description": "Text for fill action"
                }
            },
            "required": ["action"]
        }
    
    def execute(self, action: str, **kwargs) -> ToolResult:
        if not _playwright_available:
            return ToolResult(
                success=False,
                error="Playwright not installed. Run: pip install playwright && playwright install"
            )
        
        # 動作路由
        actions = {
            "navigate": self._navigate,
            "read": self._read,
            "see": self._see,
            "get_text": self._get_text,
            "search": self._search,
            "click": self._click,
            "fill": self._fill,
            "close": self._close
        }
        
        handler = actions.get(action)
        if not handler:
            return ToolResult(
                success=False,
                error=f"Unknown action: {action}. Available: {list(actions.keys())}"
            )
        
        try:
            return handler(**kwargs)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Browser error: {str(e)}"
            )
    
    def _ensure_browser(self):
        """確保瀏覽器已啟動（帶反檢測）"""
        if self._page is not None:
            return
        
        self._playwright = sync_playwright().start()
        
        # === 啟動帶反檢測的瀏覽器 ===
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                '--disable-blink-features=AutomationControlled',  # 關鍵！
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process'
            ]
        )
        
        # 創建上下文（更多偽裝）
        context = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            # 添加常見的瀏覽器功能
            has_touch=False,
            is_mobile=False,
            device_scale_factor=1
        )
        
        self._page = context.new_page()
        
        # === 注入反檢測腳本 ===
        self._page.add_init_script("""
            // 移除 webdriver 標記
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 偽造 Chrome 環境
            window.chrome = {
                runtime: {}
            };
            
            // 偽造 plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            // 偽造 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
    
    def _navigate(self, url: str = None, **_) -> ToolResult:
        if not url:
            return ToolResult(success=False, error="URL required for navigate")
        
        self._ensure_browser()
        self._page.goto(url, timeout=30000)
        
        return ToolResult(
            success=True,
            data={
                "url": self._page.url,
                "title": self._page.title()
            }
        )
    
    def _read(self, url: str = None, **_) -> ToolResult:
        """Navigate + get_text 合併"""
        if not url:
            return ToolResult(success=False, error="URL required for read")
        
        self._ensure_browser()
        self._page.goto(url, timeout=30000)
        
        # 獲取文字
        text = self._page.inner_text("body")
        # 限制長度
        if len(text) > 10000:
            text = text[:10000] + "\n\n[...truncated...]"
        
        return ToolResult(
            success=True,
            data={
                "url": self._page.url,
                "title": self._page.title(),
                "text": text
            }
        )
    
    def _see(self, **_) -> ToolResult:
        """截圖並返回 base64"""
        if self._page is None:
            return ToolResult(
                success=False,
                error="No page open. Use navigate or read first."
            )
        
        # 截圖
        screenshot_bytes = self._page.screenshot(type="png")
        image_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
        
        return ToolResult(
            success=True,
            data={
                "url": self._page.url,
                "title": self._page.title(),
                "image_base64": image_base64
            },
            metadata={"has_image": True}
        )
    
    def _get_text(self, **_) -> ToolResult:
        if self._page is None:
            return ToolResult(
                success=False,
                error="No page open. Use navigate first."
            )
        
        text = self._page.inner_text("body")
        if len(text) > 10000:
            text = text[:10000] + "\n\n[...truncated...]"
        
        return ToolResult(
            success=True,
            data={
                "url": self._page.url,
                "title": self._page.title(),
                "text": text
            }
        )
    
    def _search(self, query: str = None, **_) -> ToolResult:
        """搜尋網路並返回結果列表"""
        if not query:
            return ToolResult(success=False, error="Query required for search")
        
        self._ensure_browser()
        
        # 嘗試 DuckDuckGo HTML 版本
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        
        try:
            self._page.goto(search_url, timeout=30000)
            self._page.wait_for_timeout(2000)
            
            # 檢測 CAPTCHA
            page_text = self._page.inner_text("body")
            if "captcha" in page_text.lower() or "robot" in page_text.lower() or "verify" in page_text.lower():
                # 被擋了，嘗試 Wikipedia
                return self._search_wikipedia(query)
            
        except Exception as e:
            return self._search_wikipedia(query)
        
        # 提取搜尋結果
        results = []
        try:
            links = self._page.query_selector_all(".result__a")
            snippets = self._page.query_selector_all(".result__snippet")
            
            for i, link in enumerate(links[:5]):
                href = link.get_attribute("href")
                title = link.inner_text().strip()
                
                snippet = ""
                if i < len(snippets):
                    snippet = snippets[i].inner_text().strip()[:150]
                
                if href and title:
                    results.append({
                        "index": i + 1,
                        "title": title[:100],
                        "url": href,
                        "snippet": snippet
                    })
        except Exception:
            pass
        
        if results:
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "result_count": len(results),
                    "results": results,
                    "next_step": "Choose a result and use: browse(action='read', url='<url>')"
                }
            )
        else:
            # 降級到 Wikipedia
            return self._search_wikipedia(query)


    def _search_wikipedia(self, query: str) -> ToolResult:
        """Wikipedia 備選搜尋"""
        self._ensure_browser()
        
        # Wikipedia 搜尋
        wiki_url = f"https://en.wikipedia.org/w/index.php?search={query}"
        
        try:
            self._page.goto(wiki_url, timeout=30000)
            self._page.wait_for_timeout(2000)
            
            current_url = self._page.url
            
            # 如果直接跳轉到文章頁
            if "/wiki/" in current_url and "search" not in current_url.lower():
                title = self._page.title()
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "source": "wikipedia",
                        "found_article": True,
                        "title": title,
                        "url": current_url,
                        "next_step": f"Use browse(action='read', url='{current_url}') to read the article"
                    }
                )
            
            # 搜尋結果頁
            results = []
            try:
                search_results = self._page.query_selector_all(".mw-search-result-heading a")
                for i, link in enumerate(search_results[:5]):
                    href = link.get_attribute("href")
                    title = link.inner_text().strip()
                    if href and title:
                        full_url = f"https://en.wikipedia.org{href}"
                        results.append({
                            "index": i + 1,
                            "title": title,
                            "url": full_url
                        })
            except Exception:
                pass
            
            if results:
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "source": "wikipedia",
                        "result_count": len(results),
                        "results": results,
                        "next_step": "Choose a result and use: browse(action='read', url='<url>')"
                    }
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"No results found for '{query}' on Wikipedia"
                )
        
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Wikipedia search failed: {str(e)}"
            )
    
    def _click(self, selector: str = None, **_) -> ToolResult:
        if not selector:
            return ToolResult(success=False, error="Selector required for click")
        
        if self._page is None:
            return ToolResult(success=False, error="No page open")
        
        self._page.click(selector, timeout=5000)
        self._page.wait_for_timeout(1000)
        
        return ToolResult(
            success=True,
            data={
                "clicked": selector,
                "current_url": self._page.url
            }
        )
    
    def _fill(self, selector: str = None, text: str = None, **_) -> ToolResult:
        if not selector or text is None:
            return ToolResult(
                success=False,
                error="Selector and text required for fill"
            )
        
        if self._page is None:
            return ToolResult(success=False, error="No page open")
        
        self._page.fill(selector, text, timeout=5000)
        
        return ToolResult(
            success=True,
            data={
                "filled": selector,
                "text_length": len(text)
            }
        )
    
    def _close(self, **_) -> ToolResult:
        if self._browser:
            self._browser.close()
            self._browser = None
            self._page = None
        
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        
        return ToolResult(
            success=True,
            data={"message": "Browser closed"}
        )
    
    def __del__(self):
        """清理資源"""
        try:
            self._close()
        except:
            pass
"""
視覺瀏覽器工具

讓 Atlas 能夠「看見」並「像人類一樣」操作網頁。
這是 Atlas 的眼睛和手。
"""

import base64
import random
import time
from pathlib import Path
from typing import Optional

from .base import Tool, ToolResult

# Playwright 延遲導入
_playwright_available = True
try:
    from playwright.sync_api import sync_playwright, Browser as PWBrowser, Page, BrowserContext
except ImportError:
    _playwright_available = False


class VisualBrowser(Tool):
    """
    視覺化瀏覽器 - Atlas 的眼睛與手
    
    核心理念：
    - 視覺優先：透過截圖而非 DOM 來理解頁面
    - Set-of-Mark：在可交互元素上標記編號
    - 擬人化：模擬人類的滑鼠軌跡和打字節奏
    """
    
    # === 配置常量 ===
    VIEWPORT = {"width": 1280, "height": 800}
    SCREENSHOT_QUALITY = 75  # JPEG 品質
    
    def __init__(
        self, 
        headless: bool = False,      # False = 可觀察 Atlas 操作
        humanize: bool = True,       # True = 擬人化操作
        workspace: str = None
    ):
        self._headless = headless
        self._humanize = humanize
        self._workspace = Path(workspace) if workspace else Path.cwd() / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)
        
        # 瀏覽器狀態
        self._playwright = None
        self._browser: Optional[PWBrowser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        
        # 滑鼠位置追蹤（擬人化需要）
        self._mouse_pos = (self.VIEWPORT["width"] // 2, self.VIEWPORT["height"] // 2)
        
        # SoM 元素映射（只保留在 Python 端，不傳給 LLM）
        self._element_map: dict[int, dict] = {}
    
    # === Tool 介面實作 ===
    
    @property
    def name(self) -> str:
        return "browse"
    
    @property
    def description(self) -> str:
        return """Browse the web with VISION. You can SEE pages like a human.

When you use this tool, you'll receive:
- A screenshot with numbered labels [0], [1], [2]... on clickable elements
- Use these label numbers to interact

Actions:
- navigate: Go to a URL
- observe: Get current page screenshot with labels
- click: Click element by label number
- type: Type text (at current focus)
- scroll: Scroll the page
- close: Close browser

Example workflow:
1. navigate to a URL
2. Look at the screenshot, find the search box labeled [3]
3. click label_id=3
4. type text="your search query"
5. Look for the search button, maybe [7]
6. click label_id=7"""
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["navigate", "observe", "click", "type", "scroll", "close"],
                    "description": "What action to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL for navigate action"
                },
                "label_id": {
                    "type": "integer",
                    "description": "Element label number for click action"
                },
                "text": {
                    "type": "string",
                    "description": "Text for type action"
                },
                "submit": {
                    "type": "boolean",
                    "description": "Press Enter after typing (for search boxes)"
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction"
                }
            },
            "required": ["action"]
        }
    
    def execute(self, action: str, **kwargs) -> ToolResult:
        """執行動作"""
        if not _playwright_available:
            return ToolResult(
                success=False,
                error="Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
        
        actions = {
            "navigate": self._navigate,
            "observe": self._observe,
            "click": self._click,
            "type": self._type,
            "scroll": self._scroll,
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
    
    # === 瀏覽器生命週期 ===
    
    def _ensure_browser(self):
        """確保瀏覽器已啟動（帶反檢測配置）"""
        if self._page is not None:
            return
        
        self._playwright = sync_playwright().start()
        
        # 啟動瀏覽器（反檢測參數）
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        # 創建上下文（偽裝配置）
        self._context = self._browser.new_context(
            viewport=self.VIEWPORT,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
        )
        
        self._page = self._context.new_page()
        
        # 注入反檢測腳本
        self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
    
    def _close(self, **_) -> ToolResult:
        """關閉瀏覽器"""
        if self._browser:
            self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
        
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        
        self._element_map = {}
        self._mouse_pos = (self.VIEWPORT["width"] // 2, self.VIEWPORT["height"] // 2)
        
        return ToolResult(success=True, data={"message": "Browser closed"})
    
    # === SoM (Set-of-Mark) 注入 ===
    
    # 這段 JavaScript 會在頁面上標記所有可交互元素
    SOM_INJECT_SCRIPT = """
    () => {
        // 移除舊標記
        document.querySelectorAll('.atlas-som-label').forEach(el => el.remove());
        
        // 要標記的元素選擇器
        const selectors = [
            'a[href]',
            'button',
            'input:not([type="hidden"])',
            'select',
            'textarea',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="menuitem"]',
            '[onclick]',
            '[tabindex]:not([tabindex="-1"])'
        ];
        
        const elements = [];
        let labelId = 0;
        
        // 標記函數（支援遞歸處理 iframe）
        function markElements(doc, offsetX = 0, offsetY = 0) {
            if (!doc) return;
            
            selectors.forEach(selector => {
                try {
                    doc.querySelectorAll(selector).forEach(el => {
                        // 檢查元素是否可見
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        if (
                            rect.width <= 0 || 
                            rect.height <= 0 ||
                            style.visibility === 'hidden' ||
                            style.display === 'none' ||
                            parseFloat(style.opacity) === 0
                        ) {
                            return;
                        }
                        
                        // 檢查元素是否在視窗內
                        const viewportWidth = window.innerWidth;
                        const viewportHeight = window.innerHeight;
                        
                        if (
                            rect.right < 0 || 
                            rect.bottom < 0 ||
                            rect.left > viewportWidth ||
                            rect.top > viewportHeight
                        ) {
                            return;
                        }
                        
                        // 創建標籤
                        const label = document.createElement('div');
                        label.className = 'atlas-som-label';
                        label.textContent = labelId;
                        label.style.cssText = `
                            position: fixed !important;
                            left: ${rect.left + offsetX}px !important;
                            top: ${rect.top + offsetY}px !important;
                            background: #FFFF00 !important;
                            color: #000000 !important;
                            border: 2px solid #FF0000 !important;
                            font-size: 12px !important;
                            font-weight: bold !important;
                            font-family: monospace !important;
                            padding: 1px 4px !important;
                            z-index: 2147483647 !important;
                            pointer-events: none !important;
                            border-radius: 3px !important;
                            line-height: 1.2 !important;
                        `;
                        document.body.appendChild(label);
                        
                        // 獲取元素的可讀文字
                        let text = '';
                        if (el.tagName === 'INPUT') {
                            text = el.placeholder || el.value || el.name || '';
                        } else if (el.tagName === 'SELECT') {
                            text = el.options[el.selectedIndex]?.text || '';
                        } else {
                            text = el.innerText || el.textContent || el.getAttribute('aria-label') || '';
                        }
                        text = text.trim().substring(0, 50);  // 限制長度
                        
                        // 記錄元素資訊
                        elements.push({
                            id: labelId,
                            x: Math.round(rect.left + rect.width / 2 + offsetX),
                            y: Math.round(rect.top + rect.height / 2 + offsetY),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            tag: el.tagName.toLowerCase(),
                            type: el.type || '',
                            text: text
                        });
                        
                        labelId++;
                    });
                } catch (e) {
                    // 忽略選擇器錯誤
                }
            });
            
            // 遞歸處理 iframe
            try {
                doc.querySelectorAll('iframe').forEach(iframe => {
                    try {
                        const iframeRect = iframe.getBoundingClientRect();
                        const iframeDoc = iframe.contentDocument || iframe.contentWindow?.document;
                        if (iframeDoc) {
                            markElements(
                                iframeDoc, 
                                offsetX + iframeRect.left, 
                                offsetY + iframeRect.top
                            );
                        }
                    } catch (e) {
                        // 跨域 iframe 無法訪問，忽略
                    }
                });
            } catch (e) {
                // 忽略 iframe 錯誤
            }
        }
        
        // 執行標記
        markElements(document);
        
        return elements;
    }
    """
    
    # 移除 SoM 標記的腳本
    SOM_CLEANUP_SCRIPT = """
    () => {
        document.querySelectorAll('.atlas-som-label').forEach(el => el.remove());
    }
    """
    
    def __del__(self):
        try:
            self._close()
        except:
            pass
    
    # === 核心動作 ===
    
    def _navigate(self, url: str = None, **_) -> ToolResult:
        """導航到 URL 並返回觀察"""
        if not url:
            return ToolResult(success=False, error="URL required")
        
        self._ensure_browser()
        
        try:
            self._page.goto(url, timeout=30000, wait_until="domcontentloaded")
            self._page.wait_for_timeout(1500)  # 等待頁面穩定
            
            # 導航後自動返回觀察
            return self._observe()
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Navigation failed: {str(e)}"
            )
    
    def _observe(self, **_) -> ToolResult:
        """
        獲取當前頁面的視覺觀察
        
        返回：
        - 帶有 SoM 標籤的截圖 (base64)
        - 元素簡要列表（僅 id, tag, text，不含座標）
        """
        if self._page is None:
            return ToolResult(success=False, error="No page open. Use navigate first.")
        
        try:
            # 1. 等待頁面穩定
            self._page.wait_for_timeout(500)
            
            # 2. 注入 SoM 標記並獲取元素資訊
            elements = self._page.evaluate(self.SOM_INJECT_SCRIPT)
            
            # 3. 更新內部元素映射（座標留在 Python 端）
            self._element_map = {}
            for el in elements:
                self._element_map[el['id']] = {
                    'x': el['x'],
                    'y': el['y'],
                    'width': el['width'],
                    'height': el['height'],
                    'tag': el['tag'],
                    'type': el['type'],
                    'text': el['text']
                }
            
            # 4. 截圖（帶有 SoM 標籤）
            screenshot_bytes = self._page.screenshot(
                type="jpeg",
                quality=self.SCREENSHOT_QUALITY
            )
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            # 5. 構建給 LLM 的元素列表（不含座標，節省 token）
            elements_for_llm = []
            for el in elements:
                element_info = {
                    'id': el['id'],
                    'tag': el['tag'],
                }
                # 只有當有 text 時才加入
                if el['text']:
                    element_info['text'] = el['text']
                # input 類型有用
                if el['type']:
                    element_info['type'] = el['type']
                elements_for_llm.append(element_info)
            
            # 6. 可選：清理標記（如果需要乾淨截圖再截一次）
            # self._page.evaluate(self.SOM_CLEANUP_SCRIPT)
            
            return ToolResult(
                success=True,
                data={
                    'url': self._page.url,
                    'title': self._page.title(),
                    'screenshot': screenshot_base64,
                    'elements': elements_for_llm,
                    'element_count': len(elements)
                },
                metadata={'has_image': True}
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Observation failed: {str(e)}"
            )
    
    # === 核心動作實作 ===
    
    def _click(self, label_id: int = None, **_) -> ToolResult:
        """點擊指定標籤的元素"""
        if label_id is None:
            return ToolResult(success=False, error="label_id required")
        
        if label_id not in self._element_map:
            return ToolResult(
                success=False, 
                error=f"Label [{label_id}] not found. Available labels: {list(self._element_map.keys())[:10]}..."
            )
        
        if self._page is None:
            return ToolResult(success=False, error="No page open")
        
        # 獲取元素資訊
        element = self._element_map[label_id]
        
        try:
            # 點擊前先清除 SoM 標籤（避免遮擋）
            self._page.evaluate("() => document.querySelectorAll('.atlas-som-label').forEach(el => el.remove())")
            
            # 記住當前 URL（用於檢測是否發生導航）
            url_before = self._page.url
            
            # 擬人化點擊
            self._human_click_at(
                element['x'], 
                element['y'], 
                element['width'], 
                element['height']
            )
            
            # 等待可能的頁面導航或動態變化
            try:
                # 等待網路空閒或最多 3 秒
                self._page.wait_for_load_state("networkidle", timeout=3000)
            except:
                # 超時沒關係，頁面可能沒有導航
                pass
            
            # 額外等待確保頁面穩定
            self._page.wait_for_timeout(500)
            
            # 返回新的觀察
            return self._observe()
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Click failed: {str(e)}"
            )
    
    def _type(self, text: str = None, submit: bool = False, **_) -> ToolResult:
        """輸入文字（在當前焦點位置）"""
        if not text:
            return ToolResult(success=False, error="text required")
        
        if self._page is None:
            return ToolResult(success=False, error="No page open")
        
        try:
            self._human_type(text)
            
            # 如果需要提交（按 Enter）
            if submit:
                if self._humanize:
                    time.sleep(random.uniform(0.1, 0.3))  # 打完字後稍微停頓
                self._page.keyboard.press("Enter")
                
                # 等待頁面響應
                try:
                    self._page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass
                self._page.wait_for_timeout(1000)
            else:
                # 打字後稍等
                self._page.wait_for_timeout(500)
            
            # 返回新的觀察
            return self._observe()
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Type failed: {str(e)}"
            )
    
    def _scroll(self, direction: str = "down", **_) -> ToolResult:
        """滾動頁面"""
        if self._page is None:
            return ToolResult(success=False, error="No page open")
        
        if direction not in ["up", "down"]:
            return ToolResult(success=False, error="direction must be 'up' or 'down'")
        
        try:
            # 擬人化滾動
            amount = random.randint(250, 400) if self._humanize else 300
            self._human_scroll(direction, amount)
            
            # 滾動後返回新的觀察
            return self._observe()
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Scroll failed: {str(e)}"
            )
    
    # === 擬人化輔助方法 ===
    
    def _bezier_curve(self, start: tuple, end: tuple, steps: int = None) -> list[tuple]:
        """
        生成從 start 到 end 的貝塞爾曲線軌跡點
        
        使用三階貝塞爾曲線，添加隨機控制點模擬人類手部抖動
        """
        if steps is None:
            # 根據距離動態計算步數
            distance = ((end[0] - start[0])**2 + (end[1] - start[1])**2)**0.5
            steps = max(20, min(int(distance / 10), 40))
        
        # 生成兩個隨機控制點
        # 控制點在起點和終點連線的附近，但有偏移
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        # 控制點 1：靠近起點，隨機偏移
        ctrl1_x = start[0] + dx * 0.25 + random.uniform(-abs(dx) * 0.3, abs(dx) * 0.3)
        ctrl1_y = start[1] + dy * 0.25 + random.uniform(-abs(dy) * 0.3, abs(dy) * 0.3)
        
        # 控制點 2：靠近終點，隨機偏移
        ctrl2_x = start[0] + dx * 0.75 + random.uniform(-abs(dx) * 0.3, abs(dx) * 0.3)
        ctrl2_y = start[1] + dy * 0.75 + random.uniform(-abs(dy) * 0.3, abs(dy) * 0.3)
        
        p0 = start
        p1 = (ctrl1_x, ctrl1_y)
        p2 = (ctrl2_x, ctrl2_y)
        p3 = end
        
        # 計算貝塞爾曲線上的點
        points = []
        for i in range(steps + 1):
            t = i / steps
            u = 1 - t
            
            # 三階貝塞爾公式
            x = (u**3 * p0[0] + 
                 3 * u**2 * t * p1[0] + 
                 3 * u * t**2 * p2[0] + 
                 t**3 * p3[0])
            
            y = (u**3 * p0[1] + 
                 3 * u**2 * t * p1[1] + 
                 3 * u * t**2 * p2[1] + 
                 t**3 * p3[1])
            
            points.append((int(x), int(y)))
        
        return points
    
    def _human_move(self, target: tuple):
        """
        擬人化移動滑鼠到目標位置
        
        特點：
        - 貝塞爾曲線軌跡
        - 非勻速（開始慢、中間快、結束慢）
        - 輕微抖動
        """
        if not self._humanize:
            # 非擬人模式：直接移動
            self._page.mouse.move(target[0], target[1])
            self._mouse_pos = target
            return
        
        # 生成曲線軌跡
        path = self._bezier_curve(self._mouse_pos, target)
        
        # 沿著軌跡移動
        for i, point in enumerate(path):
            # 計算延遲（非勻速：開始慢、中間快、結束慢）
            progress = i / len(path)
            if progress < 0.2:
                # 起始階段：慢
                delay = random.uniform(0.008, 0.015)
            elif progress > 0.8:
                # 結束階段：慢
                delay = random.uniform(0.008, 0.015)
            else:
                # 中間階段：快
                delay = random.uniform(0.003, 0.008)
            
            self._page.mouse.move(point[0], point[1])
            time.sleep(delay)
        
        self._mouse_pos = target
    
    def _human_click_at(self, x: int, y: int, width: int, height: int):
        """
        擬人化點擊
        """
        # 調試輸出
        print(f"    🎯 Clicking at center ({x}, {y}), element size: {width}x{height}")
        
        # 1. 計算點擊位置
        if self._humanize:
            max_offset_x = min(10, width * 0.15)
            max_offset_y = min(10, height * 0.15)
            
            offset_x = random.uniform(-max_offset_x, max_offset_x)
            offset_y = random.uniform(-max_offset_y, max_offset_y)
        else:
            offset_x = 0
            offset_y = 0
        
        target_x = int(x + offset_x)
        target_y = int(y + offset_y)
        
        print(f"    🖱️  Final target: ({target_x}, {target_y})")
        
        # ... 其餘代碼不變 ...
        
        # 2. 移動到目標位置
        self._human_move((target_x, target_y))
        
        # 3. 懸停（讓 :hover 樣式觸發，也更像人類）
        if self._humanize:
            time.sleep(random.uniform(0.1, 0.3))
        
        # 4. 按下 → 等待 → 釋放
        self._page.mouse.down()
        if self._humanize:
            time.sleep(random.uniform(0.05, 0.12))
        self._page.mouse.up()
        
        # 5. 點擊後稍微停頓（觀察反應）
        if self._humanize:
            time.sleep(random.uniform(0.1, 0.25))
    
    def _human_type(self, text: str):
        """
        擬人化打字
        
        特點：
        - 不規則間隔（50-150ms）
        - 10% 機率更長停頓（思考）
        - 模擬思考停頓
        """
        if not self._humanize:
            # 非擬人模式：直接輸入
            self._page.keyboard.type(text)
            return
        
        for i, char in enumerate(text):
            # 基礎延遲
            delay = random.uniform(0.05, 0.15)
            
            # 10% 機率：更長停頓（模擬思考下一個字）
            if random.random() < 0.1:
                delay += random.uniform(0.15, 0.4)
            
            # 空格後稍微停頓（詞之間的停頓）
            if i > 0 and text[i-1] == ' ':
                delay += random.uniform(0.05, 0.15)
            
            self._page.keyboard.type(char)
            time.sleep(delay)
    
    def _human_scroll(self, direction: str, amount: int = 300):
        """
        擬人化滾動
        
        特點：
        - 慣性效果（開始慢、中間快、結束慢）
        - 不是一次到位，而是分段滾動
        - 偶爾會滾過頭再回滾一點
        """
        delta = amount if direction == "down" else -amount
        
        if not self._humanize:
            # 非擬人模式：直接滾動
            self._page.mouse.wheel(0, delta)
            return
        
        # 分成多段滾動（模擬慣性）
        segments = random.randint(5, 10)
        total_scrolled = 0
        
        for i in range(segments):
            # 計算這一段的滾動量（開始小、中間大、結束小）
            progress = i / segments
            if progress < 0.2:
                segment_ratio = 0.05
            elif progress > 0.8:
                segment_ratio = 0.05
            else:
                segment_ratio = 0.15
            
            segment_delta = int(delta * segment_ratio)
            self._page.mouse.wheel(0, segment_delta)
            total_scrolled += segment_delta
            
            # 段間延遲
            time.sleep(random.uniform(0.02, 0.05))
        
        # 補足剩餘距離
        remaining = delta - total_scrolled
        if abs(remaining) > 10:
            self._page.mouse.wheel(0, remaining)
        
        # 15% 機率：滾過頭再回滾一點（人類常見行為）
        if self._humanize and random.random() < 0.15:
            time.sleep(random.uniform(0.1, 0.3))
            correction = int(delta * random.uniform(-0.1, -0.05))
            self._page.mouse.wheel(0, correction)
        
        # 滾動後停頓（閱讀內容）
        if self._humanize:
            time.sleep(random.uniform(0.3, 0.8))
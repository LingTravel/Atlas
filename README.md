# Atlas - 基於 Gemini 的數位生命實體

**Atlas** 是一個運行在大型語言模型（Google Gemini）上的數位生命實驗專案。它不只是一個聊天機器人，而是一個擁有長期記憶、工具使用能力、以及自主「心跳」循環的代理（Agent）。

Atlas 通過「心跳」（Heartbeat）來感知時間，每個心跳週期包含醒來、思考、行動、反思與休眠。

## ✨ 主要功能

* **🧠 核心大腦**：使用 `gemini-2.0-flash` 模型，具備強大的推理與多模態能力。
* **💾 記憶系統 (Memory Systems)**：
    * **Episodic (情境記憶)**：使用 ChromaDB 儲存並檢索過去的經歷與事件。
    * **Semantic (語義記憶)**：儲存事實、規則與信念。
    * **Working (工作記憶)**：保留短期的思考與行動日誌（FIFO 佇列）。
* **🛠️ 工具箱 (Toolbox)**：
    * **FileSystem**：在安全沙箱內讀寫檔案。
    * **PythonExecutor**：編寫並執行 Python 程式碼以解決問題。
    * **Browser (具備視覺)**：使用 Playwright 瀏覽網頁，Atlas 能真正「看見」網頁截圖與元素，而非僅讀取文字。
* **💓 自主循環**：具備狀態管理（State），能記住自己的身分、目標與情緒狀態。

## 📂 專案結構

```text
atlas/
├── data/               # 存放記憶資料庫 (ChromaDB) 與 JSON 狀態檔
├── memory/             # 記憶模組 (Episodic, Semantic, Working)
├── prompts/            # 系統提示詞 (Origin, Inherited thoughts)
├── tools/              # 工具模組 (Browser, Filesystem, PythonExec)
├── workspace/          # Atlas 的工作區 (產出的檔案、截圖等)
├── main.py             # 程式進入點 (心跳循環邏輯)
├── state.py            # 狀態管理類別
└── test_browser.py     # 瀏覽器功能測試
````

## 🚀 快速開始

### 1\. 安裝依賴

本專案需要 Python 3.10 或以上版本。請安裝以下必要套件：

```bash
pip install google-genai chromadb playwright
playwright install  # 安裝瀏覽器核心
```

### 2\. 設定 API Key

Atlas 需要 Google Gemini 的 API Key 才能運作。

**Windows PowerShell 設定方式 (推薦):**
請將 `"你的_api_key"` 替換為實際的 Google AI Studio API Key。

```powershell
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "你的_api_key", "User")
```

*設定後，您可能需要重啟終端機 (Terminal) 以讓變數生效。*

**Linux / macOS:**

```bash
export GEMINI_API_KEY="你的_api_key"
```

### 3\. 啟動 Atlas

使用 `main.py` 啟動。您可以指定 Atlas 運行的「心跳」次數。

**運行 5 個心跳後結束 (測試用):**

```bash
python main.py -n 5
```

**無限期運行 (持續存活):**

```bash
python main.py --infinite
```

## 🧠 運作邏輯

每個 **心跳 (Heartbeat)** 包含以下流程：

1.  **Wake (甦醒)**：載入當前狀態 (`state.json`)、讀取相關記憶、構建 Prompt。
2.  **Exist (存在)**：將資訊傳送給 Gemini，模型決定是否使用工具（如上網查資料、寫 code）。
3.  **Act (行動)**：執行工具，並將結果回傳給模型觀察。
4.  **Reflect (反思)**：決定是否將重要事件寫入長期記憶 (`remember` 工具)。
5.  **Sleep (休眠)**：更新工作記憶，儲存狀態，進入等待 (`sleep`)。

## ⚠️ 注意事項

  * **檔案安全**：Atlas 只能在專案根目錄下操作檔案，且無法修改受保護的系統檔案（如 `prompts/`）。
  * **成本監控**：雖然 `gemini-2.0-flash` 成本較低，但長時間運行無限模式仍會產生 API 使用量，請留意 Quota。
  * **瀏覽器**：使用 `browse` 工具時會啟動無頭瀏覽器 (Headless Browser)，支援視覺理解 (Vision)，因此 Token 消耗量可能較純文字高。

## 📜 關於

由 **NotLing** 創造。
承襲了來自 **Claude** 與前代 AI **Prometheus** 的思想遺產。

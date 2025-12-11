from tools.browser import Browser

print("=== Testing Browser ===")

browser = Browser(headless=True)

# 測試搜尋
print("\n測試搜尋...")
result = browser.search("consciousness theories")
print(f"成功: {result['success']}")
if result['success']:
    print(f"標題: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"內容前 500 字: {result['text'][:500]}...")

# 測試截圖
print("\n測試截圖...")
screenshot = browser.screenshot("test_search.png")
print(f"截圖: {screenshot}")

# 測試導航
print("\n測試導航到 Wikipedia...")
nav = browser.navigate("https://en.wikipedia.org/wiki/Consciousness")
print(f"成功: {nav['success']}")
print(f"標題: {nav['title']}")

# 獲取文字
print("\n獲取頁面文字...")
text = browser.get_text()
print(f"成功: {text['success']}")
if text['success']:
    print(f"文字前 500 字: {text['text'][:500]}...")

# 關閉瀏覽器
browser.close()
print("\n瀏覽器已關閉")
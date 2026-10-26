"""golden：把網頁目前「確認正確」的關鍵規格釘住（2026-10-25 使用者要求「釘成 golden」）。

從 index.html／lib／test_sync.py 抽出規格，跟 tests/golden/contract.json 比對，有任何不同就紅。
- 故意要改規格（使用者新裁示）時：改完程式 → `python3 tests/test_golden.py --update` 重生 → 檢查 diff → 一起 commit。
- 不准為了讓測試變綠而重生：先想清楚是不是改壞了。
"""
import hashlib, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN = os.path.join(ROOT, "tests", "golden", "contract.json")
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
sync_test = open(os.path.join(ROOT, "tests", "test_sync.py"), encoding="utf-8").read()


def section(start, end):
    return html[html.index(start):html.index(end, html.index(start))]


def ids(block):
    return re.findall(r'\sid="([^"]+)"', block)


def one(pattern, text=html, group=1):
    m = re.search(pattern, text, re.S)
    return m.group(group).strip() if m else None


def extract():
    host = section('<section id="host"', "</section>")
    viewer = section('<section id="viewer"', "</section>")
    script = html[html.rindex("<script>"):]
    libs = re.findall(r'<script src="(lib/[^"]+)"', html)
    return {
        "畫面元件": {
            "主持人頁面（依序）": ids(host),
            "觀眾頁面（依序）": ids(viewer),
            "不准出現（已依裁示拿掉）": sorted(x for x in ["muteAll", "muteAllHint", "tap", "tapBtn", "tapTitle", "selfMute", "newRoom"]
                                    if f'id="{x}"' not in html),
            "QR code 在主持人頁面最上面": host.index('id="qr"') < host.index('id="url"') < host.index('id="hostPlayer"'),
            "紅框在影片外面": "tapHint" not in section('id="viewerWrap"', "</div>\n"),
        },
        "提示文字": {
            "紅框": one(r"\$\('tapHint'\)\.innerHTML = '([^']+)'"),
            "主持人靜音說明": one(r'<p class="hint">(觀眾的影片一律靜音[^<]+)</p>'),
            "已結束": one(r'<div id="ended" class="hidden">(.*?)</div>\s*</div>'),
            "結束放映按鈕": one(r'id="endShow">([^<]+)<'),
            "載入中": one(r'<p id="boot" class="hint">([^<]+)<'),
        },
        "播放器設定": {
            "共用": one(r"const playerVars = (\{[^}]+\})"),
            "主持人": one(r"new YT\.Player\('hostPlayer', \{\s*playerVars: ([^\n]+?\))[,\s]*//"),
            "觀眾": one(r"new YT\.Player\('viewerPlayer', \{\s*playerVars: (Object\.assign\(\{\}, playerVars, \{[^}]+\}\))"),
        },
        "全螢幕": {
            "主持人按鈕": one(r'id="hostFsBtn">([^<]+)<'),
            "觀眾按鈕": one(r'id="fsBtn">([^<]+)<'),
            "離開按鈕": sorted(set(re.findall(r'class="fs-exit" id="[^"]+">([^<]+)<', html))),
            "主持人與觀眾共用同一套": re.findall(r"setupFullscreen\(\$\('(\w+)'\)", script),
            "iPhone 直拿轉 90 度": "rotate(90deg)" in html,
            "Android 鎖橫向": "screen.orientation.lock('landscape')" in script,
            "主持人藏起 YouTube 全螢幕鍵": "playerVars, { fs: 0 })" in script,
        },
        "同步參數": {
            "訊息伺服器": re.findall(r"'(wss://[^']+)'", script),
            "主題前綴": one(r"const PREFIX = '([^']+)'"),
            "主持人送狀態間隔ms": one(r"setInterval\(sendState, (\d+)\)"),
            "位置取樣間隔ms": one(r"samples\.shift\(\);\s*\}, (\d+)\);"),
            "跳轉門檻": one(r"const jumpAt = ([^;]+);"),
            "微調沒效幾次改跳轉": one(r"if \(rateFails >= (\d+)\) rateWorks = false"),
            "iPhone/Safari 一開始只用跳轉": one(r"let (rateWorks = !isSafariLike)"),
            "Safari 判斷": one(r"const isSafariLike = ([^;]+);"),
            "卡住判定ms": one(r"now - stuckSince > (\d+)"),
            "紅框出現時停止跳轉": "if (directTap) return;" in script,
            "對時頻率": one(r"setTimeout\(ping, ([^)]+)\)"),
        },
        "程式庫": {lib: hashlib.sha256(open(os.path.join(ROOT, lib), "rb").read()).hexdigest()[:16] for lib in libs},
        "測試門檻": {
            "同步誤差ms": (re.search(r"^TOL_MS = (\d+)", sync_test, re.M) or [None, None])[1],
            "Safari 同步誤差ms": one(r"Safari 核心的觀眾也同步 < (\d+)ms", sync_test),
        },
    }


def main():
    cur = extract()
    if "--update" in sys.argv:
        json.dump(cur, open(GOLDEN, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("已重生 golden：", GOLDEN); return 0
    if not os.path.exists(GOLDEN):
        print("FAIL 沒有 golden 檔，先跑 --update"); return 1
    gold = json.load(open(GOLDEN, encoding="utf-8"))
    fails = 0
    for grp, items in gold.items():
        for k, v in items.items():
            c = cur.get(grp, {}).get(k, "（不見了）")
            ok = c == v
            print(("PASS " if ok else "FAIL ") + f"golden {grp}／{k}" + ("" if ok else f"\n     golden：{v}\n     現在：  {c}"))
            fails += not ok
    for grp, items in cur.items():  # 新抽出的規格也要先進 golden
        for k in items:
            if k not in gold.get(grp, {}):
                print(f"FAIL golden 少了 {grp}／{k}（新規格要用 --update 收進來）"); fails += 1
    return 1 if fails else 0


sys.exit(main())

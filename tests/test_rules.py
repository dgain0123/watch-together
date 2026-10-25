"""靜態規則：不用開瀏覽器就能檢查的事。"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

# 外部程式庫一律寫死版本（不寫版本＝哪天自動更新就壞）
# 程式庫放在自己網站（外部網站偶爾慢到網頁出不來），檔名帶版本
srcs = re.findall(r'<script src="([^"]+)"', html)
check("程式庫都放在自己網站且檔名帶版本", len(srcs) == 2 and all(s.startswith("lib/") and re.search(r"-\d+\.\d+\.\d+\.min\.js$", s) and os.path.exists(os.path.join(ROOT, s)) for s in srcs))
# 使用者裁示（2026-10-25 晚）：觀眾一律靜音、不提供開聲音（iOS 12 從靜音切有聲音必暫停，AI 會議確認做不到）
check("沒有任何開聲音的按鈕（全部靜音開關、自己靜音鈕、點我開始觀看都拿掉）",
      'id="muteAll"' not in html and "selfMute" not in html and 'id="tapBtn"' not in html and "unMute(" not in html)
check("觀眾播放器一律靜音載入且持續保持靜音", "mute: 1 }" in html and "function keepMuted" in html)
# 兩台訊息伺服器同時連，一台掛了還能用
check("同時連兩台訊息伺服器", html.count("wss://") >= 2)
check("觀眾有全螢幕按鈕", 'id="fsBtn"' in html and 'id="fsExit"' in html)
# 使用者裁示（2026-10-25）：主持人網頁的 QR code 放在最上面（標題下第一塊）
host = html[html.index('<section id="host"'):html.index('</section>')]
check("主持人網頁 QR code 在最上面", host.index('id="qr"') < host.index('id="url"') < host.index('id="hostPlayer"'))
# 使用者裁示（2026-10-25）：不用自己貼網址，要有「一鍵貼上並播放」大按鈕
check("有一鍵貼上並播放按鈕", 'id="pasteGo"' in html and "clipboard.readText" in html)
# 使用者裁示（2026-10-25）：按結束放映後全部失效（觀眾斷線不再接、主持人換新 QR code）
check("有結束放映按鈕", 'id="endShow"' in html and "net.close()" in html and "wt_just_ended" in html)
check("錯誤會顯示在手機畫面上", 'id="err"' in html and "addEventListener('error'" in html)
# 2026-10-25 使用者的觀眾 iPhone 系統舊（iOS 13.4 以前），看不懂 ?? 等新寫法 → 整頁黑畫面。
# 網頁內的程式一律要能被只懂 ES2017 的解析器讀懂；外部程式庫也要用舊版相容版本。
try:
    import esprima
    for i, js in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
        try:
            esprima.parseScript(js); ok = True
        except Exception as e:
            ok = False; print("   ", e)
        check(f"第 {i+1} 段程式舊 iPhone 看得懂（ES2017）", ok)
except ImportError:
    check("需要 esprima（pip3 install --user esprima）", False)
check("連線程式庫用相容舊 iPhone 的 4.x 版", "lib/mqtt-4." in html)
try:
    for lib in srcs:
        esprima.parseScript(open(os.path.join(ROOT, lib), encoding="utf-8").read()); 
    check("程式庫本身舊 iPhone 也看得懂（ES2017）", True)
except Exception as e:
    check(f"程式庫本身舊 iPhone 也看得懂（ES2017）：{e}", False)
css = html[html.index("<style>"):html.index("</style>")]
check("版面不用舊 iPhone 不支援的 inset / aspect-ratio", "inset:" not in css and "aspect-ratio" not in css)
# ---- 2026-10-25 各修正的釘樁（完整來龍去脈見 詳解_修正紀錄.md）----
# 卡住偵測要「播放器說在播＋時間有在變」：iOS 12 實測播放器停在 -1 但跳轉讓時間一直變，只看時間會被騙
check("卡住偵測看播放器狀態（st===1）不只看時間", "if (st === 1 && ct !== lastCt" in html)
# 主畫面 App 會一直開「加入當下的網址」→ 以手機記住的房號為準，結束過的舊房間不能復活
check("主持人房號以手機記住的為準", "let room = safeGet('wt_host_room') || params.get('host');" in html)
# 診斷工具也用自架程式庫（unpkg 偶爾慢到開不起來）
tool = open(os.path.join(ROOT, "tools", "listen_diag.py"), encoding="utf-8").read()
check("診斷工具用自架 mqtt 程式庫", "mqtt-4.3.8.min.js" in tool and "unpkg" not in tool)
check("觀眾會回報狀態給診斷工具（含最近 10 秒紀錄）", "net.publish('diag'" in html and "trail: trail.slice()" in html)
# 觀眾一開頁就報到會碰到還沒建立的變數（TDZ）→ 第一次報到要延後
check("觀眾第一次報到延後（避免變數還沒建立）", "setTimeout(sayHello," in html)
sys.exit(1 if fails else 0)

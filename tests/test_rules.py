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
# 使用者裁示（2026-10-25）：靜音只由主持人控制，觀眾端不放靜音按鈕
check("觀眾端沒有自己的靜音按鈕", "selfMute" not in html and "我要靜音" not in html)
check("主持人有全部靜音開關", 'id="muteAll"' in html and "m: muteAll" in html)
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
sys.exit(1 if fails else 0)

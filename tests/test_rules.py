"""靜態規則：不用開瀏覽器就能檢查的事。"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond: fails.append(name)

# 外部程式庫一律寫死版本（不寫版本＝哪天自動更新就壞）
srcs = re.findall(r'<script src="([^"]+)"', html)
check("外部程式庫都有寫死版本", all(re.search(r"@\d+\.\d+\.\d+|/\d+\.\d+\.\d+/", s) for s in srcs) and len(srcs) == 2)
# 使用者裁示（2026-10-25）：靜音只由主持人控制，觀眾端不放靜音按鈕
check("觀眾端沒有自己的靜音按鈕", "selfMute" not in html and "我要靜音" not in html)
check("主持人有全部靜音開關", 'id="muteAll"' in html and "m: muteAll" in html)
# 兩台訊息伺服器同時連，一台掛了還能用
check("同時連兩台訊息伺服器", html.count("wss://") >= 2)
check("觀眾有全螢幕按鈕", 'id="fsBtn"' in html and 'id="fsExit"' in html)
# 使用者裁示（2026-10-25）：主持人網頁的 QR code 放在最上面（標題下第一塊）
host = html[html.index('<section id="host"'):html.index('</section>')]
check("主持人網頁 QR code 在最上面", host.index('id="qr"') < host.index('id="url"') < host.index('id="hostPlayer"'))
sys.exit(1 if fails else 0)

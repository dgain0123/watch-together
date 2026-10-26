"""實際開瀏覽器測：一台主持人＋兩台觀眾（時鐘故意調快 3 秒、調慢 1.7 秒），量同步誤差。
需要網路（YouTube＋公開訊息伺服器）。約 60 秒。"""
import asyncio, os, random, socket, subprocess, sys, time
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = "dQw4w9WgXcQ"
TOL_MS = 80          # 穩定播放時容許誤差（經公開訊息伺服器對時，去回程不對稱本身就有幾十毫秒誤差）
fails = []
def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name, flush=True)
    if not cond: fails.append(name)

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

async def video(p):
    for f in p.frames:
        if "youtube.com/embed" in f.url:
            return await f.evaluate("(()=>{const v=document.querySelector('video');return v?{t:v.currentTime,at:performance.timeOrigin+performance.now(),paused:v.paused,muted:v.muted,rate:v.playbackRate}:null})()")

async def diff_ms(h, v):
    H, V = await video(h), await video(v)
    if not H or not V: return None
    # 電腦上大家共用同一個真時鐘，換算到主持人讀值那一刻再比
    vt = V["t"] + (0 if V["paused"] else (H["at"] - V["at"]) / 1000 * V["rate"])
    return (vt - H["t"]) * 1000

async def host_play(h):
    """主持人按播放：影片可能還在載入，重試到真的在播。"""
    for _ in range(40):
        try:
            hf = [f for f in h.frames if "youtube.com/embed" in f.url][0]
            ok = await hf.evaluate("(()=>{const v=document.querySelector('video');if(!v)return false;try{const p=v.play();if(p&&p.catch)p.catch(()=>{})}catch(e){};return !v.paused&&v.currentTime>0})()")
            if ok: return hf
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("主持人影片播不起來")

async def median_diff(h, v, n=6, gap=0.8):
    """連續量幾次取中間值（跳轉校正的瞬間會停頓一下，單拍一張不準）"""
    xs = []
    for _ in range(n):
        x = await diff_ms(h, v)
        if x is not None: xs.append(x)
        await asyncio.sleep(gap)
    return sorted(xs)[len(xs) // 2] if xs else None

async def wait_stable(h, vs, secs=8):
    await asyncio.sleep(max(0, secs - 4))
    return list(await asyncio.gather(*[median_diff(h, v, n=5, gap=0.8) for v in vs]))

async def main():
    port = free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=ROOT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    U, room = f"http://localhost:{port}/", "t" + str(random.randint(10**5, 10**6))
    try:
        async with async_playwright() as pw:
            b = await pw.chromium.launch()  # 預設自動播放規則＝跟手機一樣，沒點過只能靜音播
            mob = {k: v for k, v in pw.devices["iPhone 13"].items() if k != "default_browser_type"}
            andr = {k: v for k, v in pw.devices["Pixel 5"].items() if k != "default_browser_type"}  # Chrome 觀眾＝Android 流程
            h = await (await b.new_context(**mob)).new_page()
            await h.goto(U + "?host=" + room, wait_until="domcontentloaded")
            dialogs = []
            def on_dialog(dlg):
                dialogs.append(dlg.message); asyncio.ensure_future(dlg.accept())
            h.on("dialog", on_dialog)
            for _ in range(30):  # 公開訊息伺服器有時連得慢，最多等 15 秒
                if "已連線" in await h.inner_text("#hostStatus"): break
                await asyncio.sleep(0.5)
            check("主持人連上訊息伺服器", "已連線" in await h.inner_text("#hostStatus"))
            # 一鍵貼上並播放：模擬在 YouTube 按「複製連結」的分享文字
            await h.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=U.rstrip("/"))
            await h.evaluate(f"navigator.clipboard.writeText('https://youtu.be/{VID}?si=abc123')")
            await h.click("#pasteGo")
            await asyncio.sleep(1)
            check("一鍵貼上並播放：讀到剪貼簿的連結", VID in await h.input_value("#url"))
            hf = await host_play(h)

            vs = []
            for skew in (3000, -1700):
                c = await b.new_context(**andr)
                await c.add_init_script(f"(()=>{{const D=Date.now.bind(Date);Date.now=()=>D()+({skew});}})()")
                v = await c.new_page(); await v.goto(U + "?room=" + room, wait_until="domcontentloaded"); vs.append(v)
            # 使用者裁示（2026-10-25）：觀眾一律靜音、不用點任何東西就自動開始
            d = await wait_stable(h, vs, 16)  # 對時前 15 秒每秒一次、挑最準的那次，太早量會量到還沒對準的
            check(f"觀眾不用點就自動開始、同步誤差 < {TOL_MS}ms（時鐘偏 +3s／-1.7s）：{d}", all(x is not None and abs(x) < TOL_MS for x in d))
            Vs = [await video(v) for v in vs]
            check("觀眾一律靜音", all(x and x["muted"] for x in Vs))

            await hf.evaluate("(()=>{const v=document.querySelector('video');v.currentTime+=20})()")
            d = await wait_stable(h, vs, 9)  # 跳轉後偶爾要 6 秒以上才收斂
            check(f"主持人跳 20 秒後跟上：{d}", all(x is not None and abs(x) < TOL_MS for x in d))

            await hf.evaluate("document.querySelector('video').pause()")
            await asyncio.sleep(3)
            Vs = [await video(v) for v in vs]; d = [await diff_ms(h, v) for v in vs]
            check(f"主持人暫停→觀眾也停在同一格：{d}", all(x["paused"] for x in Vs) and all(abs(x) < 50 for x in d))
            hf = await host_play(h)

            # 全螢幕（模擬 iPhone：沒有真全螢幕功能）
            v = vs[0]
            await v.evaluate("delete Element.prototype.requestFullscreen")
            await v.click("#fsBtn"); await asyncio.sleep(0.8)
            r = await v.evaluate("(()=>{const r=document.getElementById('viewerWrap').getBoundingClientRect();return [r.width,r.height]})()")
            vp = v.viewport_size
            check(f"全螢幕鋪滿畫面 {r} vs {vp}", abs(r[0] - vp["width"]) < 2 and abs(r[1] - vp["height"]) < 2)
            await v.click("#fsExit"); await asyncio.sleep(0.5)
            check("離開全螢幕", "fs" not in await v.evaluate("document.body.className"))
            # 主持人（iPhone 尺寸）全螢幕再縮回來：影片不能停（2026-10-26 使用者要求）
            await h.evaluate("delete Element.prototype.requestFullscreen")
            await h.click("#hostFsBtn"); await asyncio.sleep(0.8)
            r = await h.evaluate("(()=>{const r=document.getElementById('hostWrap').getBoundingClientRect();return [r.width,r.height]})()")
            hvp = h.viewport_size
            check(f"主持人全螢幕鋪滿畫面 {r} vs {hvp}", abs(r[0] - hvp["width"]) < 2 and abs(r[1] - hvp["height"]) < 2)
            await h.click("#hostFsExit"); await asyncio.sleep(1)
            H1 = await video(h); await asyncio.sleep(1); H2 = await video(h)
            check("主持人離開全螢幕：影片繼續播沒有暫停", "fs" not in await h.evaluate("document.body.className")
                  and H1 and H2 and not H2["paused"] and H2["t"] > H1["t"] + 0.5)
            # 直接貼進輸入框也會自動開始（換一部影片）
            await h.evaluate("(()=>{const el=document.getElementById('url');el.value='https://www.youtube.com/watch?v=9bZkp7q19f0';el.dispatchEvent(new Event('paste'))})()")
            ok = False
            for _ in range(20):  # 換成另一部長度 4 分多的影片，觀眾的影片長度跟著變
                await asyncio.sleep(0.5)
                d2 = [await f.evaluate("(()=>{const v=document.querySelector('video');return v?v.duration:0})()") for f in vs[1].frames if "youtube.com/embed" in f.url]
                if d2 and 240 < d2[0] < 260: ok = True; break
            check("貼進輸入框就自動開始，觀眾跟著換影片", ok)
            # iPhone 擋住網頁替觀眾按播放 → 拿掉遮罩、提示觀眾直接點影片；點了之後照常同步
            bp = await (await b.new_context(**andr)).new_page()
            await bp.goto(U + "?room=" + room, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            # 模擬 iOS 12 實測：叫播放沒反應、播放器一直「還沒開始」，但跳轉會讓時間數字跟著變
            await bp.evaluate("""(()=>{const p=__wt.player; window.__o=[p.playVideo,p.seekTo,p.getCurrentTime,p.getPlayerState];
              let fake=0; p.playVideo=()=>{}; p.seekTo=(t)=>{fake=t}; p.getCurrentTime=()=>fake; p.getPlayerState=()=>-1;})()""")
            for f in bp.frames:  # 真實情況是影片根本沒開始播：把已經在播的影片真的停住
                if "youtube.com/embed" in f.url:
                    await f.evaluate("(()=>{const v=document.querySelector('video'); if(v) v.pause();})()")
            ok = False
            for _ in range(16):
                await asyncio.sleep(0.5)
                if await bp.is_visible("#tapHint"): ok = True; break
            check("播放被手機擋住→出現「請直接點一下影片」且遮罩拿掉", ok and not await bp.is_visible("#shield"))
            await bp.evaluate("(()=>{const p=__wt.player; p.playVideo=__o[0]; p.seekTo=__o[1]; p.getCurrentTime=__o[2]; p.getPlayerState=__o[3];})()")
            await bp.click("#viewerWrap")  # 觀眾用手指點影片正中間
            for _ in range(20):
                B = await video(bp)
                if B and not B["paused"] and B["t"] > 0: break
                await asyncio.sleep(0.5)
            await asyncio.sleep(5)
            dd = await median_diff(h, bp)
            if dd is None or abs(dd) >= TOL_MS:
                print("  被擋觀眾診斷:", await bp.is_visible("#tapHint"), await bp.is_visible("#shield"), await video(bp),
                      await bp.evaluate("(()=>{const p=__wt.player;return {st:p.getPlayerState(),ct:p.getCurrentTime(),dt:__wt.directTap}})()"))
            check(f"觀眾自己點影片後遮罩蓋回、照常同步（{dd}）", not await bp.is_visible("#tapHint") and await bp.is_visible("#shield") and dd is not None and abs(dd) < TOL_MS)

            # Safari 核心的觀眾（改速度沒效果的那種）也要對得上
            wb = await pw.webkit.launch()
            wv = await (await wb.new_context(**mob)).new_page()
            await wv.goto(U + "?room=" + room, wait_until="domcontentloaded"); await asyncio.sleep(4)
            # iPhone（Safari 核心）也不用點就自動靜音播放
            ok = False
            for _ in range(20):
                V = await video(wv)
                if V and not V["paused"] and V["t"] > 0: ok = True; break
                await asyncio.sleep(0.5)
            check("iPhone 觀眾不用點就自動開始、靜音、沒有紅框", ok and V["muted"] and not await wv.is_visible("#tapHint"))
            await asyncio.sleep(16)  # 等對時做完（前 15 秒每秒一次）再量
            dw = await median_diff(h, wv)
            if dw is None or abs(dw) >= 100:
                print("  Safari 觀眾診斷:", await video(wv), await video(h), await wv.inner_text("#viewerStatus"), await wv.inner_text("#err"),
                      await wv.evaluate("(()=>{const p=__wt.player;return p&&p.getPlayerState?{st:p.getPlayerState(),ct:p.getCurrentTime(),rw:__wt.rateWorks,dt:__wt.directTap}:null})()"), )
            # Safari 只能用跳轉校正（差 0.08 秒以上才跳，太常跳畫面會頓），所以標準放 0.1 秒
            check(f"Safari 核心的觀眾也同步 < 100ms（{dw}）", dw is not None and abs(dw) < 100)

            # 結束放映＝全部失效：觀眾停止並斷線、舊 QR code 作廢、主持人換新 QR code
            await h.click("#endShow")
            ok = False
            for _ in range(12):
                await asyncio.sleep(0.5)
                if all([await v.is_visible("#ended") for v in vs + [wv]]): ok = True; break
            Vs = [await video(v) for v in vs]
            check("結束放映→觀眾都顯示「主持人已結束放映」且停止", ok and all(x is None or x["paused"] or x["t"] == 0 for x in Vs))
            await asyncio.sleep(2)
            new_room = h.url.split("host=")[1]
            check(f"主持人自動換成新房間（{room}→{new_room}）且有提示", new_room != room and "失效" in await h.inner_text("#endHint"))
            # 主畫面 App 情境：用「舊網址」重新打開主持人頁面，也要自動換到新房間、不能讓舊房間復活
            await h.goto(U + "?host=" + room, wait_until="domcontentloaded"); await asyncio.sleep(2)
            check(f"用舊網址打開主持人頁面→自動用新房間（{h.url.split('host=')[1]}）", h.url.split("host=")[1] == new_room)
            late = await (await b.new_context(**mob)).new_page()
            await late.goto(U + "?room=" + room, wait_until="domcontentloaded"); await asyncio.sleep(4)
            check("結束後才掃舊 QR code 的人只看到已結束", await late.is_visible("#ended"))
            # 主持人在新房間再播放：舊觀眾不會接上
            await asyncio.sleep(2)
            await h.evaluate("(()=>{const el=document.getElementById('url');el.value='https://youtu.be/dQw4w9WgXcQ';el.dispatchEvent(new Event('paste'))})()")
            await host_play(h)
            await asyncio.sleep(5)
            Vs = [await video(v) for v in vs]
            check("新房間播放時舊觀眾仍是結束、不會跟著播", all([await v.is_visible("#ended") for v in vs]) and all(x is None or x["paused"] or x["t"] < 1 for x in Vs))
            await wb.close()
            await b.close()
    finally:
        srv.kill()

asyncio.run(asyncio.wait_for(main(), 300))  # 最多 5 分鐘，不准卡死
sys.exit(1 if fails else 0)

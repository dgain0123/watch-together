"""實際開瀏覽器測：一台主持人＋兩台觀眾（時鐘故意調快 3 秒、調慢 1.7 秒），量同步誤差。
需要網路（YouTube＋公開訊息伺服器）。約 60 秒。"""
import asyncio, os, random, socket, subprocess, sys, time
from playwright.async_api import async_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VID = "dQw4w9WgXcQ"
TOL_MS = 60          # 穩定播放時容許誤差
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
            ok = await hf.evaluate("(async()=>{const v=document.querySelector('video');if(!v)return false;try{await v.play()}catch(e){};return !v.paused&&v.currentTime>0})()")
            if ok: return hf
        except Exception:
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError("主持人影片播不起來")

async def wait_stable(h, vs, secs=8):
    await asyncio.sleep(secs)
    return [await diff_ms(h, v) for v in vs]

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
            h = await (await b.new_context(**mob)).new_page()
            await h.goto(U + "?host=" + room, wait_until="domcontentloaded")
            await asyncio.sleep(3)
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
                c = await b.new_context(**mob)
                await c.add_init_script(f"(()=>{{const D=Date.now.bind(Date);Date.now=()=>D()+({skew});}})()")
                v = await c.new_page(); await v.goto(U + "?room=" + room, wait_until="domcontentloaded"); vs.append(v)
            for v in vs: await v.click("#tapBtn")

            d = await wait_stable(h, vs, 10)
            check(f"播放同步誤差 < {TOL_MS}ms（時鐘偏 +3s／-1.7s）：{d}", all(x is not None and abs(x) < TOL_MS for x in d))
            V = await video(vs[0])
            check("觀眾點過開始後有聲音", V and not V["muted"])

            await hf.evaluate("(()=>{const v=document.querySelector('video');v.currentTime+=20})()")
            d = await wait_stable(h, vs, 9)  # 跳轉後偶爾要 6 秒以上才收斂
            check(f"主持人跳 20 秒後跟上：{d}", all(x is not None and abs(x) < TOL_MS for x in d))

            await hf.evaluate("document.querySelector('video').pause()")
            await asyncio.sleep(3)
            Vs = [await video(v) for v in vs]; d = [await diff_ms(h, v) for v in vs]
            check(f"主持人暫停→觀眾也停在同一格：{d}", all(x["paused"] for x in Vs) and all(abs(x) < 50 for x in d))
            hf = await host_play(h)

            # 主持人全部靜音：新觀眾不用點就直接靜音播放；關掉後要點一下才出聲
            await h.click("#muteAll")
            await asyncio.sleep(2)
            Vs = [await video(v) for v in vs]
            check("全部靜音→舊觀眾都變靜音", all(x["muted"] for x in Vs))
            nv = await (await b.new_context(**mob)).new_page(); await nv.goto(U + "?room=" + room, wait_until="domcontentloaded")
            await asyncio.sleep(10)
            N = await video(nv); dn = await diff_ms(h, nv)
            check(f"全部靜音時新觀眾不用點就開始播（靜音、同步 {dn}）",
                  N and not N["paused"] and N["muted"] and not await nv.is_visible("#tap") and dn is not None and abs(dn) < TOL_MS)
            await h.click("#muteAll")
            for _ in range(12):  # 公開訊息伺服器偶爾慢到 2 秒以上，最多等 6 秒
                await asyncio.sleep(0.5)
                Vs = [await video(v) for v in vs]
                if all(not x["muted"] for x in Vs) and await nv.is_visible("#tap"): break
            check("關掉全部靜音→點過的觀眾恢復聲音", all(not x["muted"] for x in Vs))
            if not await nv.is_visible("#tap"):
                print("  診斷 nv:", await nv.inner_text("#viewerStatus"), await nv.inner_text("#err"), await video(nv),
                      await nv.evaluate("(()=>{const p=__wt.player;return {st:p.getPlayerState(),muted:p.isMuted(),dt:__wt.directTap}})()"),
                      "ended", await nv.is_visible("#ended"), "hint", await nv.is_visible("#tapHint"))
            check("關掉全部靜音→沒點過的觀眾跳出「點一下聽聲音」", await nv.is_visible("#tap"))
            await nv.click("#tapBtn"); await asyncio.sleep(1.5)
            N = await video(nv)
            check("沒點過的觀眾點一下後有聲音且繼續播", N and not N["muted"] and not N["paused"])

            # 全螢幕（模擬 iPhone：沒有真全螢幕功能）
            v = vs[0]
            await v.evaluate("delete Element.prototype.requestFullscreen")
            await v.click("#fsBtn"); await asyncio.sleep(0.8)
            r = await v.evaluate("(()=>{const r=document.getElementById('viewerWrap').getBoundingClientRect();return [r.width,r.height]})()")
            vp = v.viewport_size
            check(f"全螢幕鋪滿畫面 {r} vs {vp}", abs(r[0] - vp["width"]) < 2 and abs(r[1] - vp["height"]) < 2)
            await v.click("#fsExit"); await asyncio.sleep(0.5)
            check("離開全螢幕", "fs" not in await v.evaluate("document.body.className"))
            # 直接貼進輸入框也會自動開始（換一部影片）
            await h.evaluate("(()=>{const el=document.getElementById('url');el.value='https://www.youtube.com/watch?v=9bZkp7q19f0';el.dispatchEvent(new Event('paste'))})()")
            ok = False
            for _ in range(20):  # 換成另一部長度 4 分多的影片，觀眾的影片長度跟著變
                await asyncio.sleep(0.5)
                d2 = [await f.evaluate("(()=>{const v=document.querySelector('video');return v?v.duration:0})()") for f in vs[1].frames if "youtube.com/embed" in f.url]
                if d2 and 240 < d2[0] < 260: ok = True; break
            check("貼進輸入框就自動開始，觀眾跟著換影片", ok)
            # iPhone 擋住網頁替觀眾按播放 → 拿掉遮罩、提示觀眾直接點影片；點了之後照常同步
            bp = await (await b.new_context(**mob)).new_page()
            await bp.goto(U + "?room=" + room, wait_until="domcontentloaded")
            await asyncio.sleep(4)
            await bp.evaluate("(()=>{const p=__wt.player; window.__o=[p.playVideo,p.seekTo]; p.playVideo=()=>{}; p.seekTo=()=>{};})()")  # 模擬 iPhone：網頁叫播放、跳轉都沒反應
            await bp.click("#tapBtn")
            ok = False
            for _ in range(16):
                await asyncio.sleep(0.5)
                if await bp.is_visible("#tapHint"): ok = True; break
            check("播放被手機擋住→出現「請直接點一下影片」且遮罩拿掉", ok and not await bp.is_visible("#shield"))
            await bp.evaluate("(()=>{const p=__wt.player; p.playVideo=__o[0]; p.seekTo=__o[1];})()")
            await host_play(bp)  # 觀眾自己點影片（同一個「重試到真的在播」）
            await asyncio.sleep(8)
            dd = await diff_ms(h, bp)
            check(f"觀眾自己點影片後遮罩蓋回、照常同步（{dd}）", not await bp.is_visible("#tapHint") and await bp.is_visible("#shield") and dd is not None and abs(dd) < TOL_MS)

            # Safari 核心的觀眾（改速度沒效果的那種）也要對得上
            wb = await pw.webkit.launch()
            wv = await (await wb.new_context(**mob)).new_page()
            await wv.goto(U + "?room=" + room, wait_until="domcontentloaded"); await asyncio.sleep(4)
            await wv.tap("#tapBtn")
            await asyncio.sleep(16)
            dw = await diff_ms(h, wv)
            if dw is None or abs(dw) >= TOL_MS:
                print("  Safari 觀眾診斷:", await video(wv), await video(h), await wv.inner_text("#viewerStatus"), await wv.inner_text("#err"),
                      await wv.evaluate("(()=>{const p=__wt.player;return p&&p.getPlayerState?{st:p.getPlayerState(),ct:p.getCurrentTime(),rw:__wt.rateWorks,dt:__wt.directTap}:null})()"), "tap可見", await wv.is_visible("#tap"))
            check(f"Safari 核心的觀眾也同步（{dw}）", dw is not None and abs(dw) < TOL_MS)

            # 結束放映＝全部失效：觀眾停止並斷線、舊 QR code 作廢、主持人換新 QR code
            h.on("dialog", lambda dlg: asyncio.ensure_future(dlg.accept()))
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

asyncio.run(asyncio.wait_for(main(), 180))  # 最多 3 分鐘，不准卡死
sys.exit(1 if fails else 0)

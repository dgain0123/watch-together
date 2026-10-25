"""收觀眾手機回報的狀態（除錯用）：python3 tools/listen_diag.py [秒數]，印出所有房間的 diag 訊息。"""
import asyncio, json, sys, time
from playwright.async_api import async_playwright
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 600
HTML = """<script src="https://unpkg.com/mqtt@5.10.1/dist/mqtt.min.js"></script><script>
for (const u of ['wss://broker.emqx.io:8084/mqtt','wss://broker.hivemq.com:8884/mqtt']) {
  const c = mqtt.connect(u, {clientId:'diag_'+Math.random().toString(36).slice(2)});
  c.on('connect', () => { c.subscribe('dgain0123-watch-together/v1/+/diag'); console.log('connected ' + u); });
  c.on('message', (t, p) => console.log('DIAG ' + t.split('/')[2] + ' ' + p.toString()));
}</script>"""
async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch(); p = await b.new_page()
        seen = {}
        def on(m):
            t = m.text
            if t.startswith('DIAG '):
                _, room, js = t.split(' ', 2); d = json.loads(js)
                key = (d['id'], d['at'])
                if key in seen: return
                seen[key] = 1
                print(time.strftime('%H:%M:%S'), room, json.dumps(d, ensure_ascii=False), flush=True)
            else:
                print(t, flush=True)
        p.on('console', on)
        await p.goto('about:blank'); await p.set_content(HTML)
        await asyncio.sleep(SECS)
asyncio.run(main())

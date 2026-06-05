"""
Génération PDF via Chrome CDP — Guide Pipeline Auto NotebookLM
"""
import subprocess, time, json, base64, urllib.request, sys, threading
import websocket

CHROME  = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
HTML    = r"C:\Users\levan\AppData\Roaming\Claude\local-agent-mode-sessions\93b51d0b-0806-48de-b7a8-1b4cb9a96909\43571d99-7689-40c9-980a-0889cd24834a\local_777f35aa-69a0-4f29-9077-75eed984cda0\outputs\guide_pipeline_auto_notebooklm.html"
OUT_PDF = r"C:\Users\levan\AppData\Roaming\Claude\local-agent-mode-sessions\93b51d0b-0806-48de-b7a8-1b4cb9a96909\43571d99-7689-40c9-980a-0889cd24834a\local_777f35aa-69a0-4f29-9077-75eed984cda0\outputs\guide_pipeline_auto_notebooklm.pdf"
PORT    = 9229

FOOTER = (
    '<div style="width:100%;font-size:8px;font-family:Arial,sans-serif;'
    'color:#1B3A5C;display:flex;justify-content:space-between;'
    'padding:3px 14mm 0;box-sizing:border-box;'
    'border-top:1pt solid #C9A84C;">'
    '<span>Christian Levannier &nbsp;&middot;&nbsp; Pipeline Auto NotebookLM</span>'
    '<span>31 mai 2026 &nbsp;&middot;&nbsp; Page '
    '<span class="pageNumber"></span>'
    ' / <span class="totalPages"></span></span>'
    '</div>'
)

PRINT_PARAMS = {
    "displayHeaderFooter": True,
    "headerTemplate": "<div></div>",
    "footerTemplate": FOOTER,
    "printBackground": True,
    "paperWidth":  8.27,
    "paperHeight": 11.69,
    "marginTop":    0,
    "marginBottom": 0.4,
    "marginLeft":   0,
    "marginRight":  0,
    "preferCSSPageSize": True
}

proc = subprocess.Popen([
    CHROME,
    f"--remote-debugging-port={PORT}",
    "--remote-allow-origins=*",
    "--headless",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-extensions",
    "about:blank"
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

time.sleep(4)

try:
    for attempt in range(5):
        try:
            tabs_raw = urllib.request.urlopen(f"http://localhost:{PORT}/json", timeout=5).read()
            tabs = json.loads(tabs_raw)
            break
        except Exception as e:
            print(f"Tentative {attempt+1}: {e}")
            time.sleep(2)
    else:
        print("ERREUR: Chrome ne répond pas")
        sys.exit(1)

    ws_url = next((t["webSocketDebuggerUrl"] for t in tabs if t.get("type") == "page"), None)
    if not ws_url:
        print("ERREUR: aucune page trouvée")
        sys.exit(1)

    print(f"WebSocket: {ws_url[:80]}")

    result = [None]
    done   = threading.Event()
    page_loaded = [False]
    msg_id = [0]

    def send(ws_conn, method, params=None, mid=None):
        if mid is None:
            msg_id[0] += 1; mid = msg_id[0]
        ws_conn.send(json.dumps({"id": mid, "method": method, "params": params or {}}))

    def on_open(ws_conn):
        print("WS ouvert — activation Page.enable")
        send(ws_conn, "Page.enable", mid=1)
        time.sleep(0.5)
        send(ws_conn, "Page.navigate", {"url": f"file:///{HTML}"}, mid=10)

    def on_message(ws_conn, message):
        data = json.loads(message)
        if data.get("method") == "Page.loadEventFired" and not page_loaded[0]:
            page_loaded[0] = True
            print("Page chargée — printToPDF...")
            time.sleep(1.5)
            send(ws_conn, "Page.printToPDF", PRINT_PARAMS, mid=99)
        if data.get("id") == 99:
            result[0] = data.get("result", {})
            done.set()

    def on_error(ws_conn, error):
        print(f"WS erreur: {error}")

    ws = websocket.WebSocketApp(ws_url, on_open=on_open, on_message=on_message, on_error=on_error)
    t = threading.Thread(target=ws.run_forever)
    t.daemon = True
    t.start()

    if done.wait(timeout=60):
        pdf_b64 = result[0].get("data", "") if result[0] else ""
        if pdf_b64:
            pdf_bytes = base64.b64decode(pdf_b64)
            with open(OUT_PDF, "wb") as f:
                f.write(pdf_bytes)
            print(f"\nOK PDF généré : {len(pdf_bytes):,} bytes -> {OUT_PDF}")
        else:
            print(f"ERREUR données vides : {result[0]}")
    else:
        print(f"TIMEOUT 60s — page_loaded: {page_loaded[0]}")

    ws.close()

finally:
    proc.terminate()
    proc.wait()
    print("Chrome terminé")

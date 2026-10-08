// Шаги по CDP на открытой вкладке headless Chrome — с настоящей мышью (Input.dispatchMouseEvent), чего нет в помощнике
// хаба: {"go": адрес} {"eval": выражение} {"until": выражение, "ms": 5000} {"sleep": мс}
// {"press": селектор} — нажать мышью в центр элемента   {"type": текст} — набрать в поле с фокусом
// {"mouse": "down|move|up", "at": выражение → [x, y]} — шаг мыши с зажатой левой кнопкой
// {"shot": файл, "width": 1300, "height": 900} — снимок экрана. Печатает JSON-список результатов.
const [port, stepsJson] = process.argv.slice(2);
const tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
const ws = new WebSocket(tabs.find((t) => t.type === "page").webSocketDebuggerUrl);
let id = 0;
const wait = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && wait.has(d.id)) { wait.get(d.id)(d); wait.delete(d.id); } };
await new Promise((r) => (ws.onopen = r));
const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const js = async (expr) => (await send("Runtime.evaluate", { expression: expr, returnByValue: true, awaitPromise: true })).result.result?.value;
const mouse = (type, [x, y], buttons = 1) => send("Input.dispatchMouseEvent", { type, x, y, button: type === "mouseMoved" && !buttons ? "none" : "left", buttons, clickCount: 1 });
const out = [];
for (const s of JSON.parse(stepsJson)) {
  if (s.sleep) { await sleep(s.sleep); out.push({ sleep: s.sleep }); }
  else if (s.eval) out.push({ eval: await js(s.eval) });
  else if (s.until) {
    const end = Date.now() + (s.ms || 5000);
    let v = await js(s.until);
    while (!v && Date.now() < end) { await sleep(100); v = await js(s.until); }
    out.push({ until: v });
  } else if (s.go) {
    await send("Page.enable");
    await send("Page.addScriptToEvaluateOnNewDocument", { source: "try { localStorage.setItem('hub.feed', 'full') } catch {}" });
    if (s.width) await send("Emulation.setDeviceMetricsOverride", { width: s.width, height: s.height || 900, deviceScaleFactor: 1, mobile: s.width < 600 });
    await send("Page.navigate", { url: s.go });
    out.push({ go: s.go });
  } else if (s.press) {
    const at = await js(`(() => { const n = document.querySelector(${JSON.stringify(s.press)}); if (!n) return null;
      n.scrollIntoView({ block: "center" }); const r = n.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()`);
    if (at) { await mouse("mouseMoved", at, 0); await mouse("mousePressed", at); await mouse("mouseReleased", at, 0); }
    out.push({ press: s.press, ok: !!at });
  } else if (s.mouse) {
    const at = await js(s.at);
    await mouse({ down: "mousePressed", move: "mouseMoved", up: "mouseReleased" }[s.mouse], at, s.mouse === "up" ? 0 : 1);
    out.push({ mouse: s.mouse, at });
  } else if (s.type) {
    await send("Input.insertText", { text: s.type });
    out.push({ type: s.type });
  } else if (s.shot) {
    await send("Emulation.setDeviceMetricsOverride", { width: s.width || 1300, height: s.height || 900, deviceScaleFactor: s.scale || 1, mobile: (s.width || 1300) < 600 });
    await sleep(400);
    const r = await send("Page.captureScreenshot", { format: "png" });
    (await import("node:fs")).writeFileSync(s.shot, Buffer.from(r.result.data, "base64"));
    out.push({ shot: s.shot });
  }
}
console.log(JSON.stringify(out));
ws.close();

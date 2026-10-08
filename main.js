// Быстрые ответы — плагин страницы хаба (EXTENDING.md, API 1.1).
// 1. Карточка вопроса сессии: вариант — кнопка, нажатие сразу отправляет ответ. Общая «Ответить» остаётся только там,
//    где выбирают несколько вариантов. Свой ответ — поле с кнопкой отправки справа.
// 2. Лента пересобирается на каждом снимке ядра, и выделение текста в ней пропадало, пока сессии работают: плагин
//    возвращает его в новую ленту, а нажатие, которым закончили выделять, не сворачивает строку.
// Карточку рисует хаб; плагин только меняет её вид и жмёт её же форму — ответ уходит тем же путём, что и раньше.

const CARD = "form.ask-card";
const FEED = "main .feed";

export default function register(hub) {
  hub.addStyle("quick.css");
  const main = document.getElementById("main");
  if (!main) return;
  quickCards(hub, main);
  keepSelection(main);
}

// ——— карточки вопросов ———

function quickCards(hub, main) {
  const scan = () => { for (const f of main.querySelectorAll(`${CARD}:not([data-quick])`)) upgrade(f, hub); };
  new MutationObserver(scan).observe(main, { childList: true, subtree: true });   // до отрисовки: карточка не мигает
  scan();
}

// выделяли текст варианта — это не ответ
const selecting = (node) => { const s = getSelection(); return !s.isCollapsed && s.containsNode(node, true); };

function upgrade(f, hub) {
  f.dataset.quick = "1";
  const sets = [...f.querySelectorAll("fieldset")];
  const multi = sets.some((fs) => fs.querySelector("input[type=checkbox]"));
  f.classList.add("quick");
  f.classList.toggle("quick-multi", multi);
  const answered = (fs) => !!(fs.querySelector("input:checked") || fs.querySelector("textarea.other")?.value.trim());
  for (const fs of sets) {
    const own = fs.querySelector("textarea.other");
    const radios = [...fs.querySelectorAll("label.opt input[type=radio]")];
    for (const box of radios) {
      const lab = box.closest("label");
      box.tabIndex = -1;   // кнопка — сам вариант: стрелки по скрытым радио не должны отвечать за владельца
      lab.tabIndex = 0;
      lab.setAttribute("role", "button");
      const pick = () => {
        if (f.dataset.sending) return;
        box.checked = true;
        if (own && own.value) { own.value = ""; own.dispatchEvent(new Event("input")); }   // ответ — вариант, не набранное
        if (!multi && sets.every(answered)) f.requestSubmit();   // вопросов несколько — уйдёт с ответом на последний
      };
      lab.addEventListener("click", (e) => {
        if (e.target.closest("a")) return;   // ссылка на файл в описании варианта — открыть, не отвечать
        e.preventDefault();
        if (!selecting(lab)) pick();
      });
      lab.addEventListener("keydown", (e) => {
        if (e.target === lab && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(); }
      });
    }
    if (own) ownAnswer(f, own, radios, hub);
  }
}

// свой ответ: поле и кнопка отправки справа от него
function ownAnswer(f, own, radios, hub) {
  const wrap = hub.el("div", "quick-own"), send = hub.el("button", "btn primary quick-send");
  send.type = "button";
  send.title = "Отправить свой ответ (Enter)";
  send.setAttribute("aria-label", "Отправить свой ответ");
  send.append(hub.icon("send"));
  send.disabled = !own.value.trim();
  own.replaceWith(wrap);
  wrap.append(own, send);
  own.addEventListener("input", () => {
    send.disabled = !own.value.trim();
    if (own.value.trim()) for (const r of radios) r.checked = false;   // набрали своё — вариант снят
  });
  send.addEventListener("click", () => f.requestSubmit());
}

// ——— выделение текста в ленте ———

function keepSelection(main) {
  let kept = null;   // {feed, from, to}: где выделение стояло в ленте — путь по номерам детей, смещение, текст узла
  const feedOf = (n) => (n?.nodeType === 1 ? n : n?.parentElement)?.closest(FEED) || null;
  const spot = (feed, node, offset) => {
    const path = [];
    for (let n = node; n !== feed; n = n.parentNode) path.unshift([...n.parentNode.childNodes].indexOf(n));
    return { path, offset, text: node.nodeValue };
  };
  const find = (feed, at) => {
    const node = at.path.reduce((n, i) => n?.childNodes[i], feed);
    return node && node.nodeValue === at.text ? node : null;   // на этом месте теперь другое — не выделять чужое
  };

  document.addEventListener("selectionchange", () => {
    const s = getSelection();
    const feed = s.isCollapsed ? null : feedOf(s.anchorNode);
    if (feed && feed === feedOf(s.focusNode)) {
      kept = { feed, from: spot(feed, s.anchorNode, s.anchorOffset), to: spot(feed, s.focusNode, s.focusOffset) };
    } else if (kept?.feed.isConnected) {
      kept = null;   // сняли сами; если же ленту пересобрали — вернём ниже
    }
  });

  new MutationObserver(() => {
    if (!kept || kept.feed.isConnected) return;
    const was = kept, feed = main.querySelector(".feed");
    kept = null;
    if (!feed) return;
    const from = find(feed, was.from), to = find(feed, was.to);
    if (!from || !to) return;
    try { getSelection().setBaseAndExtent(from, was.from.offset, to, was.to.offset); } catch { return; }
    kept = { ...was, feed };
  }).observe(main, { childList: true });

  // выделяли мышью по строке шага — отпускание не должно её сворачивать или раскрывать (и перерисовывать ленту)
  document.addEventListener("click", (e) => {
    const t = e.target.nodeType === 1 ? e.target : e.target.parentElement;
    if (!t?.closest(FEED) || t.closest("a, button, input, textarea, select, label, summary, img")) return;
    const s = getSelection();
    if (!s.isCollapsed && s.containsNode(t.closest(".row") || t, true)) e.stopPropagation();
  }, true);
}

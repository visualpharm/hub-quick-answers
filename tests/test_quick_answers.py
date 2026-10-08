"""Плагин на настоящей странице хаба: headless Chrome, страница на временном журнале (помощники — из тестов хаба),
мышь — настоящими событиями ввода. Запуск: python3 tests/test_quick_answers.py (код хаба — HUB_CORE, иначе
~/projects/agents-hub-core). Что проверяется — жалобы владельца 08.10:
- «чтобы были не радиокнопки и сабмит, а сразу нажималась опция, и она уже отправлялась; сабмит — только для инпута,
  и справа от инпута»;
- «не могу в чате выделять текст — он как-то сразу выделяется, и ничего не копируется»: лента пересобирается на
  каждом снимке ядра, выделение пропадало."""
import json
import os
import shutil
import signal
import subprocess
import sys
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HUB = os.environ.get("HUB_CORE") or os.path.expanduser("~/projects/agents-hub-core")
sys.path.insert(0, HUB)

import tests  # noqa: E402, F401 — тесты хаба: своя папка состояния и настройки, не машины
from tests import test_web_e2e  # noqa: E402

CDP = os.path.join(PLUGIN, "tests", "cdp.mjs")
WITH_PLUGIN = os.environ.get("QUICK_OFF") != "1"   # QUICK_OFF=1 — та же страница без плагина: видно, что чинит он
ONE = [{"question": "Выкатываем?", "options": [{"label": "Да", "description": "сегодня"}, {"label": "Позже"}]}]
TWO = ONE + [{"question": "Куда?", "options": [{"label": "Стенд"}, {"label": "Прод"}]}]
MANY = [{"question": "Что проверить?", "multiSelect": True, "options": [{"label": "Тесты"}, {"label": "Линт"}, {"label": "Сборку"}]}]
SEL = "getSelection().toString()"
# точка в тексте строки ленты: [x, y] начала (0) или конца (1) узла с этим текстом
POINT = """(() => {{ const n = [...document.querySelectorAll('.feed .row .b, .feed .row .b *')].reverse().find((x) => x.textContent.trim() === {text!r});
  const r = document.createRange(); r.selectNodeContents(n); const b = r.getBoundingClientRect();
  return [{end} ? b.right - 1 : b.left + 1, b.top + b.height / 2]; }})()"""


@unittest.skipUnless(test_web_e2e.READY, "нужны Google Chrome и node")
class QuickAnswers(test_web_e2e.PageInChrome):
    def setUp(self):
        super().setUp()
        cfg = os.environ["HUB_CONFIG"]
        with open(cfg) as f:
            saved = f.read()
        self.addCleanup(lambda: open(cfg, "w").write(saved))
        with open(cfg, "w") as f:
            json.dump({"dev": {"enabled": False}, "agent_dev": {"enabled": False}, "update": {"enabled": False},
                       "extensions": {"quick-answers": {"path": PLUGIN, "web": "main.js"}} if WITH_PLUGIN else {}}, f)
        self.ev("session.requested", "a", session_id="s-a", cwd="/w", channel="cli", owner=True)
        self.ev("session.started", "a", session_id="s-a")

    def stop_chrome(self):
        try:
            super().stop_chrome()
        except subprocess.TimeoutExpired:   # машина перегружена: Chrome не успел выйти сам — тест от этого не красный
            os.killpg(self.chrome.pid, signal.SIGKILL)
            self.chrome.wait(60)
            shutil.rmtree(self.profile, ignore_errors=True)

    def page(self, *steps):
        r = subprocess.run(["node", "--experimental-websocket", CDP, str(self.cdp), json.dumps(list(steps))], capture_output=True, text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stderr[:1500])
        return json.loads(r.stdout)

    def open(self, *steps, width=1300):
        ready = "!!document.querySelector('.ask-card.quick')" if self.asked else "!!document.querySelector('.feed .row')"
        return self.page({"go": f"http://127.0.0.1:{self.port}/#/s/a", "width": width}, {"until": ready, "ms": 15000}, *steps)

    asked = False

    def ask(self, questions):
        self.asked = True
        self.ev("turn.started", "a", marker=None, prompt_head="x")
        self.ev("permission.requested", "a", request_id="r1", tool="AskUserQuestion", interactive=True,
                input={"questions": questions})

    def answers(self):
        return [e["data"]["answers"] for e in self.spooled() if e["type"] == "permission.answered"]

    def say(self, text):
        self.ev("session.said", "a", text=text)

    # --- карточка вопроса ------------------------------------------------------------------------------------------
    def test_a_click_on_an_option_answers_at_once(self):
        self.ask(ONE)
        got = self.open(
            {"eval": "[...document.querySelectorAll('.ask-card input[type=radio], .ask-card button[type=submit]')]"
                     ".filter((n) => { const r = n.getBoundingClientRect(); return r.width > 2 && getComputedStyle(n).opacity !== '0'; }).length"},
            {"press": ".ask-card .opt:nth-of-type(2)"},
            {"until": "!document.querySelector('.ask-card')"})
        self.assertEqual(got[2]["eval"], 0)   # ни радиокнопок, ни общей «Ответить»
        self.assertTrue(got[-1]["until"])     # карточка ушла сразу
        self.assertEqual(self.answers(), [{"Выкатываем?": "Позже"}])

    def test_an_option_answers_from_the_keyboard(self):
        self.ask(ONE)
        self.open({"eval": "document.querySelector('.ask-card .opt').focus(), document.activeElement.dispatchEvent("
                           "new KeyboardEvent('keydown', {key: 'Enter', bubbles: true, cancelable: true})), 1"},
                  {"until": "!document.querySelector('.ask-card')"})
        self.assertEqual(self.answers(), [{"Выкатываем?": "Да"}])

    def test_two_questions_go_with_the_last_pick(self):
        self.ask(TWO)
        self.open({"press": ".ask-card fieldset:nth-of-type(1) .opt"}, {"sleep": 400},
                  {"eval": "!!document.querySelector('.ask-card')"})
        self.assertEqual(self.answers(), [])   # второй вопрос ещё без ответа
        self.page({"press": ".ask-card fieldset:nth-of-type(2) .opt:nth-of-type(2)"},
                  {"until": "!document.querySelector('.ask-card')"})
        self.assertEqual(self.answers(), [{"Выкатываем?": "Да", "Куда?": "Прод"}])

    def test_several_choices_are_toggled_and_sent_with_one_button(self):
        self.ask(MANY)
        got = self.open({"press": ".ask-card .opt:nth-of-type(1)"}, {"press": ".ask-card .opt:nth-of-type(3)"},
                        {"sleep": 300}, {"eval": "!!document.querySelector('.ask-card')"})
        self.assertTrue(got[-1]["eval"])
        self.assertEqual(self.answers(), [])   # выбор — не ответ
        self.page({"press": ".ask-card .btns button[type=submit]"}, {"until": "!document.querySelector('.ask-card')"})
        self.assertEqual(self.answers(), [{"Что проверить?": "Тесты, Сборку"}])

    def test_own_answer_goes_with_the_button_to_the_right_of_the_field(self):
        self.ask(ONE)
        for width in (1300, 390):
            with self.subTest(width=width):
                got = self.open(
                    {"eval": "(() => { const t = document.querySelector('.ask-card textarea.other').getBoundingClientRect(),"
                             " b = document.querySelector('.ask-card .quick-send').getBoundingClientRect();"
                             " return [b.left >= t.right, b.top < t.bottom && b.bottom > t.top, b.right <= innerWidth,"
                             " document.querySelector('.ask-card .quick-send').disabled]; })()"}, width=width)
                self.assertEqual(got[-1]["eval"], [True, True, True, True])   # справа, в одной строке, пустое не уходит
        self.page({"press": ".ask-card textarea.other"}, {"type": "через час"}, {"press": ".ask-card .quick-send"},
                  {"until": "!document.querySelector('.ask-card')"})
        self.assertEqual(self.answers(), [{"Выкатываем?": "через час"}])

    def test_selecting_the_text_of_an_option_is_not_an_answer(self):
        self.ask(ONE)
        at = "(() => { const r = document.createRange(); r.selectNodeContents(document.querySelector('.ask-card .opt small'));" \
             " const b = r.getBoundingClientRect(); return [%s, b.top + b.height / 2]; })()"
        got = self.open({"mouse": "down", "at": at % "b.left + 1"}, {"mouse": "move", "at": at % "b.right - 1"},
                        {"mouse": "up", "at": at % "b.right - 1"}, {"sleep": 300}, {"eval": SEL})
        self.assertEqual(got[-1]["eval"], "сегодня")
        self.assertEqual(self.answers(), [])

    # --- выделение в ленте -----------------------------------------------------------------------------------------
    def select(self, text):
        return [{"mouse": "down", "at": POINT.format(text=text, end=0)}, {"mouse": "move", "at": POINT.format(text=text, end=1)},
                {"mouse": "up", "at": POINT.format(text=text, end=1)}]

    def test_selection_survives_new_events_in_the_feed(self):
        self.say("первая строка ответа")
        got = self.open({"until": "document.body.innerText.includes('первая строка ответа')"},
                        *self.select("первая строка ответа"), {"eval": SEL})
        self.assertEqual(got[-1]["eval"], "первая строка ответа")
        self.say("вторая строка")                      # новый снимок ядра — лента пересобирается
        self.ev("turn.tool", "a", id="t1", name="Bash", input={"command": "make"})
        got = self.page({"until": "document.body.innerText.includes('вторая строка')"}, {"sleep": 300}, {"eval": SEL},
                        {"eval": "(() => { let got = ''; document.addEventListener('copy', (e) => { got = getSelection().toString(); }, { once: true });"
                                 " document.execCommand('copy'); return got; })()"})
        self.assertEqual(got[2]["eval"], "первая строка ответа")
        self.assertEqual(got[3]["eval"], "первая строка ответа")   # и копируется

    def test_selection_keeps_growing_when_the_feed_is_rebuilt_under_the_mouse(self):
        self.say("первая строка ответа")
        self.say("вторая строка ответа")
        self.open({"until": "document.body.innerText.includes('вторая строка ответа')"},
                  {"mouse": "down", "at": POINT.format(text="первая строка ответа", end=0)},
                  {"mouse": "move", "at": POINT.format(text="первая строка ответа", end=1)})
        self.say("третья строка")                      # снимок пришёл, пока кнопка мыши зажата
        got = self.page({"until": "document.body.innerText.includes('третья строка')"},
                        {"mouse": "move", "at": POINT.format(text="вторая строка ответа", end=1)},
                        {"mouse": "up", "at": POINT.format(text="вторая строка ответа", end=1)}, {"eval": SEL})
        self.assertIn("первая строка ответа", got[-1]["eval"])
        self.assertIn("вторая строка ответа", got[-1]["eval"])

    def test_selecting_a_step_line_does_not_fold_it(self):
        self.ev("turn.started", "a", marker=None, prompt_head="x")
        self.ev("turn.tool", "a", id="t1", name="Bash", input={"command": "make test"})
        expanded = "document.querySelector('.feed .row.tool').getAttribute('aria-expanded')"
        at = "(() => { const b = document.querySelector('.feed .row.tool .call').getBoundingClientRect(); return [%s, b.top + b.height / 2]; })()"
        got = self.open({"until": "!!document.querySelector('.feed .row.tool')"}, {"eval": expanded},
                        {"mouse": "down", "at": at % "b.left + 2"}, {"mouse": "move", "at": at % "b.left + 60"},
                        {"mouse": "up", "at": at % "b.left + 60"}, {"sleep": 300}, {"eval": expanded}, {"eval": SEL},
                        {"press": ".feed .row.tool .g"}, {"sleep": 300}, {"eval": expanded})
        self.assertEqual((got[3]["eval"], got[8]["eval"]), ("false", "false"))   # выделили — строка не раскрылась
        self.assertTrue(got[9]["eval"])
        self.assertEqual(got[-1]["eval"], "true")                                # обычное нажатие раскрывает, как раньше


for _name in dir(test_web_e2e.PageInChrome):   # тесты самой страницы гоняет хаб — здесь только плагин
    if _name.startswith("test_") and _name not in vars(QuickAnswers):
        setattr(QuickAnswers, _name, None)


if __name__ == "__main__":
    unittest.main()

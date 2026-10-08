"""Страница хаба на временном журнале с вопросами сессий — посмотреть плагин глазами и снять снимки:
python3 tests/demo.py [--off] [--port N]. Сессии: a — один вопрос, b — выбор нескольких, c — два вопроса."""
import json
import os
import sys
import threading
import time

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get("HUB_CORE") or os.path.expanduser("~/projects/agents-hub-core"))

import tests  # noqa: E402, F401 — своя папка состояния и настройки, не машины
from tests import test_web  # noqa: E402

ASKS = {
    "a": [{"question": "Правка готова в ветке `fix/retry`. Выкатываем на стенд?", "options": [
        {"label": "Выкатывай (рекомендую)", "description": "Стенд обновится за пару минут, прод не трогаем."},
        {"label": "Сначала покажи дифф", "description": "Пришлю ссылку на изменения и подожду."},
        {"label": "Позже"}]}],
    "b": [{"question": "Что прогнать перед выпуском?", "multiSelect": True, "options": [
        {"label": "Тесты", "description": "Весь набор, около двух минут."}, {"label": "Линт"},
        {"label": "Сборку", "description": "Проверит, что пакет собирается."}]}],
    "c": [{"question": "Куда выкатываем?", "options": [{"label": "Стенд"}, {"label": "Прод"}]},
          {"question": "Когда?", "options": [{"label": "Сейчас"}, {"label": "Вечером"}]}],
}


def main(argv):
    port = int(argv[argv.index("--port") + 1]) if "--port" in argv else 0
    with open(os.environ["HUB_CONFIG"], "w") as f:
        json.dump({"dev": {"enabled": False}, "agent_dev": {"enabled": False}, "update": {"enabled": False},
                   "extensions": {} if "--off" in argv else {"quick-answers": {"path": PLUGIN, "web": "main.js"}}}, f)
    t = test_web.WebTest("test_page_and_snapshot")
    t.setUp()
    if port:   # нужен постоянный адрес — второй сервер той же страницы
        server = t.web.serve(port=port)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    for name, questions in ASKS.items():
        t.j.append("session.requested", name, {"session_id": f"s-{name}", "cwd": "/w/proj", "channel": "cli", "owner": True})
        t.j.append("session.started", name, {"session_id": f"s-{name}"})
        e = t.j.append("message.received", None, {"to": name, "text": "Почини повторы запросов", "channel": "cli", "owner": True})
        t.j.append("turn.started", name, {"marker": f"m{e['seq']}", "prompt_head": "Почини повторы запросов"})
        t.j.append("session.said", name, {"text": "Нашла причину: повтор уходил без паузы и упирался в лимит. "
                                                  "Добавила паузу с ростом и тест на три попытки."})
        t.j.append("permission.requested", name, {"request_id": "r1", "tool": "AskUserQuestion", "interactive": True,
                                                  "input": {"questions": questions}})
    print(f"http://127.0.0.1:{port or t.port}/#/s/a", flush=True)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main(sys.argv[1:])

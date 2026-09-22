# Telegram WebApp Clicker

Интерактивное веб-приложение (Mini App) для Telegram с анимацией SVG-персонажей, физикой взаимодействия и обратной связью (Haptic Feedback).

## Особенности

- **Интерактивный UI:** Анимированные SVG-элементы и Canvas-эффекты частиц
- **Физика клика:** Эффекты ударов, брызг и визуальная реакция на действия пользователя
- **Telegram Haptic Feedback:** Полная интеграция с нативной вибрацией устройства через Telegram WebApp API
- **Автономный фронтенд:** Высокая скорость работы без тяжелых внешних зависимостей

## Технологический стек

- **Frontend:** HTML5, Pure CSS, JavaScript (Canvas, SVG Animation), Telegram WebApp SDK
- **Backend:** Python (FastAPI), SQLite

## Запуск проекта

1. Откройте `index.html` локально в браузере или запустите бэкенд:

   ```bash
   pip install -r requirements.txt
   python main.py
   ```

Для тестирования в Telegram используйте `window.BACKEND_URL` и подключите локальный сервер через туннель (ngrok/localtunnel).

## Использование

1. Установите зависимости: `pip install -r requirements.txt`
2. Запустите сервер: `python main.py`
3. Откройте `index.html` в браузере для локального тестирования
4. Для Telegram используйте туннель для доступа к локальному серверу

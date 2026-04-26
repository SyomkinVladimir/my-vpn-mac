import rumps
import core
import json
import os
import time
import threading
import subprocess # Добавлено для Popen

HOME_DIR = os.path.expanduser("~/.myvpn")
SETTINGS_FILE = os.path.join(HOME_DIR, "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"mode": "Умный VPN (Split)"}

class OctaraMenuApp(rumps.App):
    def __init__(self):
        super(OctaraMenuApp, self).__init__("🐙", quit_button=None)

        self.timer_running = False
        self.start_time = 0

        self.status_item = rumps.MenuItem("Статус: ОТКЛЮЧЕНО")
        self.timer_item = rumps.MenuItem("Время сессии: 00:00:00")
        self.timer_item.hidden = True

        self.connect_btn = rumps.MenuItem("🟢 Подключить", callback=self.connect)
        self.disconnect_btn = rumps.MenuItem("🔴 Отключить", callback=self.disconnect)
        self.disconnect_btn.hidden = True

        self.logs_btn = rumps.MenuItem("📜 Открыть логи", callback=self.open_logs)
        self.settings_btn = rumps.MenuItem("⚙️ Настройки (main.py)", callback=self.open_settings)
        self.quit_btn = rumps.MenuItem("Выход", callback=self.quit_app)

        self.menu = [
            self.status_item,
            self.timer_item,
            None,
            self.connect_btn,
            self.disconnect_btn,
            self.logs_btn,
            None,
            self.settings_btn,
            self.quit_btn
        ]

    @rumps.timer(1)
    def update_timer(self, _):
        if self.timer_running:
            elapsed = int(time.time() - self.start_time)
            hours, rem = divmod(elapsed, 3600)
            minutes, seconds = divmod(rem, 60)
            self.timer_item.title = f"Время сессии: {hours:02}:{minutes:02}:{seconds:02}"

    def connect(self, _):
        settings = load_settings()
        mode = settings.get("mode", "Умный VPN (Split)")

        link = core.get_vless_link()

        if not link:
            old_link = settings.get("link", "")
            if old_link:
                core.save_vless_link(old_link)
                link = old_link

        if not link:
            rumps.alert("Ошибка", "Ключ VLESS не задан. Нажмите 'Настройки' и добавьте ключ.")
            return

        self.status_item.title = "Статус: ЗАПУСК..."
        self.connect_btn.hidden = True

        threading.Thread(target=self._run_core, args=(link, mode), daemon=True).start()

    def _run_core(self, link, mode):
        # Добавлен on_recover_callback
        result = core.start_vpn(link, mode, on_crash_callback=self.on_crash, on_recover_callback=self.on_recover)

        if result == "успех":
            self.status_item.title = f"Статус: ПОДКЛЮЧЕНО ({mode})"
            self.title = "🟢" # Иконка успешного подключения
            self.disconnect_btn.hidden = False
            self.start_time = time.time()
            self.timer_running = True
            self.timer_item.hidden = False
        else:
            self.status_item.title = f"⚠️ Ошибка: {result}"
            self.connect_btn.hidden = False
            self.title = "🔴" # Иконка ошибки
            rumps.alert("Ошибка ядра", result)

    def on_crash(self, reason):
        self.status_item.title = f"⚠️ Ошибка: {reason}"
        self.title = "🔴" # Иконка ошибки
        self.timer_running = False
        self.timer_item.hidden = True
        self.connect_btn.hidden = False
        self.disconnect_btn.hidden = True
        # УДАЛЕНО: core.unlock_network() - Kill-switch теперь жестко блокирует сеть

    def on_recover(self, mode):
        self.status_item.title = f"Статус: ПОДКЛЮЧЕНО ({mode}) [Восстановлено]"
        self.title = "🟢" # Возвращаем зеленую иконку
        self.timer_running = True
        self.start_time = time.time()
        self.timer_item.hidden = False
        self.disconnect_btn.hidden = False
        self.connect_btn.hidden = True

    def disconnect(self, _):
        core.stop_vpn()
        self.timer_running = False
        self.timer_item.hidden = True
        self.status_item.title = "Статус: ОТКЛЮЧЕНО"
        self.title = "🐙" # Стандартная иконка при отключении
        self.disconnect_btn.hidden = True
        self.connect_btn.hidden = False

    def open_logs(self, _):
        log_path = os.path.expanduser("~/.myvpn/octara.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("Лог-файл создан. Подключите VPN для появления записей.\n")

        subprocess.Popen(["open", log_path])

    def open_settings(self, _):
        project_dir = os.path.expanduser("~/my-vpn-mac")
        flet_bin = os.path.join(project_dir, "venv/bin/flet")
        # ПРАВКА: Используем Popen для безопасного асинхронного запуска
        subprocess.Popen([flet_bin, "run", "main.py"], cwd=project_dir)

    def quit_app(self, _):
        self.disconnect(None)
        rumps.quit_application()

if __name__ == "__main__":
    core.check_and_setup_permissions()
    OctaraMenuApp().run()
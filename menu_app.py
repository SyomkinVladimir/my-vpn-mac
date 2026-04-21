import rumps
import core
import json
import os
import time
import threading

HOME_DIR = os.path.expanduser("~/.myvpn")
SETTINGS_FILE = os.path.join(HOME_DIR, "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"link": "", "mode": "Системный прокси"}

class OctaraMenuApp(rumps.App):
    def __init__(self):
        super(OctaraMenuApp, self).__init__("🐙", quit_button=None)
        
        self.settings = load_settings()
        self.timer_running = False
        self.start_time = 0

        self.status_item = rumps.MenuItem("Статус: ОТКЛЮЧЕНО")
        self.timer_item = rumps.MenuItem("Время сессии: 00:00:00")
        self.timer_item.hidden = True
        
        self.connect_btn = rumps.MenuItem("🟢 Подключить", callback=self.connect)
        self.disconnect_btn = rumps.MenuItem("🔴 Отключить", callback=self.disconnect)
        self.disconnect_btn.hidden = True
        
        self.settings_btn = rumps.MenuItem("⚙️ Настройки (main.py)", callback=self.open_settings)
        self.quit_btn = rumps.MenuItem("Выход", callback=self.quit_app)

        self.menu = [
            self.status_item,
            self.timer_item,
            None,
            self.connect_btn,
            self.disconnect_btn,
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
        self.settings = load_settings()
        link = self.settings.get("link", "")
        mode = self.settings.get("mode", "Умный VPN (Split)")

        if not link:
            rumps.alert("Ошибка", "Ключ VLESS не задан. Нажмите 'Настройки' и добавьте ключ.")
            return

        self.status_item.title = "Статус: ЗАПУСК..."
        self.connect_btn.hidden = True
        
        threading.Thread(target=self._run_core, args=(link, mode), daemon=True).start()

    def _run_core(self, link, mode):
        # Дергаем ядро с обработчиком ошибок (on_crash_callback)
        result = core.start_vpn(link, mode, on_crash_callback=self.on_crash)
        
        if result == "успех":
            self.status_item.title = f"Статус: ПОДКЛЮЧЕНО ({mode})"
            self.title = "🐙" 
            self.disconnect_btn.hidden = False
            self.start_time = time.time()
            self.timer_running = True
            self.timer_item.hidden = False
        else:
            self.status_item.title = f"⚠️ Ошибка: {result}"
            self.connect_btn.hidden = False
            self.title = "🐙" 
            rumps.alert("Ошибка ядра", result)

    def on_crash(self, reason):
        # Вызывается из core.py, если sing-box упадет (отсутствие сети и т.д.)
        self.status_item.title = f"⚠️ Ошибка: {reason}"
        self.title = "🐙"
        self.timer_running = False
        self.timer_item.hidden = True
        self.connect_btn.hidden = False
        self.disconnect_btn.hidden = True
        core.unlock_network() 

    def disconnect(self, _):
        core.stop_vpn()
        self.timer_running = False
        self.timer_item.hidden = True
        self.status_item.title = "Статус: ОТКЛЮЧЕНО"
        self.title = "🐙"
        self.disconnect_btn.hidden = True
        self.connect_btn.hidden = False

    def open_settings(self, _):
        # Жесткий путь к виртуальному окружению
        project_dir = os.path.expanduser("~/my-vpn-mac")
        flet_bin = os.path.join(project_dir, "venv/bin/flet")
        os.system(f"cd {project_dir} && {flet_bin} run main.py &")

    def quit_app(self, _):
        self.disconnect(None)
        rumps.quit_application()

if __name__ == "__main__":
    core.check_and_setup_permissions()
    OctaraMenuApp().run()
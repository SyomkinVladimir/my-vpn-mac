import flet as ft
import core
import json
import os

HOME_DIR = os.path.expanduser("~/.myvpn")
os.makedirs(HOME_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(HOME_DIR, "settings.json")

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: pass
    return {"link": "", "mode": "Системный прокси"}

def save_settings(link, mode):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f: json.dump({"link": link, "mode": mode}, f)

def main(page: ft.Page):
    page.title = "My VPN Client (macOS)"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 700
    page.window_height = 550

    saved_settings = load_settings()
    status_text = ft.Text("Статус: ОТКЛЮЧЕНО", color=ft.Colors.RED_400, size=16, weight="bold")

    # --- ИНТЕГРАЦИЯ РЕШЕНИЯ КЛОДА ---
    if not core.check_and_setup_permissions():
        page.add(ft.Text("⚠️ Внимание: Без прав администратора режимы TUN работать не будут!", color=ft.Colors.ORANGE_400, weight="bold"))
    # --------------------------------

    def on_vpn_crash(error_reason=""):
        status_text.value = f"⚠️ ОШИБКА: {error_reason}"
        status_text.color = ft.Colors.ORANGE_700
        btn_connect.disabled = False
        page.update()

    def on_vpn_recover(mode):
        status_text.value = f"Статус: ПОДКЛЮЧЕНО ({mode}) [Восстановлено]"
        status_text.color = ft.Colors.GREEN_400
        page.update()

    def update_status_log(message):
        if "Попытка" in message or "Восстановление" in message:
            status_text.value = f"🔄 {message}"
            status_text.color = ft.Colors.CYAN_400
        page.update()

    mode_picker = ft.Dropdown(
        label="Режим работы",
        value=saved_settings.get("mode", "Системный прокси"),
        options=[ft.dropdown.Option("Системный прокси"), ft.dropdown.Option("VPN (TUN)"), ft.dropdown.Option("Умный VPN (Split)")],
        width=300
    )

    link_input = ft.TextField(
        label="Ссылка vless://", multiline=True, min_lines=3, width=600,
        value=saved_settings.get("link", ""), border_color=ft.Colors.BLUE_400
    )

    def connect_click(e):
        if not link_input.value: return
        save_settings(link_input.value, mode_picker.value)
        status_text.value = "Статус: ЗАПУСК..."
        status_text.color = ft.Colors.YELLOW_400
        btn_connect.disabled = True
        page.update()

        result = core.start_vpn(
            link_input.value, 
            mode_picker.value, 
            log_callback=update_status_log, 
            on_crash_callback=on_vpn_crash,
            on_recover_callback=on_vpn_recover
        )
        if result == "успех":
            status_text.value = f"Статус: ПОДКЛЮЧЕНО ({mode_picker.value})"
            status_text.color = ft.Colors.GREEN_400
        else:
            status_text.value = f"Статус: ОШИБКА ({result})"
            status_text.color = ft.Colors.RED_400
            btn_connect.disabled = False
        page.update()

    def disconnect_click(e):
        core.stop_vpn()
        status_text.value = "Статус: ОТКЛЮЧЕНО"
        status_text.color = ft.Colors.RED_400
        btn_connect.disabled = False
        page.update()

    btn_connect = ft.ElevatedButton("ПОДКЛЮЧИТЬ", icon=ft.Icons.POWER_SETTINGS_NEW, bgcolor=ft.Colors.GREEN_800, on_click=connect_click)
    btn_disconnect = ft.ElevatedButton("ОТКЛЮЧИТЬ", icon=ft.Icons.STOP_CIRCLE, bgcolor=ft.Colors.RED_800, on_click=disconnect_click)

    page.add(
        ft.Text("Управление VPN", size=28, weight="bold"),
        ft.Divider(height=20, color="transparent"),
        mode_picker,
        link_input,
        ft.Row([btn_connect, btn_disconnect], spacing=20),
        ft.Divider(height=20, color="transparent"),
        status_text
    )

if __name__ == '__main__':
    ft.app(target=main)
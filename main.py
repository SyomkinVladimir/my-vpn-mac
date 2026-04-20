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
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"link": "", "mode": "Системный прокси"}


def save_settings(link, mode):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"link": link, "mode": mode}, f)


def main(page: ft.Page):
    page.title = "MyVPN"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 700
    page.window_height = 580
    page.window_resizable = False

    saved_settings = load_settings()

    # --- Проверка прав ---
    if not core.check_and_setup_permissions():
        page.add(ft.Text(
            "⚠️ Без прав администратора режимы TUN работать не будут!",
            color=ft.Colors.ORANGE_400,
            weight="bold"
        ))

    # --- Статус ---
    status_indicator = ft.Container(
        width=12, height=12,
        border_radius=6,
        bgcolor=ft.Colors.RED_400
    )
    status_text = ft.Text(
        "ОТКЛЮЧЕНО",
        color=ft.Colors.RED_400,
        size=16,
        weight="bold"
    )

    # --- Callbacks ---
    def on_vpn_crash(error_reason=""):
        status_indicator.bgcolor = ft.Colors.ORANGE_400
        status_text.value = f"ОШИБКА: {error_reason}"
        status_text.color = ft.Colors.ORANGE_400
        btn_connect.disabled = False
        page.update()

    def on_vpn_recover(mode):
        status_indicator.bgcolor = ft.Colors.GREEN_400
        status_text.value = f"ПОДКЛЮЧЕНО ({mode}) [Восстановлено]"
        status_text.color = ft.Colors.GREEN_400
        page.update()

    def update_status_log(message):
        if "Попытка" in message or "Восстановление" in message:
            status_indicator.bgcolor = ft.Colors.CYAN_400
            status_text.value = f"🔄 {message}"
            status_text.color = ft.Colors.CYAN_400
            page.update()

    # --- Элементы UI ---
    mode_picker = ft.Dropdown(
        label="Режим работы",
        value=saved_settings.get("mode", "Системный прокси"),
        options=[
            ft.dropdown.Option("Системный прокси"),
            ft.dropdown.Option("VPN (TUN)"),
            ft.dropdown.Option("Умный VPN (Split)")
        ],
        width=300
    )

    link_input = ft.TextField(
        label="Ссылка vless://",
        multiline=True,
        min_lines=3,
        width=620,
        value=saved_settings.get("link", ""),
        border_color=ft.Colors.BLUE_400,
        hint_text="vless://uuid@server:port?params..."
    )

    # --- Логика кнопок ---
    def connect_click(e):
        if not link_input.value.strip():
            status_text.value = "Введите ссылку vless://"
            status_text.color = ft.Colors.ORANGE_400
            page.update()
            return

        save_settings(link_input.value, mode_picker.value)
        status_indicator.bgcolor = ft.Colors.YELLOW_400
        status_text.value = "ЗАПУСК..."
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
            status_indicator.bgcolor = ft.Colors.GREEN_400
            status_text.value = f"ПОДКЛЮЧЕНО ({mode_picker.value})"
            status_text.color = ft.Colors.GREEN_400
        else:
            status_indicator.bgcolor = ft.Colors.RED_400
            status_text.value = f"ОШИБКА: {result}"
            status_text.color = ft.Colors.RED_400
            btn_connect.disabled = False
        page.update()

    def disconnect_click(e):
        core.stop_vpn()
        status_indicator.bgcolor = ft.Colors.RED_400
        status_text.value = "ОТКЛЮЧЕНО"
        status_text.color = ft.Colors.RED_400
        btn_connect.disabled = False
        page.update()

    btn_connect = ft.ElevatedButton(
        "ПОДКЛЮЧИТЬ",
        icon=ft.Icons.POWER_SETTINGS_NEW,
        bgcolor=ft.Colors.GREEN_800,
        on_click=connect_click,
        height=45
    )
    btn_disconnect = ft.ElevatedButton(
        "ОТКЛЮЧИТЬ",
        icon=ft.Icons.STOP_CIRCLE,
        bgcolor=ft.Colors.RED_800,
        on_click=disconnect_click,
        height=45
    )

    # --- Сборка UI ---
    page.add(
        ft.Container(
            content=ft.Column([
                ft.Text("🐙 MyVPN", size=28, weight="bold"),
                ft.Divider(height=10, color="transparent"),
                mode_picker,
                ft.Divider(height=6, color="transparent"),
                link_input,
                ft.Divider(height=10, color="transparent"),
                ft.Row([btn_connect, btn_disconnect], spacing=20),
                ft.Divider(height=16, color="transparent"),
                ft.Row([
                    status_indicator,
                    ft.Text("Статус: ", color=ft.Colors.GREY_400, size=16),
                    status_text
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ]),
            padding=ft.padding.all(24)
        )
    )


if __name__ == '__main__':
    ft.app(target=main)
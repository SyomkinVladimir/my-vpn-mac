import flet as ft
import core
import json
import os

SETTINGS_FILE = "settings.json"

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception: pass
    return {"link": "", "mode": "Системный прокси"}

def save_settings(link, mode):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"link": link, "mode": mode}, f)

def main(page: ft.Page):
    page.title = "My VPN Client (macOS)"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 700
    page.window_height = 500
    page.padding = 30
    page.vertical_alignment = ft.MainAxisAlignment.START

    saved_settings = load_settings()

    title_text = ft.Text("Управление VPN", size=28, weight=ft.FontWeight.BOLD)
    status_text = ft.Text("Статус: ОТКЛЮЧЕНО", color=ft.Colors.RED_400, size=16, weight=ft.FontWeight.BOLD)

    mode_picker = ft.Dropdown(
        label="Режим работы",
        value=saved_settings.get("mode", "Системный прокси"),
        options=[
            ft.dropdown.Option("Системный прокси"),
            ft.dropdown.Option("VPN (TUN)"),
            ft.dropdown.Option("Умный VPN (Split)") # <--- Вот наш 3-й режим
        ],
        width=300
    )

    link_input = ft.TextField(
        label="Вставьте ссылку vless://",
        multiline=True, min_lines=3, max_lines=5, width=600,
        border_color=ft.Colors.BLUE_400,
        value=saved_settings.get("link", "")
    )

    def connect_click(e):
        if not link_input.value: return
        save_settings(link_input.value, mode_picker.value)
        
        status_text.value = "Статус: ЗАПУСК..."
        status_text.color = ft.Colors.YELLOW_400
        btn_connect.disabled = True
        page.update()

        result = core.start_vpn(
            vless_link=link_input.value,
            mode=mode_picker.value,
            test_mode=False
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
        page.update()

    btn_connect = ft.ElevatedButton("ПОДКЛЮЧИТЬ", icon=ft.Icons.POWER_SETTINGS_NEW, bgcolor=ft.Colors.GREEN_800, color=ft.Colors.WHITE, height=50, width=200, on_click=connect_click)    
    btn_disconnect = ft.ElevatedButton("ОТКЛЮЧИТЬ", icon=ft.Icons.STOP_CIRCLE, bgcolor=ft.Colors.RED_800, color=ft.Colors.WHITE, height=50, width=200, on_click=disconnect_click)

    page.add(title_text, ft.Divider(height=20, color=ft.Colors.TRANSPARENT), mode_picker, link_input, ft.Divider(height=10, color=ft.Colors.TRANSPARENT), ft.Row([btn_connect, btn_disconnect], spacing=20), ft.Divider(height=20, color=ft.Colors.TRANSPARENT), status_text)

if __name__ == '__main__':
    ft.app(target=main)
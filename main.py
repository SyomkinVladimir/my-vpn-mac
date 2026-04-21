import flet as ft
import core
import json
import os
import time  # Добавили для работы с временем
import threading # Добавили для фонового потока таймера

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
    page.title = "My VPN Client (macOS)"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 700
    page.window_height = 550
    page.window_icon = "Octara.png"

    saved_settings = load_settings()
    current_link = saved_settings.get("link", "")
    
    # Переменные для управления таймером
    timer_running = False
    start_time = 0

    status_text = ft.Text(
        "Статус: ОТКЛЮЧЕНО",
        color=ft.Colors.RED_400,
        size=16,
        weight="bold"
    )
    
    # Новый элемент UI для отображения времени сессии
    session_timer_text = ft.Text(
        "Время сессии: 00:00:00",
        color=ft.Colors.GREY_400,
        size=14,
        visible=False # Скрыт, пока нет подключения
    )

    if not core.check_and_setup_permissions():
        page.add(ft.Text("⚠️ Требуются права администратора!", color=ft.Colors.ORANGE_400))

    # Функция, которая бежит в отдельном потоке и обновляет часы
    def update_timer():
        nonlocal timer_running
        while timer_running:
            elapsed = int(time.time() - start_time)
            hours, rem = divmod(elapsed, 3600)
            minutes, seconds = divmod(rem, 60)
            session_timer_text.value = f"Время сессии: {hours:02}:{minutes:02}:{seconds:02}"
            page.update()
            time.sleep(1)

    def on_vpn_crash(error_reason=""):
        nonlocal timer_running
        timer_running = False # Останавливаем таймер при падении
        status_text.value = f"⚠️ ОШИБКА: {error_reason}"
        status_text.color = ft.Colors.ORANGE_700
        btn_connect.disabled = False
        page.update()

    # ... функции on_vpn_recover и update_status_log остаются без изменений ...

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

    # --- Твоя карточка профиля ---
    dialog_link_input = ft.TextField(label="Ссылка vless://", multiline=True, min_lines=4, width=500, value=current_link)
    
    def save_dialog(e):
        nonlocal current_link
        current_link = dialog_link_input.value.strip()
        save_settings(current_link, mode_picker.value)
        profile_subtitle.value = "✓ Ключ установлен" if current_link else "Ключ не задан"
        profile_subtitle.color = ft.Colors.GREEN_300 if current_link else ft.Colors.RED_300
        page.close(link_dialog)
        page.update()

    link_dialog = ft.AlertDialog(
        title=ft.Text("Настройка ключа"),
        content=dialog_link_input,
        actions=[ft.TextButton("Отмена", on_click=lambda e: page.close(link_dialog)),
                 ft.ElevatedButton("Сохранить", on_click=save_dialog)]
    )

    profile_subtitle = ft.Text("✓ Ключ установлен" if current_link else "Ключ не задан", color=ft.Colors.GREEN_300, size=13)
    profile_card = ft.Container(
        padding=15, width=600, bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE), border_radius=8,
        content=ft.Row([
            ft.Column([ft.Text("VLESS Профиль", weight="bold"), profile_subtitle]),
            ft.IconButton(icon=ft.Icons.EDIT, on_click=lambda e: page.open(link_dialog))
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
    )

    def connect_click(e):
        nonlocal timer_running, start_time
        if not current_link: return

        status_text.value = "Статус: ЗАПУСК..."
        status_text.color = ft.Colors.YELLOW_400
        btn_connect.disabled = True
        page.update()

        result = core.start_vpn(current_link, mode_picker.value, on_crash_callback=on_vpn_crash)

        if result == "успех":
            status_text.value = f"Статус: ПОДКЛЮЧЕНО ({mode_picker.value})"
            status_text.color = ft.Colors.GREEN_400
            
            # ЗАПУСК ТАЙМЕРА
            start_time = time.time()
            timer_running = True
            session_timer_text.visible = True
            threading.Thread(target=update_timer, daemon=True).start()
        else:
            status_text.value = f"Статус: ОШИБКА ({result})"
            status_text.color = ft.Colors.RED_400
            btn_connect.disabled = False
        page.update()

    def disconnect_click(e):
        nonlocal timer_running
        core.stop_vpn()
        timer_running = False # Останавливаем таймер
        session_timer_text.visible = False
        status_text.value = "Статус: ОТКЛЮЧЕНО"
        status_text.color = ft.Colors.RED_400
        btn_connect.disabled = False
        page.update()

    btn_connect = ft.ElevatedButton("ПОДКЛЮЧИТЬ", bgcolor=ft.Colors.GREEN_800, on_click=connect_click)
    btn_disconnect = ft.ElevatedButton("ОТКЛЮЧИТЬ", bgcolor=ft.Colors.RED_800, on_click=disconnect_click)

    page.add(
        ft.Text("Управление VPN", size=28, weight="bold"),
        ft.Divider(height=20, color="transparent"),
        mode_picker,
        profile_card,
        ft.Divider(height=10, color="transparent"),
        ft.Row([btn_connect, btn_disconnect], spacing=20),
        ft.Divider(height=20, color="transparent"),
        status_text,
        session_timer_text # Добавили таймер в самый низ
    )

if __name__ == "__main__":
    ft.app(target=main)
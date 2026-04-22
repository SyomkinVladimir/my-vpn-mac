import flet as ft
import core
import json
import os
import time
import threading

# Настройка путей. Оставляем только для хранения несекретных настроек (режима работы)
HOME_DIR = os.path.expanduser("~/.myvpn")
os.makedirs(HOME_DIR, exist_ok=True)
SETTINGS_FILE = os.path.join(HOME_DIR, "settings.json")

def load_mode():
    """
    Зачем применяем: Загружает только несекретные пользовательские предпочтения.
    Пароль (VLESS-ссылка) отсюда ИСКЛЮЧЕН ради безопасности.
    """
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("mode", "Умный VPN (Split)")
        except Exception:
            pass
    return "Умный VPN (Split)"

def save_mode(mode):
    """Сохраняет выбранный режим маршрутизации в обычный JSON."""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump({"mode": mode}, f)

def main(page: ft.Page):
    page.title = "Octara VPN Settings"
    page.theme_mode = ft.ThemeMode.DARK
    page.window_width = 700
    page.window_height = 550
    page.window_icon = "Octara.png"

    saved_mode = load_mode()
    
    # ИНТЕГРАЦИЯ БЕЗОПАСНОСТИ: 
    # Зачем применяем: Читаем ключ напрямую из системной Связки ключей macOS через наше ядро.
    # Если ключа нет, возвращаем пустую строку, чтобы интерфейс не упал.
    current_link = core.get_vless_link() or ""
    
    timer_running = False
    start_time = 0

    status_text = ft.Text("Статус: ОТКЛЮЧЕНО", color=ft.Colors.RED_400, size=16, weight="bold")
    session_timer_text = ft.Text("Время сессии: 00:00:00", color=ft.Colors.GREY_400, size=14, visible=False)

    if not core.check_and_setup_permissions():
        page.add(ft.Text("⚠️ Требуются права администратора!", color=ft.Colors.ORANGE_400))

    def update_timer():
        """Фоновый поток обновления таймера."""
        nonlocal timer_running
        while timer_running:
            elapsed = int(time.time() - start_time)
            hours, rem = divmod(elapsed, 3600)
            minutes, seconds = divmod(rem, 60)
            session_timer_text.value = f"Время сессии: {hours:02}:{minutes:02}:{seconds:02}"
            page.update()
            time.sleep(1)

    def on_vpn_crash(error_reason=""):
        """Обработчик аварийной остановки."""
        nonlocal timer_running
        timer_running = False
        status_text.value = f"⚠️ ОШИБКА: {error_reason}"
        status_text.color = ft.Colors.ORANGE_700
        btn_connect.disabled = False
        page.update()

    mode_picker = ft.Dropdown(
        label="Режим работы",
        value=saved_mode,
        options=[
            ft.dropdown.Option("Системный прокси"),
            ft.dropdown.Option("VPN (TUN)"),
            ft.dropdown.Option("Умный VPN (Split)")
        ],
        width=300
    )

    # Поле ввода скрывает длинную ссылку, чтобы никто не подсмотрел ее из-за плеча (password=True)
    dialog_link_input = ft.TextField(
        label="Ссылка vless://", 
        multiline=True, 
        min_lines=4, 
        width=500, 
        value=current_link,
        password=True,
        can_reveal_password=True
    )
    
    def save_dialog(e):
        """
        Сохранение настроек.
        Зачем применяем: Разделяем потоки данных. Ключ уходит в зашифрованный Keychain, 
        а обычный режим работы (mode) сохраняется в JSON.
        """
        nonlocal current_link
        new_link = dialog_link_input.value.strip()
        
        if new_link:
            core.save_vless_link(new_link)
            current_link = new_link
            
        save_mode(mode_picker.value)
        
        profile_subtitle.value = "✓ Ключ установлен (Keychain)" if current_link else "Ключ не задан"
        profile_subtitle.color = ft.Colors.GREEN_300 if current_link else ft.Colors.RED_300
        page.close(link_dialog)
        page.update()

    link_dialog = ft.AlertDialog(
        title=ft.Text("Настройка ключа"),
        content=dialog_link_input,
        actions=[
            ft.TextButton("Отмена", on_click=lambda e: page.close(link_dialog)),
            ft.ElevatedButton("Сохранить", on_click=save_dialog)
        ]
    )

    profile_subtitle = ft.Text(
        "✓ Ключ установлен (Keychain)" if current_link else "Ключ не задан", 
        color=ft.Colors.GREEN_300 if current_link else ft.Colors.RED_300, 
        size=13
    )
    
    profile_card = ft.Container(
        padding=15, width=600, bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLUE), border_radius=8,
        content=ft.Row([
            ft.Column([ft.Text("VLESS Профиль", weight="bold"), profile_subtitle]),
            ft.IconButton(icon=ft.Icons.EDIT, on_click=lambda e: page.open(link_dialog))
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
    )

    def connect_click(e):
        nonlocal timer_running, start_time
        if not current_link: 
            return

        status_text.value = "Статус: ЗАПУСК..."
        status_text.color = ft.Colors.YELLOW_400
        btn_connect.disabled = True
        page.update()

        # Запускаем ядро, передавая обработчик падений
        result = core.start_vpn(current_link, mode_picker.value, on_crash_callback=on_vpn_crash)

        if result == "успех":
            status_text.value = f"Статус: ПОДКЛЮЧЕНО ({mode_picker.value})"
            status_text.color = ft.Colors.GREEN_400
            
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
        timer_running = False
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
        session_timer_text
    )

if __name__ == "__main__":
    ft.app(target=main)
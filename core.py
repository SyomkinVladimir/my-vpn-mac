import json
import subprocess
import os
import re
import platform
import threading
from urllib.parse import urlparse, unquote, parse_qs

# Глобальная переменная для хранения процесса ядра
core_process = None

def parse_vless_link(vless_url):
    try:
        # Очистка от случайных пробелов и переносов строк
        vless_url = re.sub(r'\s+', '', vless_url)
        
        # Отрезаем название сервера (всё, что после #)
        if '#' in vless_url:
            vless_url = vless_url.split('#')[0]
        
        parsed_url = urlparse(vless_url)
        
        # Проверка, что это именно VLESS
        if parsed_url.scheme != 'vless': 
            return None
        
        # Разбор параметров
        qs = parse_qs(parsed_url.query)
        params = {k: unquote(v[0]) for k, v in qs.items()}

        return {
            "uuid": parsed_url.username,     
            "server_ip": parsed_url.hostname, 
            "port": int(parsed_url.port),    
            "params": params                 
        }
    
    except Exception as e:
        print(f"Ошибка парсинга ссылки: {e}")
        return None

def set_system_proxy(enable=True):
    # Эта функция работает только на macOS
    if platform.system() != "Darwin":
        return
        
    interface = "Wi-Fi"
    state = "on" if enable else "off"

    try:
        # Включаем или выключаем системные настройки
        subprocess.run(["networksetup", "-setwebproxystate", interface, state])
        subprocess.run(["networksetup", "-setsecurewebproxystate", interface, state])

        if enable:
            # Направляем трафик на локальный порт sing-box
            subprocess.run(["networksetup", "-setwebproxy", interface, "127.0.0.1", "10808"])
            subprocess.run(["networksetup", "-setsecurewebproxy", interface, "127.0.0.1", "10808"])

    except Exception as e:
        print(f"Proxy error: {e}")

def generate_singbox_config(data):
    server_host = data["server_ip"]
    params = data["params"]

    # Базовые настройки исходящего подключения
    vless_outbound = {
        "type": "vless",
        "tag": "vless-out",
        "server": server_host,
        "server_port": data["port"],
        "uuid": data["uuid"],
        "packet_encoding": "xudp"
    }
    
    if params.get("flow"):
        vless_outbound["flow"] = params["flow"]
        
    # Настройки шифрования (TLS / Reality)
    if params.get("security") in ["tls", "reality"]:
        vless_outbound["tls"] = {
            "enabled": True,
            "server_name": params.get("sni", server_host),
            "utls": {"enabled": True, "fingerprint": params.get("fp", "chrome")},
            "alpn": ["h2", "http/1.1"]  
        }
        if params.get("security") == "reality":
            vless_outbound["tls"]["reality"] = {
                "enabled": True,
                "public_key": params.get("pbk", ""),
                "short_id": params.get("sid", "")
            }
            
    # Сборка финального файла конфигурации
    config = {
        "log": {"level": "error"},
        "inbounds": [{
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": 10808,
            "sniff": True
        }],
        "outbounds": [
            vless_outbound,
            {"type": "direct", "tag": "direct-out"}
        ],
        "route": {
            "rules": [
                {"ip_cidr": [f"{server_host}/32"], "outbound": "direct-out"}
            ],
            "auto_detect_interface": True
        }
    }

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def start_vpn(vless_link, mode, log_callback=None, test_mode=False):
    global core_process
    
    # --- НОВЫЙ БЛОК ДЛЯ ТЕСТОВ ---
    if test_mode:
        if log_callback:
            log_callback("> [TEST] Запуск в режиме имитации...")
            log_callback(f"> [TEST] Выбран режим: {mode}")
            log_callback("> [TEST] Ядро успешно сымитировало работу!")
        return "успех"
    # ---------------------------------

    if core_process is not None:
        return "уже работает"
    
    parsed_data = parse_vless_link(vless_link)
    if not parsed_data:
        return "ошибка ссылки"
    
    # Генерируем config.json
    generate_singbox_config(parsed_data)
    
    # Очищаем старые зависшие процессы
    os.system("killall sing-box 2>/dev/null")

    try:
        # Запускаем ядро в фоновом режиме
        core_process = subprocess.Popen(
            ["./sing-box", "run", "-c", "config.json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Если передан интерфейс логов, запускаем поток для их чтения
        if log_callback:
            def read_logs():
                for line in core_process.stdout:
                    if line:
                        # Очищаем логи от системных цветовых кодов
                        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line.strip())
                        log_callback(clean_line)
                        
            threading.Thread(target=read_logs, daemon=True).start()

        # Включаем системный прокси (защита от регистра)
        if mode.lower() == "системный прокси":
            set_system_proxy(True)
        
        return "успех"
    
    except Exception as e:
        core_process = None
        return f"ошибка: {e}"

def stop_vpn():
    global core_process
    
    # Отключаем прокси в macOS
    set_system_proxy(False)
    
    # Убиваем процесс ядра
    if core_process is not None:
        os.system("killall sing-box 2>/dev/null")
        core_process.terminate()
        core_process = None
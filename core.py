import json
import subprocess
import os
import re
import platform
import threading
import time
import sys
import shutil
import stat
import getpass
import logging
import keyring
from urllib.parse import urlparse, unquote, parse_qs

# --- Настройка путей и глобальных переменных ---
core_process = None
is_manually_stopped = False
MAX_RETRIES = 3
current_retries = 0

HOME_DIR = os.path.expanduser("~/.myvpn")
os.makedirs(HOME_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(HOME_DIR, "config.json")
SINGBOX_PATH = os.path.join(HOME_DIR, "sing-box")
LOG_FILE = os.path.join(HOME_DIR, "octara.log")

def clear_logs():
    """Очищает файл логов."""
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.truncate(0)
    except Exception:
        pass

def setup_logger():
    logging.basicConfig(
        level=logging.INFO, 
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

setup_logger()

# --- Безопасное хранение данных ---
def save_vless_link(link):
    try:
        keyring.set_password("OctaraVPN", "vless_config", link)
    except Exception as e:
        logging.error(f"Ошибка сохранения в Keychain: {e}")

def get_vless_link():
    try:
        return keyring.get_password("OctaraVPN", "vless_config")
    except Exception as e:
        logging.error(f"Ошибка чтения из Keychain: {e}")
        return None

# --- Системные функции ---
def setup_singbox():
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    bundled_singbox = os.path.join(base_path, "sing-box")
    
    if os.path.exists(bundled_singbox):
        shutil.copy(bundled_singbox, SINGBOX_PATH)
        os.chmod(SINGBOX_PATH, stat.S_IRWXU)
        subprocess.run(["/usr/bin/xattr", "-rd", "com.apple.quarantine", SINGBOX_PATH], stderr=subprocess.DEVNULL)

setup_singbox()

def check_and_setup_permissions():
    sudoers_file = "/etc/sudoers.d/myvpn_v2"
    if os.path.exists(sudoers_file):
        return True

    user = getpass.getuser()
    sudoers_line = f"{user} ALL=(ALL) NOPASSWD: {SINGBOX_PATH}, /sbin/pfctl, /usr/bin/killall"
    script = f'''do shell script "rm -f /etc/sudoers.d/myvpn* && echo '{sudoers_line}' > {sudoers_file} && chmod 440 {sudoers_file}" with administrator privileges'''

    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def lock_network():
    subprocess.run(["/usr/bin/sudo", "-n", "/sbin/pfctl", "-e", "-f", "-"], input="block drop all", text=True, stderr=subprocess.DEVNULL)

def unlock_network():
    subprocess.run(["/usr/bin/sudo", "-n", "/sbin/pfctl", "-d"], stderr=subprocess.DEVNULL)

# --- Работа с сетью и конфигами ---
def parse_vless_link(vless_url):
    try:
        vless_url = re.sub(r'\s+', '', vless_url).split('#')[0]
        parsed_url = urlparse(vless_url)
        if parsed_url.scheme != 'vless': return None
            
        params = {k: unquote(v[0]) for k, v in parse_qs(parsed_url.query).items()}
        return {
            "uuid": parsed_url.username,
            "server_ip": parsed_url.hostname,
            "port": int(parsed_url.port),
            "params": params,
        }
    except Exception:
        return None

def set_system_proxy(enable=True):
    if platform.system() != "Darwin": return
    state = "on" if enable else "off"
    cmds = [
        ["networksetup", "-setwebproxystate", "Wi-Fi", state],
        ["networksetup", "-setsecurewebproxystate", "Wi-Fi", state]
    ]
    if enable:
        cmds.extend([
            ["networksetup", "-setwebproxy", "Wi-Fi", "127.0.0.1", "10808"],
            ["networksetup", "-setsecurewebproxy", "Wi-Fi", "127.0.0.1", "10808"]
        ])
    for cmd in cmds:
        subprocess.run(cmd, capture_output=True)
def generate_singbox_config(data, mode):
    server_host = data["server_ip"]
    params = data["params"]
    
    vless_outbound = {
        "type": "vless",
        "tag": "vless-out",
        "server": server_host,
        "server_port": data["port"],
        "uuid": data["uuid"],
        "packet_encoding": "xudp",
        "tcp_fast_open": True,
    }
    
    if params.get("flow"): vless_outbound["flow"] = params["flow"]
        
    if params.get("security") in ["tls", "reality"]:
        vless_outbound["tls"] = {
            "enabled": True,
            "server_name": params.get("sni", server_host),
            "utls": {"enabled": True, "fingerprint": params.get("fp", "chrome")},
            "alpn": ["h2", "http/1.1"],
        }
        if params.get("security") == "reality":
            vless_outbound["tls"]["reality"] = {
                "enabled": True,
                "public_key": params.get("pbk", ""),
                "short_id": params.get("sid", ""),
            }

    inbounds = []
    if mode in ["VPN (TUN)", "Умный VPN (Split)"]:
        inbounds.append({
            "type": "tun",
            "tag": "tun-in",
            "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"],
            "mtu": 9000, # MTU 9000 критически важен для стека gvisor и Gemini
            "auto_route": True,
            "strict_route": True,
            "stack": "gvisor",
            "sniff": True,
            "sniff_override_destination": True
        })
    else:
        inbounds.append({
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": 10808,
            "sniff": True,
            "sniff_override_destination": True
        })

    # Список доменов Google для маршрутизации и блокировки QUIC
    google_domains = [
        "google.com", "googleapis.com", "gstatic.com", 
        "youtube.com", "googlevideo.com", "ytimg.com", "ggpht.com",
        "generativeai.google", "googleusercontent.com", "gvt1.com"
    ]

    rules = [
        {"protocol": "dns", "outbound": "dns-out"},
        {"ip_cidr": [f"{server_host}/32"], "outbound": "direct-out"},
        {"ip_cidr": ["192.168.0.0/16", "10.0.0.0/8", "127.0.0.0/8"], "outbound": "direct-out"}
    ]
    
    # ХИРУРГИЧЕСКАЯ БЛОКИРОВКА: Блокируем UDP 443 ТОЛЬКО для Google.
    # Apple (mask.icloud.com) и другие системы теперь не пострадают.
    rules.append({
        "network": "udp", 
        "port": 443, 
        "domain_suffix": google_domains, 
        "outbound": "block-out"
    })

    if mode == "Умный VPN (Split)":
        rules.append({
            "domain_suffix": google_domains, 
            "outbound": "vless-out"
        })
        rules.append({
            "domain_suffix": [".ru", ".рф", ".su", "yandex.ru", "vk.com", "mail.ru"], 
            "outbound": "direct-out"
        })

    config = {
        "log": {"level": "info"},
        "dns": {
            # Простая и надежная конфигурация DNS, которая работала у нас с самого начала
            "servers": [
                {"tag": "google-dns", "address": "8.8.8.8", "detour": "vless-out"},
                {"tag": "cloudflare-dns", "address": "1.1.1.1", "detour": "vless-out"}
            ],
            "strategy": "ipv4_only",
            "independent_cache": True,
        },
        "inbounds": inbounds,
        "outbounds": [
            vless_outbound, 
            {"type": "direct", "tag": "direct-out"}, 
            {"type": "dns", "tag": "dns-out"},
            {"type": "block", "tag": "block-out"}
        ],
        "route": {
            "rules": rules, 
            "auto_detect_interface": True, 
            "final": "vless-out" if mode == "VPN (TUN)" else "direct-out"
        },
    }
    
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

# --- Управление жизненным циклом ---
def monitor_process(process, vless_link, mode, log_callback, on_crash_callback, on_recover_callback):
    global current_retries, core_process
    process.wait()

    if is_manually_stopped: return

    core_process = None
    logging.error(f"Ядро неожиданно остановилось. Попытка {current_retries + 1}/{MAX_RETRIES}")

    if current_retries < MAX_RETRIES:
        current_retries += 1
        time.sleep(1.5)
        result = start_vpn(vless_link, mode, log_callback, on_crash_callback, on_recover_callback, is_retry=True)
        if result == "успех" and on_recover_callback:
            on_recover_callback(mode)
    else:
        lock_network()
        if on_crash_callback: on_crash_callback("Лимит попыток исчерпан.")

def start_vpn(vless_link, mode, log_callback=None, on_crash_callback=None, on_recover_callback=None, is_retry=False):
    global core_process, is_manually_stopped, current_retries
    
    clear_logs() # Очистка логов перед каждым новым запуском
    
    if not is_retry:
        current_retries = 0
        is_manually_stopped = False
        
    unlock_network()
    
    if core_process is not None: return "уже работает"
        
    parsed_data = parse_vless_link(vless_link)
    if not parsed_data: return "ошибка ссылки"
        
    generate_singbox_config(parsed_data, mode)
    subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/killall", "sing-box"], stderr=subprocess.DEVNULL)
    
    try:
        cmd = [SINGBOX_PATH, "run", "-c", CONFIG_FILE]
        if mode in ["VPN (TUN)", "Умный VPN (Split)"]:
            cmd = ["/usr/bin/sudo", "-n"] + cmd
            
        core_process = subprocess.Popen(
            cmd, 
            stdin=subprocess.DEVNULL, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1, 
            cwd=HOME_DIR
        )
        
        def read_logs():
            for line in core_process.stdout:
                clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line.strip())
                # ВАЖНО: Фильтруем спам на уровне Python. Строки с таймаутом просто игнорируются.
                if clean_line and "operation timed out" not in clean_line:
                    logging.info(f"[Core]: {clean_line}")
                    if log_callback: log_callback(clean_line)
                    
        threading.Thread(target=read_logs, daemon=True).start()
        time.sleep(0.5)
        
        if core_process.poll() is not None:
            core_process = None
            return "Нет прав администратора (sudo)"
            
        threading.Thread(target=monitor_process, args=(core_process, vless_link, mode, log_callback, on_crash_callback, on_recover_callback), daemon=True).start()
        
        if mode == "Системный прокси": set_system_proxy(True)
        return "успех"
        
    except Exception as e:
        core_process = None
        return f"ошибка: {e}"

def stop_vpn():
    global core_process, is_manually_stopped
    is_manually_stopped = True
    unlock_network()
    set_system_proxy(False)
    
    if core_process is not None:
        subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/killall", "sing-box"], stderr=subprocess.DEVNULL)
        core_process.terminate()
        core_process = None
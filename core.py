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
from urllib.parse import urlparse, unquote, parse_qs

core_process = None
is_manually_stopped = False
MAX_RETRIES = 3
current_retries = 0

HOME_DIR = os.path.expanduser("~/.myvpn")
os.makedirs(HOME_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(HOME_DIR, "config.json")
SINGBOX_PATH = os.path.join(HOME_DIR, "sing-box")

def setup_singbox():
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    bundled_singbox = os.path.join(base_path, "sing-box")
    if os.path.exists(bundled_singbox):
        shutil.copy(bundled_singbox, SINGBOX_PATH)
        os.chmod(SINGBOX_PATH, stat.S_IRWXU)
        os.system(f"/usr/bin/xattr -rd com.apple.quarantine {SINGBOX_PATH} 2>/dev/null")

setup_singbox()

def check_and_setup_permissions():
    """Запрашивает пароль один раз и прописывает sudoers"""
    sudoers_file = "/etc/sudoers.d/myvpn_v2" # Новое имя для принудительного обновления файла!
    if os.path.exists(sudoers_file):
        return True
    
    user = getpass.getuser() # Идеально точный метод получения твоего логина
    sudoers_line = f"{user} ALL=(ALL) NOPASSWD: {SINGBOX_PATH}, /sbin/pfctl, /usr/bin/killall"
    
    # Удаляем старый проблемный файл и создаем новый
    script = f'''do shell script "rm -f /etc/sudoers.d/myvpn && echo '{sudoers_line}' > {sudoers_file} && chmod 440 {sudoers_file}" with administrator privileges'''
    
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script], capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def lock_network():
    os.system('echo "block drop all" | /usr/bin/sudo -n /sbin/pfctl -e -f - 2>/dev/null')

def unlock_network():
    os.system('/usr/bin/sudo -n /sbin/pfctl -d 2>/dev/null')

def parse_vless_link(vless_url):
    try:
        vless_url = re.sub(r'\s+', '', vless_url)
        if '#' in vless_url: vless_url = vless_url.split('#')[0]
        parsed_url = urlparse(vless_url)
        if parsed_url.scheme != 'vless': return None
        qs = parse_qs(parsed_url.query)
        params = {k: unquote(v[0]) for k, v in qs.items()}
        return {"uuid": parsed_url.username, "server_ip": parsed_url.hostname, "port": int(parsed_url.port), "params": params}
    except Exception: return None

def set_system_proxy(enable=True):
    if platform.system() != "Darwin": return
    interface = "Wi-Fi"
    state = "on" if enable else "off"
    try:
        subprocess.run(["networksetup", "-setwebproxystate", interface, state])
        subprocess.run(["networksetup", "-setsecurewebproxystate", interface, state])
        if enable:
            subprocess.run(["networksetup", "-setwebproxy", interface, "127.0.0.1", "10808"])
            subprocess.run(["networksetup", "-setsecurewebproxy", interface, "127.0.0.1", "10808"])
    except Exception: pass

def generate_singbox_config(data, mode):
    server_host = data["server_ip"]
    params = data["params"]
    vless_outbound = {
        "type": "vless", "tag": "vless-out", "server": server_host,
        "server_port": data["port"], "uuid": data["uuid"], "packet_encoding": "xudp"
    }
    if params.get("flow"): vless_outbound["flow"] = params["flow"]
    if params.get("security") in ["tls", "reality"]:
        vless_outbound["tls"] = {
            "enabled": True, "server_name": params.get("sni", server_host),
            "utls": {"enabled": True, "fingerprint": params.get("fp", "chrome")},
            "alpn": ["h2", "http/1.1"]
        }
        if params.get("security") == "reality":
            vless_outbound["tls"]["reality"] = {
                "enabled": True, "public_key": params.get("pbk", ""), "short_id": params.get("sid", "")
            }
    
    inbounds = []
    if mode in ["VPN (TUN)", "Умный VPN (Split)"]:
        inbounds.append({
            "type": "tun", "tag": "tun-in", 
            "address": ["172.19.0.1/30", "fdfe:dcba:9876::1/126"], 
            "auto_route": True, "strict_route": True, "stack": "system", "sniff": True
        })
    else:
        inbounds.append({"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 10808, "sniff": True})

    rules = [
        {"protocol": "dns", "outbound": "dns-out"},
        {"ip_cidr": [f"{server_host}/32"], "outbound": "direct-out"},
        {"ip_cidr": ["192.168.0.0/16", "10.0.0.0/8", "127.0.0.0/8"], "outbound": "direct-out"}
    ]
    if mode == "Умный VPN (Split)":
        rules.insert(0, {"domain_suffix": ["google.com", "googleapis.com", "gstatic.com"], "outbound": "vless-out"})
        rules.insert(1, {"domain_suffix": [".ru", ".рф", ".su", "yandex.ru", "vk.com", "mail.ru"], "outbound": "direct-out"})

    config = {
        "log": {"level": "error"},
        "dns": {"servers": [{"tag": "google-dns", "address": "8.8.8.8", "detour": "vless-out"}], "strategy": "ipv4_only"},
        "inbounds": inbounds,
        "outbounds": [vless_outbound, {"type": "direct", "tag": "direct-out"}, {"type": "dns", "tag": "dns-out"}],
        "route": {"rules": rules, "auto_detect_interface": True}
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f: json.dump(config, f, indent=4)

def monitor_process(process, vless_link, mode, log_callback, on_crash_callback, on_recover_callback):
    global current_retries, core_process
    process.wait()
    
    if not is_manually_stopped:
        core_process = None 
        
        if current_retries < MAX_RETRIES:
            current_retries += 1
            if log_callback: log_callback(f"Попытка восстановления {current_retries}/{MAX_RETRIES}...")
            
            time.sleep(1.5)
            
            result = start_vpn(vless_link, mode, log_callback, on_crash_callback, on_recover_callback, is_retry=True)
            if result == "успех":
                if on_recover_callback: on_recover_callback(mode)
            else:
                lock_network()
                if on_crash_callback: on_crash_callback(result)
        else:
            lock_network()
            if on_crash_callback: on_crash_callback("Лимит попыток исчерпан")

def start_vpn(vless_link, mode, log_callback=None, on_crash_callback=None, on_recover_callback=None, is_retry=False):
    global core_process, is_manually_stopped, current_retries
    
    if not is_retry:
        current_retries = 0
        is_manually_stopped = False
    
    unlock_network()
    if core_process is not None: return "уже работает"
    
    parsed_data = parse_vless_link(vless_link)
    if not parsed_data: return "ошибка ссылки"
    
    generate_singbox_config(parsed_data, mode)
    os.system("/usr/bin/sudo -n /usr/bin/killall sing-box 2>/dev/null || killall sing-box 2>/dev/null")
    
    try:
        # УБРАЛИ /usr/bin/env. Теперь sudo видит ТОЛЬКО разрешенный sing-box
        if mode in ["VPN (TUN)", "Умный VPN (Split)"]:
            cmd = ["/usr/bin/sudo", "-n", SINGBOX_PATH, "run", "-c", CONFIG_FILE]
        else:
            cmd = [SINGBOX_PATH, "run", "-c", CONFIG_FILE]
            
        core_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=HOME_DIR)
        
        def read_logs():
            for line in core_process.stdout:
                if line and log_callback: log_callback(re.sub(r'\x1b\[[0-9;]*m', '', line.strip()))
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
        os.system("/usr/bin/sudo -n /usr/bin/killall sing-box 2>/dev/null || killall sing-box 2>/dev/null")
        core_process.terminate()
        core_process = None
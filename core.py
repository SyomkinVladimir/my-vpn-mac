import json
import subprocess
import os
import re
import platform
import threading
from urllib.parse import urlparse, unquote, parse_qs

core_process = None
is_manually_stopped = False

# --- НОВЫЙ БЛОК: УПРАВЛЕНИЕ ФАЙРВОЛОМ (KILL SWITCH) ---
def lock_network():
    """Жестко блокирует весь интернет-трафик через pf."""
    # Правило 'block drop all' приказывает ядру macOS сбрасывать любые пакеты
    os.system('echo "block drop all" | sudo pfctl -e -f - 2>/dev/null')

def unlock_network():
    """Снимает блокировку и выключает pf."""
    os.system('sudo pfctl -d 2>/dev/null')
# -------------------------------------------------------

def parse_vless_link(vless_url):
    try:
        vless_url = re.sub(r'\s+', '', vless_url)
        if '#' in vless_url: vless_url = vless_url.split('#')[0]
        parsed_url = urlparse(vless_url)
        if parsed_url.scheme != 'vless': return None
        qs = parse_qs(parsed_url.query)
        params = {k: unquote(v[0]) for k, v in qs.items()}
        return {
            "uuid": parsed_url.username,     
            "server_ip": parsed_url.hostname, 
            "port": int(parsed_url.port),    
            "params": params                 
        }
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
            "type": "tun", "tag": "tun-in", "address": ["172.19.0.1/30"],
            "auto_route": True, "strict_route": True, "stack": "system", "sniff": True
        })
    else:
        inbounds.append({
            "type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 10808, "sniff": True
        })

    rules = [
        {"protocol": "dns", "outbound": "dns-out"},
        {"ip_cidr": [f"{server_host}/32"], "outbound": "direct-out"},
        {"ip_cidr": ["192.168.0.0/16", "10.0.0.0/8", "127.0.0.0/8"], "outbound": "direct-out"}
    ]
    if mode == "Умный VPN (Split)":
        rules.insert(1, {"domain_suffix": [".ru", ".рф", ".su", "yandex.ru", "vk.com", "mail.ru"], "outbound": "direct-out"})

    config = {
        "log": {"level": "error"},
        "dns": {"servers": [{"tag": "google-dns", "address": "8.8.8.8", "detour": "vless-out"}], "strategy": "ipv4_only"},
        "inbounds": inbounds,
        "outbounds": [vless_outbound, {"type": "direct", "tag": "direct-out"}, {"type": "dns", "tag": "dns-out"}],
        "route": {"rules": rules, "auto_detect_interface": True}
    }
    with open("config.json", "w", encoding="utf-8") as f: json.dump(config, f, indent=4)

def monitor_process(process, on_crash_callback):
    process.wait()
    if not is_manually_stopped:
        lock_network() # <--- ЕСЛИ УПАЛО, БЛОКИРУЕМ СЕТЬ
        if on_crash_callback: on_crash_callback()

def start_vpn(vless_link, mode, log_callback=None, on_crash_callback=None):
    global core_process, is_manually_stopped
    is_manually_stopped = False
    unlock_network() # На всякий случай снимаем блокировку перед стартом
    
    if core_process is not None: return "уже работает"
    parsed_data = parse_vless_link(vless_link)
    if not parsed_data: return "ошибка ссылки"
    generate_singbox_config(parsed_data, mode)
    os.system("sudo killall sing-box 2>/dev/null")
    try:
        cmd = ["./sing-box", "run", "-c", "config.json"]
        if mode in ["VPN (TUN)", "Умный VPN (Split)"]: cmd = ["sudo"] + cmd
        core_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        if log_callback:
            def read_logs():
                for line in core_process.stdout:
                    if line: log_callback(re.sub(r'\x1b\[[0-9;]*m', '', line.strip()))
            threading.Thread(target=read_logs, daemon=True).start()
        threading.Thread(target=monitor_process, args=(core_process, on_crash_callback), daemon=True).start()
        if mode == "Системный прокси": set_system_proxy(True)
        return "успех"
    except Exception as e:
        core_process = None
        return f"ошибка: {e}"

def stop_vpn():
    global core_process, is_manually_stopped
    is_manually_stopped = True
    unlock_network() # <--- СНИМАЕМ БЛОКИРОВКУ, КОГДА ОТКЛЮЧАЕМ РУКАМИ
    set_system_proxy(False)
    if core_process is not None:
        os.system("sudo killall sing-box 2>/dev/null")
        core_process.terminate()
        core_process = None
import json
import subprocess
import os
import re
import platform
import threading
from urllib.parse import urlparse, unquote, parse_qs

# Глобальная переменная для управления процессом (handle)
core_process = None

def parse_vless_link(vless_url):
    try:
        vless_url = re.sub(r'\s+', '', vless_url)
        if '#' in vless_url:
            vless_url = vless_url.split('#')[0]
        
        parsed_url = urlparse(vless_url)
        if parsed_url.scheme != 'vless': 
            return None
        
        qs = parse_qs(parsed_url.query)
        params = {k: unquote(v[0]) for k, v in qs.items()}

        return {
            "uuid": parsed_url.username,     
            "server_ip": parsed_url.hostname, 
            "port": int(parsed_url.port),    
            "params": params                 
        }
    except Exception:
        return None

def set_system_proxy(enable=True):
    if platform.system() != "Darwin":
        return
    interface = "Wi-Fi"
    state = "on" if enable else "off"
    try:
        subprocess.run(["networksetup", "-setwebproxystate", interface, state])
        subprocess.run(["networksetup", "-setsecurewebproxystate", interface, state])
        if enable:
            subprocess.run(["networksetup", "-setwebproxy", interface, "127.0.0.1", "10808"])
            subprocess.run(["networksetup", "-setsecurewebproxy", interface, "127.0.0.1", "10808"])
    except Exception as e:
        print(f"Proxy error: {e}")

def generate_singbox_config(data, mode):
    server_host = data["server_ip"]
    params = data["params"]

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
            
    inbounds = []
    if mode == "VPN (TUN)":
        inbounds.append({
            "type": "tun",
            "tag": "tun-in",
            # Строку "interface_name": "utun" мы полностью УДАЛИЛИ
            "address": ["172.19.0.1/30"], # ИСПРАВЛЕНО: Новый синтаксис (список)
            "auto_route": True,
            "strict_route": True,
            "stack": "system",
            "sniff": True
        })
    else:
        inbounds.append({
            "type": "mixed",
            "tag": "mixed-in",
            "listen": "127.0.0.1",
            "listen_port": 10808,
            "sniff": True
        })

    config = {
        "log": {"level": "error"},
        # --- НОВЫЙ БЛОК: УЧИМ ЯДРО ПОНИМАТЬ ИМЕНА САЙТОВ ---
        "dns": {
            "servers": [
                {"tag": "google-dns", "address": "8.8.8.8", "detour": "vless-out"}
            ],
            "strategy": "ipv4_only" # Защита от утечек IPv6
        },
        "inbounds": inbounds,
        "outbounds": [
            vless_outbound, 
            {"type": "direct", "tag": "direct-out"},
            {"type": "dns", "tag": "dns-out"} # Специальный шлюз для обработки DNS
        ],
        "route": {
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"}, # Перехватываем DNS
                {"ip_cidr": [f"{server_host}/32"], "outbound": "direct-out"}
            ],
            "auto_detect_interface": True
        }
    }

    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def start_vpn(vless_link, mode, log_callback=None, test_mode=False):
    global core_process
    
    if test_mode:
        if log_callback: log_callback("> [TEST] Имитация запуска...")
        return "успех"

    if core_process is not None:
        return "уже работает"
    
    parsed_data = parse_vless_link(vless_link)
    if not parsed_data: return "ошибка ссылки"
    
    generate_singbox_config(parsed_data, mode)
    
    # Очистка старых процессов с правами sudo
    os.system("sudo killall sing-box 2>/dev/null")

    try:
        cmd = ["./sing-box", "run", "-c", "config.json"]
        if mode == "VPN (TUN)":
            cmd = ["sudo"] + cmd

        core_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        if log_callback:
            def read_logs():
                for line in core_process.stdout:
                    if line:
                        clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line.strip())
                        log_callback(clean_line)
            threading.Thread(target=read_logs, daemon=True).start()

        if mode == "Системный прокси":
            set_system_proxy(True)
        
        return "успех"
    except Exception as e:
        core_process = None
        return f"ошибка: {e}"

def stop_vpn():
    global core_process
    set_system_proxy(False)
    if core_process is not None:
        os.system("sudo killall sing-box 2>/dev/null")
        core_process.terminate()
        core_process = None
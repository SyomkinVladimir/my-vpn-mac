import json
import subprocess
import os
import re
import platform
from urllib.parse import urlparse, unquote, parse_qs
def parse_vless_link(vless_url):
    try:
        vless_url =re.sub(r'\s+', '', vless_url)
        if '#' in vless_url:
            vless_url = vless_url.split('#')[0]
        
        parsed_url = urlparse(vless_url)
        if parsed.scheme != 'vless':
            return None
        
        qs = parse_qs(parsed_url.query)
        params = {k: unquote(v[0]) for k, v in qs.items()}

        return {
            "uuid": parsed.username,
            "server_ip": parsed.hostname,
            "port": int(parsed.port),
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



def generate_singbox_config(data):
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
            "utls":{"enabled": True, "fingerprint": params.get("fp" , "chrome")},
            "alp": ["h2", "http/1.1"]
        
            }
        if params.get("security") == "reality":
            vless_outbound["tls"]["reality"] = {
                "enabled": True,
                "public_key": params.get("pbk", ""),
                "short_id": params.get("sid", "")
            }
    config ={
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
        "auto_detect_interface": True
    }

    with open("config.json", "w") as f:
        json.dump(config, f, indent=4)



    


                



    

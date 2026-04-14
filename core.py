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



    

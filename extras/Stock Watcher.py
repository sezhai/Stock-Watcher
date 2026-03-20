import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time
import threading
import ctypes
import json
import os
import math
import random
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor

# ================= 常量配置 =================
VERSION = "1.0.0"
CONFIG_FILE = "stock_config.json"
WINDOW_STATE_FILE = "window_state.json"

WINDOW_BG_COLOR = "black"
WINDOW_ALPHA = 0.6
WINDOW_WIDTH = 220
WINDOW_HEIGHT_PER_ITEM = 40

FONT_CONFIG = ("Microsoft YaHei UI", 10, "bold")
COLOR_UP = "#FF4D4F"   # 红色
COLOR_DOWN = "#52C41A" # 绿色
COLOR_NEUTRAL = "#cccccc"

# ================= 帮助文档文本 =================
HELP_TEXT = """【监控代码输入格式说明】

在设置面板中，必须先正确选择单选按钮（"股票/外汇" 或 "数字货币"），然后按以下规则输入代码：

1. 股票与指数 (选择 "股票/外汇")
--------------------------------------------------[A股/国内指数] (经由腾讯 API)
• 格式: 交易所小写拼音首字母 + 6位数字代码
• 示例: sh000001 (上证指数), sh600519 (贵州茅台), sz000858 (五粮液), sz399001 (深证成指)

[美股] (经由新浪 API)
• 格式: gb_ + 小写股票代码
• 示例: gb_aapl (苹果), gb_tsla (特斯拉), gb_qqq (纳指ETF)

[港股] (经由腾讯 API)
• 格式: hk + 数字代码
• 示例: hk00700 (腾讯控股), hk09988 (阿里巴巴)


2. 期货与外汇 (选择 "股票/外汇")
--------------------------------------------------
[国际大宗商品/外盘期货] (经由新浪 API)
• 格式: hf_ + 品种大写代码
• 示例: hf_GC (COMEX黄金), hf_CL (WTI原油), hf_SI (白银)

[国内期货] (经由新浪 API)
• 格式: nf_ + 品种代码
• 示例: nf_AU0 (沪金连续), nf_RB0 (螺纹钢连续)[外汇汇率] (经由新浪 API)
• 格式: 6位大写字母组合 (基础货币+计价货币)
• 示例: EURUSD (欧元/美元), USDJPY (美元/日元), USDCNH (美元/离岸人民币)


3. 数字货币 (选择 "数字货币")
--------------------------------------------------
代码内置了自动拼接 USDT 的逻辑，并提供 币安 -> Gate.io -> CoinGecko 的三级降级容灾。
• 格式: 代币大写简称 (最简写法) 或 完整交易对
• 示例: 
  BTC 或 BTCUSDT (比特币)
  ETH 或 ETHUSDT (以太坊)
  SOL (Solana)
  DOGE (狗狗币)
"""

# 默认监控列表
DEFAULT_ITEMS =[
    {"code": "sh000001", "name": "上证指数", "type": "stock", "alert_price": 0},
    {"code": "gb_qqq", "name": "纳指QQQ", "type": "stock", "alert_price": 0},
    {"code": "hf_GC", "name": "国际金价", "type": "stock", "alert_price": 0},
    {"code": "BTC", "name": "比特币", "type": "crypto", "alert_price": 0}
]

# ================= 全局状态 =================
ITEMS =[]
items_lock = threading.Lock()
last_alert_status = {}  

root = None
main_frame = None
row_widgets_list =[]
last_ui_hash = ""

is_shaking = False
shake_anchor = None

# ================= 网络层提速 (防缓存优化) =================
GLOBAL_SESSION = requests.Session()
_retry = Retry(total=1, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=20)
GLOBAL_SESSION.mount('http://', _adapter)
GLOBAL_SESSION.mount('https://', _adapter)

# 安全防缓存方案
GLOBAL_SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0'
})

def safe_float(value, default=0.0):
    if value == "" or value is None: return default
    try:
        f = float(value)
        return default if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return default

def get_with_retry(url, headers=None, timeout=3):
    try:
        req_headers = headers if headers else {}
        resp = GLOBAL_SESSION.get(url, headers=req_headers, timeout=timeout)
        resp.raise_for_status()
        return resp
    except:
        return None

# ================= 并发数据拉取层 =================
def fetch_all_data_concurrent(stocks, cryptos):
    results = {}
    
    sina_codes =[]
    tencent_codes =[]
    
    for i in stocks:
        code = i['code']
        if code.startswith(("nf_", "Au", "Ag", "Pt", "gds_", "hf_", "gb_", "usr_", "int_", "s_", "fx_")):
            sina_codes.append(code)
        elif code.isupper() and (len(code) == 6 or code == "DINIW"):
            sina_codes.append(code)
        else:
            tencent_codes.append(code)

    def _fetch_tencent():
        if not tencent_codes: return {}
        resp = get_with_retry(f"http://qt.gtimg.cn/q={','.join(tencent_codes)}", timeout=2.5)
        local_res = {}
        if resp:
            for line in resp.content.decode('gbk', errors='ignore').split(';'):
                if '="' not in line: continue
                parts = line.strip().split('="')
                api_key = parts[0].split('v_')[-1]
                data = parts[1].strip('"').split('~')
                if len(data) > 4:
                    curr, last = safe_float(data[3]), safe_float(data[4])
                    local_res[api_key] = (curr, (curr - last) / last * 100 if last > 0 else 0.0)
        return local_res

    def _fetch_sina():
        if not sina_codes: return {}
        resp = get_with_retry(f"http://hq.sinajs.cn/list={','.join(sina_codes)}", headers={'Referer': 'http://finance.sina.com.cn'}, timeout=2.5)
        local_res = {}
        if resp:
            for line in resp.content.decode('gbk', errors='ignore').split(';'):
                if '="' not in line: continue
                parts = line.strip().split('="')
                api_key = parts[0].split('hq_str_')[-1]
                data = parts[1].strip('";').split(',')
                if len(data) < 2: continue
                try:
                    if api_key.startswith(('gb_', 'usr_', 'int_')):
                        if len(data) > 2: local_res[api_key] = (safe_float(data[1]), safe_float(data[2]))
                    elif api_key.startswith('hf_'):
                        curr = safe_float(data[0])
                        if len(data) > 7:
                            last_settle = safe_float(data[7])
                            pct = (curr - last_settle) / last_settle * 100 if last_settle > 0 else 0.0
                        else:
                            pct = safe_float(data[1]) if len(data) > 1 else 0.0
                        local_res[api_key] = (curr, pct)
                    elif api_key.isupper() and (len(api_key) == 6 or api_key == "DINIW"):
                        if len(data) > 3:
                            curr = safe_float(data[1])
                            last_close = safe_float(data[3])
                            pct = (curr - last_close) / last_close * 100 if last_close > 0 else 0.0
                            local_res[api_key] = (curr, pct)
                    else:
                        curr, change = safe_float(data[0]), safe_float(data[1])
                        last = curr - change
                        local_res[api_key] = (curr, (change / last) * 100 if last > 0 else 0.0)
                except: pass
        return local_res

    def _fetch_crypto(item):
        code = item.get("code", "").upper()
        symbol = code if 'USDT' in code else f"{code}USDT"
        
        resp = get_with_retry(f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}", timeout=1.5)
        if resp:
            try:
                data = resp.json()
                if 'lastPrice' in data:
                    return code, (safe_float(data.get('lastPrice')), safe_float(data.get('priceChangePercent')))
            except: pass
            
        gate_symbol = f"{code}_USDT" if "USDT" not in code else code.replace("USDT", "_USDT")
        resp = get_with_retry(f"https://api.gateio.ws/api/v4/spot/tickers?currency_pair={gate_symbol}", timeout=2.0)
        if resp:
            try:
                data = resp.json()[0]
                if 'last' in data:
                    return code, (safe_float(data.get('last')), safe_float(data.get('change_percentage')))
            except: pass
            
        symbol_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'DOGE': 'dogecoin', 'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano'}
        base_code = code.replace('USDT', '') if 'USDT' in code else code
        gecko_id = symbol_map.get(base_code, base_code.lower())
        resp = get_with_retry(f"https://api.coingecko.com/api/v3/simple/price?ids={gecko_id}&vs_currencies=usd&include_24hr_change=true", timeout=2.0)
        if resp:
            try:
                data = resp.json()
                if gecko_id in data:
                    return code, (safe_float(data[gecko_id].get('usd')), safe_float(data[gecko_id].get('usd_24h_change')))
            except: pass
            
        return None, None

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures =[executor.submit(_fetch_tencent), executor.submit(_fetch_sina)]
        for c in cryptos:
            futures.append(executor.submit(_fetch_crypto, c))
            
        for f in futures:
            res = f.result()
            if isinstance(res, dict):
                results.update(res)
            elif isinstance(res, tuple) and res[0]:
                results[res[0]] = res[1]

    return results

# ================= 配置系统 =================
AUTH_FILE = ".app_auth"
SECRET_SALT = "Yang_Stock_Watcher_2026_@#!" # 警告：发布前请修改此随机字符串并自行妥善保存

def get_machine_code():
    """获取本机硬件指纹"""
    mac = str(uuid.getnode())
    return hashlib.md5(mac.encode('utf-8')).hexdigest()[:8].upper()

def generate_expected_code(machine_code):
    """根据机器码和内部盐生成合法激活码"""
    raw_str = machine_code + SECRET_SALT
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16].upper()

def check_authorization():
    """执行拦截验证"""
    machine_code = get_machine_code()
    expected_code = generate_expected_code(machine_code)
    
    # 检查本地是否已存在有效授权
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                saved_code = f.read().strip()
                if saved_code == expected_code:
                    return True
        except:
            pass
            
    # 弹出验证窗口
    auth_window = tk.Tk()
    auth_window.title("软件激活")
    auth_window.geometry("350x180+400+300")
    auth_window.attributes("-topmost", True)
    
    tk.Label(auth_window, text="请输入激活码以使用本软件", font=("Microsoft YaHei", 10, "bold")).pack(pady=10)
    
    frame = tk.Frame(auth_window)
    frame.pack(pady=5)
    tk.Label(frame, text=f"您的机器码: {machine_code}", fg="red").pack()
    tk.Label(frame, text="请将机器码发送给开发者获取激活码").pack()
    
    code_entry = tk.Entry(auth_window, width=30, justify="center")
    code_entry.pack(pady=10)
    
    def verify():
        user_input = code_entry.get().strip().upper()
        if user_input == expected_code:
            with open(AUTH_FILE, 'w') as f:
                f.write(expected_code)
            messagebox.showinfo("激活成功", "授权验证通过，欢迎使用！")
            auth_window.destroy()
        else:
            messagebox.showerror("错误", "激活码无效！")
            
    def on_close():
        auth_window.destroy()
        sys.exit(0)
        
    tk.Button(auth_window, text="验证并激活", command=verify, bg="#4CAF50", fg="white", width=15).pack()
    auth_window.protocol("WM_DELETE_WINDOW", on_close)
    
    auth_window.mainloop()
    
    # 循环结束后再次严格校验（防止被绕过）
    if not os.path.exists(AUTH_FILE):
        sys.exit(0)
    with open(AUTH_FILE, 'r') as f:
        if f.read().strip() != expected_code:
            sys.exit(0)
def load_config():
    global ITEMS
    if not os.path.exists(CONFIG_FILE):
        ITEMS = DEFAULT_ITEMS.copy()
        return
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            ITEMS = data.get("items", DEFAULT_ITEMS)
    except:
        ITEMS = DEFAULT_ITEMS.copy()

def save_config():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({"items": ITEMS}, f, ensure_ascii=False, indent=4)

def load_window_state():
    if os.path.exists(WINDOW_STATE_FILE):
        try:
            with open(WINDOW_STATE_FILE, 'r', encoding='utf-8') as f:
                root.geometry(json.load(f).get("geometry", ""))
        except: pass

def save_window_state():
    if root and root.winfo_exists():
        with open(WINDOW_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump({"geometry": root.geometry()}, f)

# ================= 报警抖动引擎 (无限模式) =================
def stop_shake():
    global is_shaking, shake_anchor
    if is_shaking:
        is_shaking = False
        if shake_anchor and root and root.winfo_exists():
            try:
                root.geometry(f"+{shake_anchor[0]}+{shake_anchor[1]}")
            except: pass
            shake_anchor = None

def start_continuous_shake():
    global is_shaking, shake_anchor
    if is_shaking: return
    is_shaking = True
    shake_anchor = (root.winfo_x(), root.winfo_y())
    shake_loop()

def shake_loop():
    global is_shaking, shake_anchor
    if not is_shaking or not root or not root.winfo_exists():
        return
    dx = random.randint(-8, 8)
    dy = random.randint(-8, 8)
    try:
        root.geometry(f"+{shake_anchor[0]+dx}+{shake_anchor[1]+dy}")
    except: pass
    
    root.after(20, shake_loop)

# ================= UI 渲染与事件 =================
def on_mouse_down(e):
    stop_shake()
    root.start_x = e.x
    root.start_y = e.y

def bind_events(widget):
    widget.bind("<Button-1>", on_mouse_down)
    widget.bind("<B1-Motion>", lambda e: root.geometry(f"+{root.winfo_x() + e.x - root.start_x}+{root.winfo_y() + e.y - root.start_y}"))
    widget.bind("<Button-3>", lambda e:[stop_shake(), show_context_menu(e)])
    widget.bind("<Double-Button-1>", lambda e:[stop_shake(), root.iconify() or root.overrideredirect(False)])

def refresh_labels(data_map):
    global main_frame, row_widgets_list, last_ui_hash
    should_shake = False

    if not root or not root.winfo_exists(): return

    if main_frame is None:
        main_frame = tk.Frame(root, bg=WINDOW_BG_COLOR)
        main_frame.pack(fill="both", expand=True)
        bind_events(main_frame)
        
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_columnconfigure(2, weight=1)

    with items_lock: current_items = ITEMS.copy()
    
    ui_hash = "|".join([item.get('code', '') for item in current_items])
    
    if ui_hash != last_ui_hash:
        for w in main_frame.winfo_children(): w.destroy()
        row_widgets_list.clear()
        
        for i, item in enumerate(current_items):
            widgets = {}
            
            name_lbl = tk.Label(main_frame, text=item.get('name')[:8], bg=WINDOW_BG_COLOR, fg="white", font=FONT_CONFIG, anchor="w")
            name_lbl.grid(row=i, column=0, sticky="w", padx=(10, 5), pady=5)
            bind_events(name_lbl)
            widgets['name'] = name_lbl
            
            prc_lbl = tk.Label(main_frame, text="--", bg=WINDOW_BG_COLOR, fg="white", font=FONT_CONFIG, anchor="e")
            prc_lbl.grid(row=i, column=1, sticky="e", padx=(5, 5), pady=5)
            bind_events(prc_lbl)
            widgets['price'] = prc_lbl
            
            pct_lbl = tk.Label(main_frame, text="--%", bg=WINDOW_BG_COLOR, fg="white", font=FONT_CONFIG, anchor="e")
            pct_lbl.grid(row=i, column=2, sticky="e", padx=(5, 10), pady=5)
            bind_events(pct_lbl)
            widgets['pct'] = pct_lbl
            
            row_widgets_list.append(widgets)
        last_ui_hash = ui_hash

    for i, item in enumerate(current_items):
        if i >= len(row_widgets_list): break
        code = item.get('code', '')
        widgets = row_widgets_list[i]
        
        curr, pct, color = 0.0, 0.0, COLOR_NEUTRAL
        if code in data_map:
            curr, pct = data_map[code]
            color = COLOR_UP if pct > 0 else (COLOR_DOWN if pct < 0 else COLOR_NEUTRAL)
            
            alert_price = safe_float(item.get('alert_price', 0.0))
            if alert_price > 0 and curr > 0:
                state = last_alert_status.get(code, {})
                
                if state.get("target_price") != alert_price:
                    direction = 'high' if alert_price > curr else 'low'
                    state = {"target_price": alert_price, "direction": direction, "fired": False}
                    last_alert_status[code] = state
                
                if not state["fired"]:
                    if state["direction"] == 'high' and curr >= alert_price:
                        should_shake = True
                        state["fired"] = True
                    elif state["direction"] == 'low' and curr <= alert_price:
                        should_shake = True
                        state["fired"] = True
                else:
                    if state["direction"] == 'high' and curr < alert_price:
                        state["fired"] = False
                    elif state["direction"] == 'low' and curr > alert_price:
                        state["fired"] = False

        widgets['name'].config(fg=color)
        
        if code in data_map:
            decimals = 4 if code.isupper() and (len(code) == 6 or code == "DINIW") else 2
            price_txt = f"{curr:,.{decimals}f}"
        else:
            price_txt = "--"
            
        widgets['price'].config(text=price_txt, fg=color)
        widgets['pct'].config(text=f"{pct:+.2f}%" if code in data_map else "--", fg=color)

    main_frame.update_idletasks()
    
    if not is_shaking:
        root.geometry(f"{main_frame.winfo_reqwidth()}x{main_frame.winfo_reqheight()}+{root.winfo_x()}+{root.winfo_y()}")

    if should_shake:
        start_continuous_shake()

def update_ui_loop():
    while True:
        with items_lock: 
            stocks =[i for i in ITEMS if i.get('type') == 'stock']
            cryptos =[i for i in ITEMS if i.get('type') == 'crypto']
        
        data = fetch_all_data_concurrent(stocks, cryptos)
        
        if root and root.winfo_exists():
            root.after(0, lambda d=data: refresh_labels(d))
            
        time.sleep(0.8)

# ================= 交互菜单 =================
def show_help_window():
    help_win = tk.Toplevel(root)
    help_win.title("代码格式说明")
    help_win.geometry("500x500")
    
    text_widget = tk.Text(help_win, wrap="word", padx=15, pady=15, font=("Microsoft YaHei", 9))
    text_widget.pack(fill="both", expand=True)
    text_widget.insert(tk.END, HELP_TEXT)
    text_widget.config(state=tk.DISABLED)

def show_context_menu(e):
    m = tk.Menu(root, tearoff=0)
    m.add_command(label="设置", command=open_settings)
    m.add_separator()
    m.add_command(label="退出", command=quit_app)
    m.tk_popup(e.x_root, e.y_root)

def open_settings():
    win = tk.Toplevel(root)
    win.title("资产及预警配置")
    # 增加窗口宽度以容纳中文字符按钮
    win.geometry("560x440")
    
    frame = tk.LabelFrame(win, text="监控列表 (点击行快速编辑)", padx=10, pady=10)
    frame.pack(fill="both", expand=True, padx=10, pady=10)
    
    lb = tk.Listbox(frame, height=8)
    lb.pack(side="left", fill="both", expand=True)
    
    def refresh_list():
        lb.delete(0, tk.END)
        for i in ITEMS:
            ap = i.get('alert_price', 0.0)
            alert_str = f" [预警:{ap}]" if ap > 0 else ""
            lb.insert(tk.END, f"{i['code']} | {i['name']} ({i['type']}){alert_str}")
    
    refresh_list()
    
    def move(direction):
        sel = lb.curselection()
        if not sel: return
        idx = sel[0]
        new_idx = idx + direction
        if 0 <= new_idx < len(ITEMS):
            with items_lock: ITEMS[idx], ITEMS[new_idx] = ITEMS[new_idx], ITEMS[idx]
            save_config(); refresh_list(); lb.selection_set(new_idx); refresh_labels({})
            
    def delete_item():
        sel = lb.curselection()
        if sel:
            with items_lock: ITEMS.pop(sel[0])
            save_config(); refresh_list(); refresh_labels({})

    # 按钮由符号改为中文，宽度适度增加到 width=6
    btn_frame = tk.Frame(frame)
    btn_frame.pack(side="right", fill="y", padx=5)
    tk.Button(btn_frame, text="向上", command=lambda: move(-1), width=6).pack(pady=(0, 5))
    tk.Button(btn_frame, text="向下", command=lambda: move(1), width=6).pack(pady=5)
    tk.Button(btn_frame, text="删除", fg="red", command=delete_item, width=6).pack(pady=(15, 0))
    
    # ================= 底部录入区重构：绝对居中排版 =================
    add_f = tk.Frame(win)
    add_f.pack(fill="x", padx=10, pady=(0, 10))
    
    # 1. 使用子 Frame 将输入框同行紧凑包裹，并强制居中
    form_frame = tk.Frame(add_f)
    form_frame.pack(anchor="center", pady=5)
    
    tk.Label(form_frame, text="代码:").grid(row=0, column=0, pady=5, sticky="e")
    e_code = tk.Entry(form_frame, width=11)
    e_code.grid(row=0, column=1, padx=(2, 15), pady=5)
    
    tk.Label(form_frame, text="名称:").grid(row=0, column=2, pady=5, sticky="e")
    e_name = tk.Entry(form_frame, width=11)
    e_name.grid(row=0, column=3, padx=(2, 15), pady=5)
    
    tk.Label(form_frame, text="预警价:").grid(row=0, column=4, pady=5, sticky="e")
    e_alert = tk.Entry(form_frame, width=11)
    e_alert.grid(row=0, column=5, padx=(2, 0), pady=5)
    
    # 2. 单选按钮独立一行，并强制居中
    type_frame = tk.Frame(add_f)
    type_frame.pack(anchor="center", pady=2)
    
    t_var = tk.StringVar(value="stock")
    tk.Radiobutton(type_frame, text="股票/外汇", var=t_var, value="stock").pack(side="left", padx=10)
    tk.Radiobutton(type_frame, text="数字货币", var=t_var, value="crypto").pack(side="left", padx=10)
    
    # 列表数据回填
    def on_list_select(event):
        sel = lb.curselection()
        if sel:
            item = ITEMS[sel[0]]
            e_code.delete(0, tk.END); e_code.insert(0, item.get('code', ''))
            e_name.delete(0, tk.END); e_name.insert(0, item.get('name', ''))
            e_alert.delete(0, tk.END); e_alert.insert(0, str(item.get('alert_price', 0.0) or ""))
            t_var.set(item.get('type', 'stock'))
    lb.bind('<<ListboxSelect>>', on_list_select)

    def do_add():
        c, n = e_code.get().strip(), e_name.get().strip()
        ap = safe_float(e_alert.get().strip(), 0.0)
        
        if c and n:
            with items_lock:
                found = False
                for i in ITEMS:
                    if i['code'] == c:
                        i.update({"name": n, "type": t_var.get(), "alert_price": ap})
                        found = True
                        break
                if not found:
                    ITEMS.append({"code": c, "name": n, "type": t_var.get(), "alert_price": ap})
            save_config()
            refresh_list()
            refresh_labels({})
            
            e_code.delete(0, tk.END)
            e_name.delete(0, tk.END)
            e_alert.delete(0, tk.END)
            
    # 3. 添加按钮跨越底部独立成行，并绝对居中
    tk.Button(add_f, text="添加 / 修改", command=do_add, bg="#4CAF50", fg="white", font=("Microsoft YaHei", 10, "bold"), width=20, pady=2).pack(anchor="center", pady=(10, 10))

    help_btn = tk.Button(add_f, text="代码输入格式说明", command=show_help_window, fg="#0066cc", relief="flat", cursor="hand2")
    help_btn.pack(anchor="center", pady=(0, 5))

def quit_app():
    save_window_state(); save_config()
    if root: root.quit()

# ================= 启动 =================
def main():
    check_authorization() 

    global root
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    
    load_config()
    root = tk.Tk()
    root.title("")
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", WINDOW_ALPHA)
    
    root.geometry(f"{WINDOW_WIDTH}x{len(ITEMS)*WINDOW_HEIGHT_PER_ITEM+20}+100+100")
    load_window_state()
    
    root.bind("<Map>", lambda e: root.after(100, lambda: root.overrideredirect(True)) if root.state()=='normal' and not root.overrideredirect() else None)
    refresh_labels({})
    
    threading.Thread(target=update_ui_loop, daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    main()
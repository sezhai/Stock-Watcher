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
from concurrent.futures import ThreadPoolExecutor

# ================= 常量配置 =================
VERSION = "1.2.1-infinite-alert-fixed"
CONFIG_FILE = "stock_config.json"
WINDOW_STATE_FILE = "window_state.json"

WINDOW_BG_COLOR = "black"
WINDOW_ALPHA = 0.6
WINDOW_WIDTH = 220
WINDOW_HEIGHT_PER_ITEM = 40

FONT_CONFIG = ("Microsoft YaHei UI", 10, "bold")
COLOR_UP = "#FF4D4F"
COLOR_DOWN = "#52C41A"
COLOR_NEUTRAL = "#cccccc"

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
last_alert_status = {}  # 智能报警状态机

root = None
main_frame = None
row_widgets_list =[]
last_ui_hash = ""

# 无限抖动状态机
is_shaking = False
shake_anchor = None

# ================= 网络层提速 =================
GLOBAL_SESSION = requests.Session()
_retry = Retry(total=1, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
_adapter = HTTPAdapter(max_retries=_retry, pool_connections=20, pool_maxsize=20)
GLOBAL_SESSION.mount('http://', _adapter)
GLOBAL_SESSION.mount('https://', _adapter)
GLOBAL_SESSION.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

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
        resp = get_with_retry(f"http://qt.gtimg.cn/q={','.join(tencent_codes)}")
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
        resp = get_with_retry(f"http://hq.sinajs.cn/list={','.join(sina_codes)}", headers={'Referer': 'http://finance.sina.com.cn'})
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
        if 'USDT' in code:
            resp = get_with_retry(f"https://api.binance.com/api/v3/ticker/24hr?symbol={code}", timeout=3)
            if resp:
                try:
                    data = resp.json()
                    return code, (safe_float(data.get('lastPrice')), safe_float(data.get('priceChangePercent')))
                except: pass
        else:
            symbol_map = {'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'DOGE': 'dogecoin', 'BNB': 'binancecoin', 'XRP': 'ripple', 'ADA': 'cardano'}
            gecko_id = symbol_map.get(code, code.lower())
            resp = get_with_retry(f"https://api.coingecko.com/api/v3/simple/price?ids={gecko_id}&vs_currencies=usd&include_24hr_change=true", timeout=3)
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
    """鼠标点击调用的：一键恢复平静并重置坐标"""
    global is_shaking, shake_anchor
    if is_shaking:
        is_shaking = False
        if shake_anchor and root and root.winfo_exists():
            try:
                root.geometry(f"+{shake_anchor[0]}+{shake_anchor[1]}")
            except: pass
            shake_anchor = None

def start_continuous_shake():
    """开启无限报警循环"""
    global is_shaking, shake_anchor
    if is_shaking: return
    is_shaking = True
    shake_anchor = (root.winfo_x(), root.winfo_y())
    shake_loop()

def shake_loop():
    """异步疯抖死循环"""
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
    stop_shake() # 点击即停止抖动并恢复原位
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
            
            # --- 智能双向预警逻辑 (Auto-Direction Alert) ---
            alert_price = safe_float(item.get('alert_price', 0.0))
            
            # 价格必须有效(>0)时才进行判断，防止初始化网络异常导致误报
            if alert_price > 0 and curr > 0:
                state = last_alert_status.get(code, {})
                
                # 1. 如果发现了新的预警设定，动态识别用户意图
                if state.get("target_price") != alert_price:
                    direction = 'high' if alert_price > curr else 'low'
                    state = {
                        "target_price": alert_price,
                        "direction": direction,
                        "fired": False
                    }
                    last_alert_status[code] = state
                
                # 2. 判断是否触发
                if not state["fired"]:
                    if state["direction"] == 'high' and curr >= alert_price:
                        should_shake = True
                        state["fired"] = True
                    elif state["direction"] == 'low' and curr <= alert_price:
                        should_shake = True
                        state["fired"] = True
                else:
                    # 3. 已经触发且你已停止了它，若价格反弹回安全区，则自动重新武装(Re-arm)
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
    
    # 仅当不在抖动状态时，才去刷新真实窗口大小
    if not is_shaking:
        root.geometry(f"{main_frame.winfo_reqwidth()}x{main_frame.winfo_reqheight()}+{root.winfo_x()}+{root.winfo_y()}")

    # 触发报警抖动
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
            
        time.sleep(1.0)

# ================= 交互菜单 =================
def show_context_menu(e):
    m = tk.Menu(root, tearoff=0)
    m.add_command(label="设置", command=open_settings)
    m.add_separator()
    m.add_command(label="退出", command=quit_app)
    m.tk_popup(e.x_root, e.y_root)

def open_settings():
    win = tk.Toplevel(root)
    win.title("资产及预警配置")
    win.geometry("490x360")
    
    frame = tk.LabelFrame(win, text="监控列表 (提示: 点击列表可快速读取修改)", padx=10, pady=10)
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

    btn_frame = tk.Frame(frame)
    btn_frame.pack(side="right", fill="y", padx=5)
    tk.Button(btn_frame, text="↑ 上移", command=lambda: move(-1)).pack(pady=2)
    tk.Button(btn_frame, text="↓ 下移", command=lambda: move(1)).pack(pady=2)
    tk.Button(btn_frame, text="× 删除", fg="red", command=delete_item).pack(pady=10)
    
    add_f = tk.Frame(win)
    add_f.pack(fill="x", padx=10, pady=5)
    
    tk.Label(add_f, text="代码:").grid(row=0, column=0, pady=2, sticky="e")
    e_code = tk.Entry(add_f, width=12)
    e_code.grid(row=0, column=1, padx=5, pady=2)
    
    tk.Label(add_f, text="名称:").grid(row=0, column=2, pady=2, sticky="e")
    e_name = tk.Entry(add_f, width=12)
    e_name.grid(row=0, column=3, padx=5, pady=2)
    
    tk.Label(add_f, text="预警价:").grid(row=1, column=0, pady=2, sticky="e")
    e_alert = tk.Entry(add_f, width=12)
    e_alert.grid(row=1, column=1, padx=5, pady=2)
    
    t_var = tk.StringVar(value="stock")
    tk.Radiobutton(add_f, text="股票/外汇", var=t_var, value="stock").grid(row=1, column=2, padx=5)
    tk.Radiobutton(add_f, text="数字货币", var=t_var, value="crypto").grid(row=1, column=3, padx=5)
    
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
            
    tk.Button(add_f, text="添加 / 修改", command=do_add, bg="#4CAF50", fg="white").grid(row=0, column=4, rowspan=2, padx=10, sticky="ns")

def quit_app():
    save_window_state(); save_config()
    if root: root.quit()

# ================= 启动 =================
def main():
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
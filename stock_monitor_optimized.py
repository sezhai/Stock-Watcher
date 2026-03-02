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
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import math
import random
from functools import partial, wraps
import tempfile
import shutil

# ================= 常量配置 =================
class AppConfig:
    """应用配置常量"""
    VERSION = "0.6.0-crypto"
    
    # 文件配置
    CONFIG_FILE = "stock_config.json"
    LOG_FILE = "stock_monitor.log"
    WINDOW_STATE_FILE = "window_state.json"
    
    # 日志配置
    LOG_LEVEL = logging.DEBUG
    LOG_MAX_BYTES = 5 * 1024 * 1024
    LOG_BACKUP_COUNT = 3
    
    # UI配置
    MAX_DISPLAY_NAME_LEN = 8
    WINDOW_BG_COLOR = "black"
    WINDOW_ALPHA = 0.6
    WINDOW_WIDTH = 220
    WINDOW_HEIGHT_PER_STOCK = 40
    INITIAL_WINDOW_X = 100
    INITIAL_WINDOW_Y = 100
    
    # 显示配置
    MIN_VIEW_CEILING = 2.5
    BAR_LINE_WIDTH = 8
    BAR_CANVAS_WIDTH = 150
    BAR_CANVAS_HEIGHT = 24
    
    # 成交量配置
    VOLUME_RATIO_HIGH = 1.5
    VOLUME_RATIO_LOW = 0.6
    TRADING_MINUTES_THRESHOLD = 5
    
    # 动画配置
    SHAKE_INTENSITY = 10
    SHAKE_STEPS = 15
    SHAKE_INTERVAL = 0.02
    
    # 网络配置
    REQUEST_TIMEOUT = 5
    REQUEST_RETRIES = 3
    REQUEST_BACKOFF_FACTOR = 0.5
    
    # 刷新配置
    REFRESH_RATE = 1
    
    # 字体配置
    FONT_NAME = "Microsoft YaHei UI"
    FONT_SIZE = 10
    FONT_WEIGHT = "bold"
    
    # 颜色配置
    COLOR_UP = "#FF4D4F"
    COLOR_DOWN = "#52C41A"
    COLOR_NEUTRAL = "#cccccc"
    COLOR_BRACKET = "#555555"
    COLOR_TRACK = "#333333"
    
    # 数字货币API配置
    CRYPTO_API_TIMEOUT = 5
    CRYPTO_REFRESH_RATE = 2  # 更新更频繁


# ================= 日志系统 =================
def setup_logging():
    """初始化日志系统"""
    logger = logging.getLogger('stock_monitor')
    logger.setLevel(AppConfig.LOG_LEVEL)
    
    if logger.handlers:
        return logger
    
    try:
        handler = RotatingFileHandler(
            AppConfig.LOG_FILE,
            maxBytes=AppConfig.LOG_MAX_BYTES,
            backupCount=AppConfig.LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except Exception as e:
        print(f"Failed to setup file logger: {e}")
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logging()


# ================= 工具函数 =================
def timeit(func):
    """性能监控装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            elapsed = time.time() - start
            if elapsed > 0.1:
                logger.debug(f"{func.__name__} took {elapsed:.3f}s")
    return wrapper


def safe_float(value, default=0.0):
    """安全的浮点数转换"""
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """安全的整数转换"""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def validate_stock_code(code):
    """验证股票代码格式"""
    if not code:
        return False, "代码不能为空"
    if len(code) < 1 or len(code) > 20:
        return False, "代码长度应在1-20之间"
    return True, "OK"


def validate_stock_name(name):
    """验证股票名称格式"""
    if not name:
        return False, "名称不能为空"
    if len(name) < 2 or len(name) > 50:
        return False, "名称长度应在2-50之间"
    return True, "OK"


def get_with_retry(url, timeout=None, retries=None):
    """带重试机制的HTTP请求"""
    timeout = timeout or AppConfig.REQUEST_TIMEOUT
    retries = retries or AppConfig.REQUEST_RETRIES
    
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=AppConfig.REQUEST_BACKOFF_FACTOR,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.Timeout:
        logger.warning(f"Request timeout after {retries} retries: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request failed: {e}")
        return None
    finally:
        session.close()


# ================= 数字货币 API =================
class CryptoAPI:
    """数字货币 API 管理类"""
    
    @staticmethod
    @timeit
    def get_binance_price(symbol):
        """从币安获取数字货币价格"""
        try:
            # 币安 API
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol.upper()}"
            resp = get_with_retry(url, timeout=AppConfig.CRYPTO_API_TIMEOUT)
            
            if not resp:
                return None
            
            data = resp.json()
            current_price = safe_float(data.get('lastPrice'))
            change_percent = safe_float(data.get('priceChangePercent'))
            
            return {
                'code': symbol,
                'price': current_price,
                'change_percent': change_percent,
                'high_24h': safe_float(data.get('highPrice')),
                'low_24h': safe_float(data.get('lowPrice')),
                'volume': safe_float(data.get('volume')),
                'quote_asset_volume': safe_float(data.get('quoteAssetVolume'))
            }
        except Exception as e:
            logger.warning(f"Error fetching Binance data for {symbol}: {e}")
            return None
    
    @staticmethod
    @timeit
    def get_coinmarketcap_price(symbol):
        """从 CoinMarketCap 获取数字货币价格"""
        try:
            # 使用免费 API (需要自己设置 API key，这里使用备选方案)
            # 如果有 API key，可以用：
            # url = f"https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={symbol}"
            # headers = {"X-CMC_PRO_API_KEY": "your_api_key"}
            
            # 备选：使用 CoinGecko API (无需 key)
            symbol_map = {
                'BTC': 'bitcoin',
                'ETH': 'ethereum',
                'XRP': 'ripple',
                'ADA': 'cardano',
                'SOL': 'solana',
                'DOT': 'polkadot',
                'DOGE': 'dogecoin',
                'SHIB': 'shiba-inu',
                'LTC': 'litecoin',
                'BCH': 'bitcoin-cash',
                'LINK': 'chainlink',
                'XLM': 'stellar',
                'USDT': 'tether',
                'USDC': 'usd-coin',
                'BNB': 'binancecoin',
                'AVAX': 'avalanche-2',
                'MATIC': 'matic-network',
                'ATOM': 'cosmos',
            }
            
            gecko_id = symbol_map.get(symbol.upper())
            if not gecko_id:
                return None
            
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={gecko_id}&vs_currencies=cny&include_24hr_change=true&include_market_cap=true"
            resp = get_with_retry(url, timeout=AppConfig.CRYPTO_API_TIMEOUT)
            
            if not resp:
                return None
            
            data = resp.json()
            price_data = data.get(gecko_id, {})
            
            current_price = safe_float(price_data.get('cny'))
            change_percent = safe_float(price_data.get('cny_24h_change'))
            
            return {
                'code': symbol,
                'price': current_price,
                'change_percent': change_percent,
                'market_cap': safe_float(price_data.get('cny_market_cap')),
                'source': 'CoinGecko'
            }
        except Exception as e:
            logger.warning(f"Error fetching CoinGecko data for {symbol}: {e}")
            return None
    
    @staticmethod
    @timeit
    def get_crypto_data(code, use_binance=True):
        """获取数字货币数据"""
        if use_binance and 'USDT' in code.upper():
            # 币安交易对
            return CryptoAPI.get_binance_price(code)
        else:
            # CoinGecko API (支持多个平台)
            return CryptoAPI.get_coinmarketcap_price(code)


# ================= 默认数据 =================
DEFAULT_STOCKS = [
    {"code": "sh000681", "name": "科创价格"}, 
    {"code": "sh000832", "name": "中证转债"}, 
    {"code": "sh518880", "name": "国内金价"},
]

DEFAULT_CRYPTOS = [
    {"code": "BTC", "name": "比特币"},
    {"code": "ETH", "name": "以太坊"},
]


# ================= 全局变量 =================
STOCKS = []
CRYPTOS = []
stocks_lock = threading.Lock()

labels = []
update_thread = None
root = None
last_percentages = {}
display_mode = "bar"
show_price = True
show_volume = True
enable_shake = True
session_max_map = {}
current_date_str = datetime.now().strftime("%Y-%m-%d")
MA5_VOLUMES = {}

main_frame = None
stock_row_widgets = []
last_display_mode = None
last_stock_count = 0
last_show_price = None
last_show_volume = None

FONT_CONFIG = (AppConfig.FONT_NAME, AppConfig.FONT_SIZE, AppConfig.FONT_WEIGHT)


# ================= 配置管理 =================
def load_config():
    """加载配置文件"""
    global STOCKS, CRYPTOS, display_mode, session_max_map, show_price, show_volume, enable_shake, current_date_str
    
    if not os.path.exists(AppConfig.CONFIG_FILE):
        logger.info("Config file not found, using defaults")
        STOCKS = DEFAULT_STOCKS.copy()
        CRYPTOS = DEFAULT_CRYPTOS.copy()
        return
    
    try:
        with open(AppConfig.CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            STOCKS = data.get("stocks", DEFAULT_STOCKS)
            CRYPTOS = data.get("cryptos", DEFAULT_CRYPTOS)
            display_mode = data.get("display_mode", "bar")
            show_price = data.get("show_price", True)
            show_volume = data.get("show_volume", True)
            enable_shake = data.get("enable_shake", True)
            
            saved_date = data.get("date", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if saved_date == today:
                session_max_map = data.get("session_max_map", {})
                for key in list(session_max_map.keys()):
                    session_max_map[key] = safe_float(session_max_map[key], 0.0)
            else:
                session_max_map = {}
                current_date_str = today
        
        logger.info(f"Loaded {len(STOCKS)} stocks and {len(CRYPTOS)} cryptos from config")
        
    except Exception as e:
        logger.error(f"Error loading config: {e}", exc_info=True)
        STOCKS = DEFAULT_STOCKS.copy()
        CRYPTOS = DEFAULT_CRYPTOS.copy()


def save_config():
    """保存配置文件"""
    try:
        data = {
            "stocks": STOCKS,
            "cryptos": CRYPTOS,
            "display_mode": display_mode,
            "show_price": show_price,
            "show_volume": show_volume,
            "enable_shake": enable_shake,
            "session_max_map": session_max_map,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        
        config_dir = os.path.dirname(AppConfig.CONFIG_FILE) or '.'
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=config_dir,
            suffix='.tmp',
            delete=False,
            encoding='utf-8'
        ) as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            temp_file = f.name
        
        shutil.move(temp_file, AppConfig.CONFIG_FILE)
        logger.debug("Config saved successfully")
        
    except Exception as e:
        logger.error(f"Error saving config: {e}", exc_info=True)


def save_window_state():
    """保存窗口位置和大小"""
    try:
        if not root or not root.winfo_exists():
            return
        
        state = {
            "geometry": root.geometry(),
            "alpha": float(root.attributes("-alpha")),
            "topmost": bool(root.attributes("-topmost"))
        }
        
        with open(AppConfig.WINDOW_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f)
        
        logger.debug("Window state saved")
        
    except Exception as e:
        logger.debug(f"Failed to save window state: {e}")


def load_window_state():
    """恢复窗口位置和大小"""
    try:
        if not os.path.exists(AppConfig.WINDOW_STATE_FILE):
            return
        
        with open(AppConfig.WINDOW_STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        
        geometry = state.get("geometry", "")
        if geometry:
            try:
                root.geometry(geometry)
                logger.debug("Window state restored")
            except:
                pass
        
        alpha = state.get("alpha")
        if alpha is not None:
            try:
                root.attributes("-alpha", alpha)
            except:
                pass
        
    except Exception as e:
        logger.debug(f"No previous window state: {e}")


# ================= 数据获取 =================
@timeit
def get_stock_data_tencent(codes):
    """批量获取股票数据"""
    results = {}
    
    if not codes:
        return results
    
    sina_codes = []
    tencent_codes = []
    
    for s in codes:
        code = s.get("code", "")
        if code.startswith(("nf_", "Au", "Ag", "Pt", "gds_", "hf_")):
            sina_codes.append(code)
        else:
            tencent_codes.append(s)
    
    # 获取腾讯数据
    if tencent_codes:
        try:
            api_codes = []
            code_map = {}
            
            for item in tencent_codes:
                code = item.get("code", "")
                api_code = code
                
                if code.startswith("csi"):
                    api_code = "sh" + code[3:]
                elif code.startswith("sh1b"):
                    api_code = "sh00" + code[4:]
                
                api_codes.append(api_code)
                code_map[api_code] = code
            
            url = f"http://qt.gtimg.cn/q={','.join(api_codes)}"
            resp = get_with_retry(url)
            
            if resp:
                content = resp.content.decode('gbk', errors='ignore')
                lines = content.strip().split(';')
                
                for line in lines:
                    line = line.strip()
                    if '="' not in line:
                        continue
                    
                    try:
                        parts = line.split('="')
                        if len(parts) != 2:
                            continue
                        
                        key_part = parts[0]
                        data_part = parts[1].strip('"')
                        
                        if key_part.startswith('v_'):
                            api_key = key_part[2:]
                        else:
                            continue
                        
                        user_code = code_map.get(api_key, api_key)
                        data = data_part.split('~')
                        
                        if len(data) < 4:
                            continue
                        
                        current_price = safe_float(data[3])
                        last_close = safe_float(data[4])
                        volume = safe_float(data[36]) if len(data) > 36 else 0
                        
                        if last_close > 0:
                            percent = (current_price - last_close) / last_close * 100
                        else:
                            percent = 0.0
                        
                        results[user_code] = (current_price, percent, volume)
                        
                    except Exception as e:
                        logger.debug(f"Error parsing tencent data: {e}")
                        continue
        
        except Exception as e:
            logger.warning(f"Error fetching tencent data: {e}")
    
    # 获取新浪数据
    if sina_codes:
        try:
            query_list = []
            for c in sina_codes:
                if c.startswith(("nf_", "gds_")):
                    query_list.append(c)
                else:
                    if not c.startswith("g_"):
                        query_list.append(f"g_{c}")
                    else:
                        query_list.append(c)
            
            url = f"http://hq.sinajs.cn/list={','.join(query_list)}"
            headers = {'Referer': 'http://finance.sina.com.cn'}
            resp = get_with_retry(url)
            
            if resp:
                content = resp.content.decode('gbk', errors='ignore')
                lines = content.split(';')
                
                for line in lines:
                    line = line.strip()
                    if '="' not in line:
                        continue
                    
                    try:
                        parts = line.split('="')
                        if len(parts) != 2:
                            continue
                        
                        key_part = parts[0]
                        if key_part.startswith('hq_str_'):
                            api_key = key_part[7:]
                        else:
                            continue
                        
                        user_code = api_key
                        if api_key.startswith('g_'):
                            user_code = api_key[2:]
                        
                        data_str = parts[1].strip('"')
                        data_comma = data_str.split(',')
                        
                        if not data_comma:
                            continue
                        
                        current_price = safe_float(data_comma[0])
                        
                        if api_key.startswith('hf_'):
                            percent = safe_float(data_comma[1])
                        else:
                            change_amount = safe_float(data_comma[1])
                            if current_price > 0 and change_amount != 0:
                                last_close = current_price - change_amount
                                if last_close > 0:
                                    percent = (change_amount / last_close) * 100
                                else:
                                    percent = 0.0
                            else:
                                percent = 0.0
                        
                        results[user_code] = (current_price, percent)
                        if user_code != api_key:
                            results[api_key] = (current_price, percent)
                    
                    except Exception as e:
                        logger.debug(f"Error parsing sina data: {e}")
                        continue
        
        except Exception as e:
            logger.warning(f"Error fetching sina data: {e}")
    
    return results


@timeit
def get_crypto_data(cryptos):
    """批量获取数字货币数据"""
    results = {}
    
    if not cryptos:
        return results
    
    for crypto in cryptos:
        code = crypto.get("code", "")
        try:
            data = CryptoAPI.get_crypto_data(code)
            if data:
                current_price = data.get('price', 0)
                change_percent = data.get('change_percent', 0)
                results[code] = (current_price, change_percent)
                logger.debug(f"Got crypto data for {code}: {current_price} CNY ({change_percent:+.2f}%)")
        except Exception as e:
            logger.warning(f"Error fetching crypto data for {code}: {e}")
    
    return results


@timeit
def update_ui_loop():
    """后台线程：循环获取数据并更新UI"""
    global root
    
    error_count = 0
    consecutive_errors = 0
    
    logger.info("Starting update UI loop")
    
    while True:
        try:
            if not root or not root.winfo_exists():
                logger.info("Root window closed, stopping update loop")
                break
            
            # 获取股票数据
            with stocks_lock:
                stocks_copy = STOCKS.copy()
                cryptos_copy = CRYPTOS.copy()
            
            data_map = get_stock_data_tencent(stocks_copy)
            crypto_map = get_crypto_data(cryptos_copy)
            
            # 合并数据
            combined_data = {**data_map, **crypto_map}
            
            # 在主线程中更新UI
            root.after(0, lambda dm=combined_data: refresh_labels(dm))
            
            consecutive_errors = 0
            
        except Exception as e:
            consecutive_errors += 1
            error_count += 1
            logger.error(f"update_ui_loop error #{error_count}: {e}")
            
            if consecutive_errors > 10:
                logger.error("Too many consecutive errors, stopping update thread")
                break
        
        time.sleep(AppConfig.REFRESH_RATE)


@timeit
def get_trading_minutes():
    """计算当前已交易分钟数"""
    now = datetime.now()
    total_minutes = now.hour * 60 + now.minute
    
    morning_start = 9 * 60 + 30
    morning_end = 11 * 60 + 30
    afternoon_start = 13 * 60
    afternoon_end = 15 * 60
    
    if total_minutes < morning_start:
        return 0
    elif total_minutes <= morning_end:
        return total_minutes - morning_start
    elif total_minutes < afternoon_start:
        return morning_end - morning_start
    elif total_minutes <= afternoon_end:
        morning_minutes = morning_end - morning_start
        afternoon_minutes = total_minutes - afternoon_start
        return morning_minutes + afternoon_minutes
    else:
        return 240


# ================= UI 刷新 =================
def bind_events(widget):
    """绑定通用事件"""
    widget.bind("<Button-1>", start_drag)
    widget.bind("<B1-Motion>", on_drag)
    widget.bind("<Button-3>", show_context_menu)
    widget.bind("<Double-Button-1>", minimize_window)


def start_drag(event):
    root_win = event.widget.winfo_toplevel()
    root_win.x = event.x
    root_win.y = event.y


def on_drag(event):
    root_win = event.widget.winfo_toplevel()
    deltax = event.x - root_win.x
    deltay = event.y - root_win.y
    x = root_win.winfo_x() + deltax
    y = root_win.winfo_y() + deltay
    root_win.geometry(f"+{x}+{y}")


@timeit
def refresh_labels(data_map):
    """刷新UI标签"""
    global main_frame, stock_row_widgets, last_display_mode, last_stock_count
    global last_show_price, last_show_volume, root, last_percentages
    global session_max_map, current_date_str, show_price, show_volume, enable_shake
    
    if not root or not root.winfo_exists():
        return
    
    today = datetime.now().strftime("%Y-%m-%d")
    if today != current_date_str:
        current_date_str = today
        session_max_map = {}
        save_config()
    
    if main_frame is None:
        main_frame = tk.Frame(root, bg=AppConfig.WINDOW_BG_COLOR)
        main_frame.pack(fill="both", expand=True)
        bind_events(main_frame)
    
    # 合并股票和数字货币
    with stocks_lock:
        all_items = STOCKS + CRYPTOS
    
    need_rebuild = (display_mode != last_display_mode) or \
                   (len(all_items) != last_stock_count) or \
                   (show_price != last_show_price) or \
                   (show_volume != last_show_volume)
    
    if need_rebuild:
        logger.debug(f"Rebuilding UI layout")
        
        for widget in main_frame.winfo_children():
            try:
                widget.destroy()
            except:
                pass
        stock_row_widgets = []
        
        for i, stock in enumerate(all_items):
            row_widgets = {}
            col_idx = 0
            
            name_label = tk.Label(
                main_frame,
                text=stock.get('name', ''),
                bg=AppConfig.WINDOW_BG_COLOR,
                fg="white",
                font=FONT_CONFIG,
                anchor="w"
            )
            name_label.grid(row=i, column=col_idx, sticky="nswe", padx=(10, 5), pady=2)
            bind_events(name_label)
            row_widgets['name'] = name_label
            col_idx += 1
            
            if show_price:
                price_label = tk.Label(
                    main_frame,
                    text="--",
                    bg=AppConfig.WINDOW_BG_COLOR,
                    fg="white",
                    font=FONT_CONFIG,
                    anchor="e"
                )
                price_label.grid(row=i, column=col_idx, sticky="nswe", padx=(5, 5), pady=2)
                bind_events(price_label)
                row_widgets['price'] = price_label
                col_idx += 1
            
            if display_mode == "bar":
                bar_canvas = tk.Canvas(
                    main_frame,
                    bg=AppConfig.WINDOW_BG_COLOR,
                    height=AppConfig.BAR_CANVAS_HEIGHT,
                    width=AppConfig.BAR_CANVAS_WIDTH,
                    highlightthickness=0
                )
                bar_canvas.grid(row=i, column=col_idx, sticky="nswe", padx=5, pady=2)
                bind_events(bar_canvas)
                row_widgets['bar'] = bar_canvas
                col_idx += 1
                
                pct_label = tk.Label(
                    main_frame,
                    text="--%",
                    bg=AppConfig.WINDOW_BG_COLOR,
                    fg="white",
                    font=FONT_CONFIG,
                    anchor="e"
                )
                pct_label.grid(row=i, column=col_idx, sticky="nswe", padx=(5, 10), pady=2)
                bind_events(pct_label)
                row_widgets['pct'] = pct_label
                col_idx += 1
            else:
                pct_label = tk.Label(
                    main_frame,
                    text="--%",
                    bg=AppConfig.WINDOW_BG_COLOR,
                    fg="white",
                    font=FONT_CONFIG,
                    anchor="e"
                )
                pct_label.grid(row=i, column=col_idx, sticky="nswe", padx=(20, 10), pady=2)
                bind_events(pct_label)
                row_widgets['pct'] = pct_label
                col_idx += 1
            
            stock_row_widgets.append(row_widgets)
        
        last_display_mode = display_mode
        last_stock_count = len(all_items)
        last_show_price = show_price
        last_show_volume = show_volume
    
    # 更新历史最大值
    for code in data_map:
        val = data_map[code]
        if isinstance(val, tuple) and len(val) > 1:
            percent = safe_float(val[1])
            cur_abs = abs(percent)
            if cur_abs > session_max_map.get(code, 0.0):
                session_max_map[code] = cur_abs
    
    # 计算视口上限
    current_max_all = 0.0
    with stocks_lock:
        all_items = STOCKS + CRYPTOS
    
    for stock in all_items:
        code = stock.get('code', '')
        m = session_max_map.get(code, 0.0)
        if m > current_max_all:
            current_max_all = m
    
    view_ceiling = max(AppConfig.MIN_VIEW_CEILING, current_max_all)
    
    should_shake = False
    
    with stocks_lock:
        all_items = STOCKS + CRYPTOS
    
    for i, stock in enumerate(all_items):
        if i >= len(stock_row_widgets):
            break
        
        widgets = stock_row_widgets[i]
        code = stock.get('code', '')
        display_name = stock.get('name', '')
        
        if len(display_name) > AppConfig.MAX_DISPLAY_NAME_LEN:
            display_name = display_name[:AppConfig.MAX_DISPLAY_NAME_LEN]
        
        color = AppConfig.COLOR_NEUTRAL
        percent = 0.0
        current_price = 0.0
        vol_text = ""
        
        if code in data_map:
            val = data_map[code]
            volume = 0
            
            if isinstance(val, tuple):
                if len(val) == 3:
                    current_price, percent, volume = val
                else:
                    current_price, percent = val
            
            percent = safe_float(percent)
            current_price = safe_float(current_price)
            volume = safe_float(volume)
            
            if percent > 0:
                color = AppConfig.COLOR_UP
            elif percent < 0:
                color = AppConfig.COLOR_DOWN
            else:
                color = AppConfig.COLOR_NEUTRAL
            
            if code in last_percentages:
                prev_percent = last_percentages.get(code, 0.0)
                if (prev_percent >= 0 and percent < 0) or (prev_percent <= 0 and percent > 0):
                    should_shake = True
                if int(abs(percent)) > int(abs(prev_percent)):
                    should_shake = True
            
            last_percentages[code] = percent
        
        try:
            widgets['name'].config(text=display_name, fg=color)
            
            if 'price' in widgets:
                price_text = f"{current_price:.3f}" if code in data_map else "--"
                widgets['price'].config(text=price_text, fg=color)
            
            pct_text = f"{percent:+.2f}%" if code in data_map else "--"
            widgets['pct'].config(text=pct_text, fg=color)
            
            if 'bar' in widgets:
                canvas = widgets['bar']
                canvas.delete("all")
                
                if code in data_map:
                    w = canvas.winfo_width()
                    if w < 10:
                        w = AppConfig.BAR_CANVAS_WIDTH
                    h = canvas.winfo_height()
                    if h < 10:
                        h = AppConfig.BAR_CANVAS_HEIGHT
                    
                    center_x = w / 2
                    center_y = h / 2
                    
                    bracket_h = 14
                    bracket_w = 3
                    margin_x = 4
                    y_top = center_y - (bracket_h / 2)
                    y_bottom = center_y + (bracket_h / 2)
                    
                    lx = margin_x
                    canvas.create_line(lx, y_top, lx, y_bottom, fill=AppConfig.COLOR_BRACKET, width=2)
                    canvas.create_line(lx, y_top, lx+bracket_w, y_top, fill=AppConfig.COLOR_BRACKET, width=2)
                    canvas.create_line(lx, y_bottom, lx+bracket_w, y_bottom, fill=AppConfig.COLOR_BRACKET, width=2)
                    
                    rx = w - margin_x
                    canvas.create_line(rx, y_top, rx, y_bottom, fill=AppConfig.COLOR_BRACKET, width=2)
                    canvas.create_line(rx, y_top, rx-bracket_w, y_top, fill=AppConfig.COLOR_BRACKET, width=2)
                    canvas.create_line(rx, y_bottom, rx-bracket_w, y_bottom, fill=AppConfig.COLOR_BRACKET, width=2)
                    
                    draw_w = w - 24
                    if draw_w < 10:
                        draw_w = 10
                    
                    this_stock_max = session_max_map.get(code, 0.0)
                    track_len = (this_stock_max / view_ceiling) * draw_w
                    if track_len > draw_w:
                        track_len = draw_w
                    if track_len < 4:
                        track_len = 4
                    
                    bar_len = (abs(percent) / view_ceiling) * draw_w
                    if bar_len > draw_w:
                        bar_len = draw_w
                    if bar_len < 2:
                        bar_len = 2
                    
                    bar_color = AppConfig.COLOR_UP if percent > 0 else AppConfig.COLOR_DOWN
                    if percent == 0:
                        bar_color = "#999999"
                    
                    track_x1 = center_x - (track_len / 2)
                    track_x2 = center_x + (track_len / 2)
                    
                    canvas.create_line(
                        track_x1, center_y, track_x2, center_y,
                        width=AppConfig.BAR_LINE_WIDTH,
                        fill=AppConfig.COLOR_TRACK,
                        capstyle=tk.ROUND
                    )
                    
                    bar_x1 = center_x - (bar_len / 2)
                    bar_x2 = center_x + (bar_len / 2)
                    
                    if bar_len < AppConfig.BAR_LINE_WIDTH:
                        bar_x1 = center_x
                        bar_x2 = center_x
                    
                    canvas.create_line(
                        bar_x1, center_y, bar_x2, center_y,
                        width=AppConfig.BAR_LINE_WIDTH,
                        fill=bar_color,
                        capstyle=tk.ROUND
                    )
        
        except Exception as e:
            logger.warning(f"Error updating widget for {code}: {e}")
    
    try:
        main_frame.update_idletasks()
        req_width = main_frame.winfo_reqwidth()
        req_height = main_frame.winfo_reqheight()
        
        current_width = root.winfo_width()
        current_height = root.winfo_height()
        
        if abs(req_width - current_width) > 5 or abs(req_height - current_height) > 5:
            root.geometry(f"{req_width}x{req_height}+{root.winfo_x()}+{root.winfo_y()}")
    
    except Exception as e:
        logger.debug(f"Error adjusting window size: {e}")
    
    if should_shake and enable_shake:
        root.after(50, shake_window)


def shake_window():
    """窗口抖动"""
    if not root or not root.winfo_exists():
        return
    
    try:
        original_x = root.winfo_x()
        original_y = root.winfo_y()
        
        for _ in range(AppConfig.SHAKE_STEPS):
            dx = random.randint(-AppConfig.SHAKE_INTENSITY, AppConfig.SHAKE_INTENSITY)
            dy = random.randint(-AppConfig.SHAKE_INTENSITY, AppConfig.SHAKE_INTENSITY)
            root.geometry(f"+{original_x+dx}+{original_y+dy}")
            root.update()
            time.sleep(AppConfig.SHAKE_INTERVAL)
        
        root.geometry(f"+{original_x}+{original_y}")
    
    except Exception as e:
        logger.debug(f"Error during shake: {e}")


# ================= 菜单和设置 =================
def show_context_menu(event):
    """右键菜单"""
    menu = tk.Menu(root, tearoff=0)
    
    mode_label = "切换为百分比模式" if display_mode == "bar" else "切换为柱状图"
    menu.add_command(label=mode_label, command=lambda: toggle_display_mode("percent" if display_mode == "bar" else "bar"))
    
    price_label = "隐藏价格" if show_price else "显示价格"
    menu.add_command(label=price_label, command=toggle_show_price)
    
    shake_label = "关闭抖动" if enable_shake else "开启抖动"
    menu.add_command(label=shake_label, command=toggle_shake)
    
    menu.add_separator()
    menu.add_command(label="配置股票", command=open_settings)
    menu.add_separator()
    menu.add_command(label="退出", command=quit_app)
    
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()


def toggle_display_mode(mode):
    """切换显示模式"""
    global display_mode
    display_mode = mode
    save_config()
    if root:
        root.after(0, lambda: refresh_labels({}))


def toggle_show_price():
    """切换价格显示"""
    global show_price
    show_price = not show_price
    save_config()
    if root:
        root.after(0, lambda: refresh_labels({}))


def toggle_shake():
    """切换抖动"""
    global enable_shake
    enable_shake = not enable_shake
    save_config()


def open_settings():
    """打开设置窗口"""
    settings_win = tk.Toplevel(root)
    settings_win.title("配置")
    
    try:
        root_x = root.winfo_x()
        root_y = root.winfo_y()
        root_w = root.winfo_width()
        
        pos_x = root_x + root_w + 10
        pos_y = root_y
        
        screen_w = root.winfo_screenwidth()
        if pos_x + 700 > screen_w:
            pos_x = root_x - 700 - 10
            if pos_x < 0:
                pos_x = 10
        
        settings_win.geometry(f"700x900+{pos_x}+{pos_y}")
    except:
        settings_win.geometry("700x900")
    
    # ===股票配置===
    stock_frame = tk.LabelFrame(settings_win, text="股票配置", padx=5, pady=5)
    stock_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    stock_listbox = tk.Listbox(stock_frame, height=8)
    stock_listbox.pack(side="left", fill="both", expand=True)
    
    scrollbar = tk.Scrollbar(stock_frame)
    scrollbar.pack(side="right", fill="y")
    stock_listbox.config(yscrollcommand=scrollbar.set)
    scrollbar.config(command=stock_listbox.yview)
    
    def refresh_stock_list():
        stock_listbox.delete(0, tk.END)
        with stocks_lock:
            for stock in STOCKS:
                stock_listbox.insert(tk.END, f"{stock.get('code')} - {stock.get('name')}")
    
    refresh_stock_list()
    
    def delete_stock():
        selection = stock_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请选择要删除的股票")
            return
        
        idx = selection[0]
        with stocks_lock:
            if idx < len(STOCKS):
                del STOCKS[idx]
        
        save_config()
        refresh_stock_list()
        if root:
            root.after(0, lambda: refresh_labels({}))
    
    tk.Button(stock_frame, text="删除选中", command=delete_stock, fg="red").pack(pady=5)
    
    # === 数字货币配置 ===
    crypto_frame = tk.LabelFrame(settings_win, text="数字货币配置", padx=5, pady=5)
    crypto_frame.pack(fill="both", expand=True, padx=5, pady=5)
    
    # 数字货币列表
    crypto_listbox = tk.Listbox(crypto_frame, height=8)
    crypto_listbox.pack(side="left", fill="both", expand=True)
    
    scrollbar2 = tk.Scrollbar(crypto_frame)
    scrollbar2.pack(side="right", fill="y")
    crypto_listbox.config(yscrollcommand=scrollbar2.set)
    scrollbar2.config(command=crypto_listbox.yview)
    
    def refresh_crypto_list():
        crypto_listbox.delete(0, tk.END)
        with stocks_lock:
            for crypto in CRYPTOS:
                crypto_listbox.insert(tk.END, f"{crypto.get('code')} - {crypto.get('name')}")
    
    refresh_crypto_list()
    
    # 添加数字货币输入框
    input_frame = tk.Frame(crypto_frame)
    input_frame.pack(fill="x", pady=5)
    
    tk.Label(input_frame, text="代码:").pack(side="left", padx=5)
    crypto_code_entry = tk.Entry(input_frame, width=10)
    crypto_code_entry.pack(side="left", padx=5)
    
    tk.Label(input_frame, text="名称:").pack(side="left", padx=5)
    crypto_name_entry = tk.Entry(input_frame, width=15)
    crypto_name_entry.pack(side="left", padx=5)
    
    def add_crypto():
        code = crypto_code_entry.get().strip().upper()
        name = crypto_name_entry.get().strip()
        
        if not code or not name:
            messagebox.showwarning("提示", "代码和名称不能为空")
            return
        
        with stocks_lock:
            # 检查重复
            for c in CRYPTOS:
                if c.get('code') == code:
                    messagebox.showwarning("提示", f"{code} 已存在")
                    return
            
            CRYPTOS.append({"code": code, "name": name})
        
        save_config()
        refresh_crypto_list()
        crypto_code_entry.delete(0, tk.END)
        crypto_name_entry.delete(0, tk.END)
        if root:
            root.after(0, lambda: refresh_labels({}))
    
    def delete_crypto():
        selection = crypto_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请选择要删除的数字货币")
            return
        
        idx = selection[0]
        with stocks_lock:
            if idx < len(CRYPTOS):
                del CRYPTOS[idx]
        
        save_config()
        refresh_crypto_list()
        if root:
            root.after(0, lambda: refresh_labels({}))
    
    btn_frame = tk.Frame(crypto_frame)
    btn_frame.pack(fill="x", pady=5)
    
    tk.Button(btn_frame, text="添加", command=add_crypto, bg="#dddddd").pack(side="left", padx=5)
    tk.Button(btn_frame, text="删除选中", command=delete_crypto, fg="red").pack(side="left", padx=5)


def minimize_window(event=None):
    """最小化窗口"""
    try:
        root.overrideredirect(False)
        root.iconify()
    except Exception as e:
        logger.warning(f"Error minimizing window: {e}")


def on_map(event):
    """窗口恢复事件"""
    try:
        if root.state() == 'normal' and not root.overrideredirect():
            root.after(100, lambda: root.overrideredirect(True))
    except Exception as e:
        logger.debug(f"Error in on_map: {e}")


def quit_app():
    """退出程序"""
    global root
    
    logger.info("Quitting application")
    
    save_window_state()
    save_config()
    
    if root:
        try:
            root.withdraw()
            root.quit()
            root.destroy()
        except Exception as e:
            logger.warning(f"Error quitting: {e}")


# ================= 主程序 =================
def main():
    """主程序入口"""
    global root, update_thread
    
    logger.info(f"Starting Stock Monitor v{AppConfig.VERSION}")
    
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except:
            pass
    
    load_config()
    
    root = tk.Tk()
    root.title("")
    
    root.overrideredirect(True)
    root.wm_attributes("-topmost", True)
    root.wm_attributes("-alpha", AppConfig.WINDOW_ALPHA)
    root.configure(bg=AppConfig.WINDOW_BG_COLOR)
    
    with stocks_lock:
        all_items = STOCKS + CRYPTOS
    
    height = len(all_items) * AppConfig.WINDOW_HEIGHT_PER_STOCK + 40
    root.geometry(f"{AppConfig.WINDOW_WIDTH}x{height}+{AppConfig.INITIAL_WINDOW_X}+{AppConfig.INITIAL_WINDOW_Y}")
    
    load_window_state()
    
    root.bind("<Double-Button-1>", minimize_window)
    root.bind("<Map>", on_map)
    root.bind("<Button-1>", start_drag)
    root.bind("<B1-Motion>", on_drag)
    root.bind("<Button-3>", show_context_menu)
    
    refresh_labels({})
    
    update_thread = threading.Thread(target=update_ui_loop, daemon=True)
    update_thread.start()
    
    logger.info("Application started successfully")
    
    root.mainloop()


if __name__ == "__main__":
    main()
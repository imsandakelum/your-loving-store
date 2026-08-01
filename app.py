from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify
import sqlite3
from datetime import date, datetime, timedelta
import pandas as pd
import io
import time
import requests # Meta එකට රික්වෙස්ට් යවන්න
import hashlib  # දත්ත ආරක්ෂිතව යවන්න (Hashing)

import os
import shutil

# 🎯 පරණ Database එක අලුත් Disk එකට බලෙන් කොපි කිරීම (Force Copy)
try:
    # Render එකේ දැනට තියෙන DB එක හිස් එකක්ද කියලා බලනවා (Size එක 50KB ට අඩු නම් ඒක හිස්)
    if not os.path.exists('/var/data/database.db') or os.path.getsize('/var/data/database.db') < 50000:
        # පරණ ඩේටා තියෙන එක GitHub එකේ තියෙනවා නම්, ඒක අලුත් ඩිස්ක් එකට කොපි කරනවා
        if os.path.exists('database.db'):
            shutil.copy2('database.db', '/var/data/database.db')
            print("✅ පරණ Database එක සාර්ථකව අලුත් Disk එකට කොපි කළා!")
except Exception as e:
    print("DB Copy Error:", e)


# === META CAPI CREDENTIALS ===
META_ACCESS_TOKEN = "EAATaDxcz4B8BRz5DjkHtkeFdz4wznmP6ZAjvXZCSX9QYkHz17BLylPdOZBKbgb64b6cDDBoQY9jyFjjiaxYS3axqnOS8d3mytEZAD8jyq1uoHJNGpJxm7vwrHIquWtxZCU4aNRQiaLGQG5HwE0Ssod6Ba8rJijWNBRmzfZCuEpZBZCqceWK8xlGT0sSeZBRUaWwZDZD" # අදියර 1 න් ගත්තු Token එක
META_DATASET_ID = "1042370911648399"         # අදියර 1 න් ගත්තු ID එක
META_API_VERSION = "v19.0"


# ලංකාවේ වෙලාව සහ දිනය ලබාගැනීම සඳහා විශේෂ Function එකක්
def get_sl_today():
    # UTC වෙලාවට පැය 5යි විනාඩි 30ක් එකතු කිරීම
    sl_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return sl_time

import requests # මේක දැනටමත් උඩ තියෙනවා නම් ආයේ දාන්න ඕනේ නෑ

# 🚀 Telegram Notification සැකසුම්
TELEGRAM_BOT_TOKEN = "8614100981:AAFIcWMBvYLTqLmvoPVUM_49e5rifSJyagY" 
TELEGRAM_CHAT_ID = "980911943"

def send_telegram_alert(username, ip_address, device_info):
    try:
        sl_time = get_sl_today().strftime('%Y-%m-%d %I:%M %p')
        # 🚀 අලුත් විස්තරත් එක්ක මැසේජ් එක ලස්සනට හදලා තියෙන්නේ
        msg = f"🚨 *System Login Alert*\n\n👤 User: `{username}`\n🕒 Time: {sl_time}\n🌐 IP Address: `{ip_address}`\n💻 Device: `{device_info}`\n\n🛡️ Someone has logged into the YLS CRM."
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=5) 
    except Exception as e:
        pass

app = Flask(__name__)

app.secret_key = "your_loving_store_secret"

# --- Auto-Logout / Session Timeout සැකසුම ---
# මෙහි minutes=10 යනු විනාඩි 10කි. ඔබට අවශ්‍ය නම් එය 5, 15 ආදී වශයෙන් වෙනස් කළ හැක.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)

@app.before_request
def make_session_permanent():
    # පරිශීලකයා පද්ධතිය තුළ යම් ක්‍රියාකාරකමක් කරන සෑම විටම කාලය අලුත් වේ (Reset).
    session.permanent = True
    session.modified = True
# ---------------------------------------------

# --- Formatting Filters ---
@app.template_filter('format_currency')
def format_currency(value):
    try: return f"Rs.{float(value):,.2f}"
    except: return value

@app.template_filter('format_number')
def format_number(value):
    try: return f"{int(float(value)):,}"
    except: return value

def init_sqlite_db():
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, password TEXT NOT NULL)''')
    
    # අලුතින් Role කොලම් එක එකතු කිරීම
    try: cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'admin'")
    except: pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY AUTOINCREMENT, item_name TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS stock_batches (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, cost_price REAL NOT NULL, qty INTEGER NOT NULL, remaining_qty INTEGER, stock_date DATE NOT NULL, FOREIGN KEY(item_id) REFERENCES items(id))''')
    
    try: cursor.execute("ALTER TABLE stock_batches ADD COLUMN remaining_qty INTEGER")
    except: pass
    try: cursor.execute("UPDATE stock_batches SET remaining_qty = qty WHERE remaining_qty IS NULL")
    except: pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, barcode TEXT UNIQUE, customer_name TEXT, customer_phone TEXT, item_id INTEGER, qty INTEGER NOT NULL, selling_price REAL NOT NULL, total REAL NOT NULL, cost_at_sale REAL NOT NULL, sale_date DATE NOT NULL, status TEXT DEFAULT 'Credit', FOREIGN KEY(item_id) REFERENCES items(id))''')
    try: cursor.execute("ALTER TABLE sales ADD COLUMN payment_date DATE")
    except: pass
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL, amount REAL NOT NULL, expense_date DATE NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS returns (id INTEGER PRIMARY KEY AUTOINCREMENT, item_id INTEGER, qty INTEGER NOT NULL, return_amount REAL NOT NULL, cost_at_return REAL NOT NULL, return_date DATE NOT NULL, barcode TEXT, FOREIGN KEY(item_id) REFERENCES items(id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS other_expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL, amount REAL NOT NULL, expense_date DATE NOT NULL)''')
    try: cursor.execute("ALTER TABLE other_expenses ADD COLUMN item_name TEXT")
    except: pass
    cursor.execute('''CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, color TEXT DEFAULT '#f1c40f', note_date DATE NOT NULL)''')
    
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password) VALUES (1, 'admin', '123')")
    
    # 📝 අලුත් Username සහ Password මෙතනට දාන්න:
    # Admin ගේ පාස්වර්ඩ් එක වෙනස් කිරීමට:
    cursor.execute("UPDATE users SET password='yls@123' WHERE username='admin'")
    
    # Staff ගේ Username සහ Password වෙනස් කිරීමට:
    cursor.execute("UPDATE users SET username='user2', password='123' WHERE id=2")
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS activity_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, action TEXT, details TEXT, timestamp DATETIME)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS deleted_sales (id INTEGER PRIMARY KEY AUTOINCREMENT, barcode TEXT, customer_name TEXT, item_id INTEGER, qty INTEGER, selling_price REAL, total REAL, cost_at_sale REAL, sale_date DATE, deleted_date DATE, FOREIGN KEY(item_id) REFERENCES items(id))''')
    try: cursor.execute("ALTER TABLE stock_batches ADD COLUMN source TEXT DEFAULT 'Manual'")
    except: pass

    # --- අලුතින් එකතු කළ Leads වගුව (New Features සමඟ) ---
    cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        upload_date DATE NOT NULL,
        created_time TEXT,
        product_name TEXT NOT NULL,
        customer_name TEXT,
        phone TEXT,
        phone2 TEXT,
        address TEXT,
        size TEXT,
        status TEXT DEFAULT 'Pending',
        remarks TEXT
    )''')
    
    # කලින් මේ Table එක හැදිලා තිබුණා නම්, අලුත් කොලම් ටික ඊට එකතු කිරීම
    try: cursor.execute("ALTER TABLE leads ADD COLUMN created_time TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE leads ADD COLUMN phone2 TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE leads ADD COLUMN size TEXT")
    except: pass
    
    # 🎯 අලුත්: Domex Tracking විස්තර සේව් කරගන්න
    try: cursor.execute("ALTER TABLE leads ADD COLUMN tracking_no TEXT")
    except: pass
    try: cursor.execute("ALTER TABLE leads ADD COLUMN courier TEXT")
    except: pass

    # --- අලුත්: පෞද්ගලික වියදම් සඳහා වෙනමම Table එකක් ---
    cursor.execute('''CREATE TABLE IF NOT EXISTS personal_expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        expense_date DATE NOT NULL, 
        category TEXT NOT NULL, 
        description TEXT, 
        amount REAL NOT NULL
    )''')
    
    # --- අලුත්: ඔයාට පමණක් ඇතුළු විය හැකි විශේෂිත User Account එක ---
    # Username: madusanka_personal | Password: myexpenses123
    cursor.execute("INSERT OR IGNORE INTO users (id, username, password, role) VALUES (3, 'indika', 'indi98', 'personal_only')")
    
    conn.commit()
    conn.close()

init_sqlite_db()

def send_meta_capi_event(event_name, customer_data, custom_data=None):
    if not META_ACCESS_TOKEN or META_ACCESS_TOKEN.startswith("ඔයාගේ"):
        return None

    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_DATASET_ID}/events"
    
    def hash_data(data):
        if not data: return None
        # String එකක් බවට හරවා (str), error ඒම වැළැක්වීම
        return hashlib.sha256(str(data).strip().lower().encode('utf-8')).hexdigest()

    event_data = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "action_source": "physical_store",
        "user_data": {
            "client_ip_address": customer_data.get('client_ip', '0.0.0.0'),
            "client_user_agent": customer_data.get('client_user_agent', 'Mozilla/5.0')
        }
    }

    raw_phone = customer_data.get('phone')
    if raw_phone:
        phone_str = str(raw_phone).strip()
        if phone_str.startswith('0'):
            phone_str = '+94' + phone_str[1:]
        event_data["user_data"]["ph"] = [hash_data(phone_str)]

    if custom_data:
        event_data["custom_data"] = {
            "value": float(custom_data.get('value', 0)),
            "currency": "LKR",
            "order_id": str(custom_data.get('order_id'))
        }

    payload = {
        "data": [event_data],
        "access_token": META_ACCESS_TOKEN,
        # වැදගත්: ඔයාගේ Meta Test Events පිටුවේ දැන් තියෙන අලුත්ම TEST කෝඩ් එක මෙතනට දාන්න
        "test_event_code": "TEST806" 
    }
    
    try:
        response = requests.post(url, json=payload)
        
        # --- META API එකෙන් එන උත්තරය File එකක සේව් කිරීම ---
        with open("/var/data/meta_debug_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Event: {event_name} | Barcode: {custom_data.get('order_id')} | Status: {response.status_code} | Response: {response.text}\n")
        # ---------------------------------------------------
        
        return response.json()
    except Exception as e:
        with open("/var/data/meta_debug_log.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Event: {event_name} | Exception: {str(e)}\n")
        return None

# --- ACTIVITY LOGGER HELPER FUNCTION ---
def log_activity(username, action, details):
    try:
        conn = sqlite3.connect('/var/data/database.db')
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO activity_logs (username, action, details, timestamp) VALUES (?, ?, ?, ?)", (username, action, details, now))
        conn.commit()
        conn.close()
    except:
        pass

def deduct_fifo(cursor, item_id, sell_qty):
    # qty වෙනුවට remaining_qty භාවිතා කිරීම
    cursor.execute("SELECT id, remaining_qty, cost_price FROM stock_batches WHERE item_id=? AND remaining_qty > 0 ORDER BY stock_date ASC, id ASC", (item_id,))
    batches = cursor.fetchall()
    remaining = sell_qty
    total_cost = 0.0
    for batch in batches:
        b_id, b_rem_qty, b_cost = batch
        if remaining <= 0: break
        take = min(b_rem_qty, remaining)
        cursor.execute("UPDATE stock_batches SET remaining_qty = remaining_qty - ? WHERE id=?", (take, b_id))
        total_cost += take * b_cost
        remaining -= take
    if remaining > 0:
        cursor.execute("SELECT cost_price FROM stock_batches WHERE item_id=? ORDER BY id DESC LIMIT 1", (item_id,))
        last_cost_row = cursor.fetchone()
        last_cost = last_cost_row[0] if last_cost_row else 0.0
        total_cost += remaining * last_cost
        cursor.execute("SELECT id FROM stock_batches WHERE item_id=? ORDER BY id DESC LIMIT 1", (item_id,))
        latest_b = cursor.fetchone()
        if latest_b:
            cursor.execute("UPDATE stock_batches SET remaining_qty = remaining_qty - ? WHERE id=?", (remaining, latest_b[0]))
    return total_cost

@app.route('/')
def home():
    if 'username' in session: 
        # අලුත් යූසර් නම් Personal පේජ් එකට යවනවා
        if session.get('role') == 'personal_only':
            return redirect(url_for('personal_expenses'))
        # නැත්නම් සාමාන්‍ය Dashboard එකට යවනවා
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = sqlite3.connect('/var/data/database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (request.form['username'], request.form['password']))
        user = cursor.fetchone()
        
        if user:
            session['username'] = request.form['username']
            cursor.execute("SELECT role FROM users WHERE username=?", (request.form['username'],))
            role_row = cursor.fetchone()
            session['role'] = role_row[0] if role_row else 'user'
            
            log_activity(session['username'], "Login", "User successfully logged in.")
            
            # 🚀 1. IP Address එක හොයාගැනීම 
            ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip_addr and ',' in ip_addr:
                ip_addr = ip_addr.split(',')[0].strip()
            
            # 🚀 2. Device එක සහ Browser එක නිවැරදිව අඳුරගැනීම (Manual String Parsing)
            ua_string = request.headers.get('User-Agent', '')
            
            # OS එක අඳුරගැනීම
            os_info = "Unknown OS"
            if 'Windows' in ua_string: os_info = "Windows"
            elif 'iPhone' in ua_string or 'iPad' in ua_string: os_info = "iOS (iPhone/iPad)"
            elif 'Mac OS' in ua_string or 'Macintosh' in ua_string: os_info = "Mac OS"
            elif 'Android' in ua_string: os_info = "Android"
            elif 'Linux' in ua_string: os_info = "Linux"
            
            # Browser එක අඳුරගැනීම
            browser_info = "Unknown Browser"
            if 'Edg' in ua_string: browser_info = "Edge"
            elif 'Chrome' in ua_string and 'Safari' in ua_string: browser_info = "Chrome"
            elif 'Safari' in ua_string and 'Chrome' not in ua_string: browser_info = "Safari"
            elif 'Firefox' in ua_string: browser_info = "Firefox"
            elif 'Opera' in ua_string or 'OPR' in ua_string: browser_info = "Opera"
            
            device_info = f"{os_info} - {browser_info}"
            
            # 🚀 Telegram Alert එක යැවීම
            try:
                send_telegram_alert(session['username'], ip_addr, device_info)
            except Exception as e:
                print("Telegram Alert Error:", e) 
                
            conn.close()
            # ... (උඩ තියෙන Telegram Alert කේතය එලෙසම තබන්න) ...
            
            conn.close()
            
            # 🎯 අලුත්: Role එක අනුව අදාල පේජ් එකට යැවීම
            if session['role'] == 'personal_only':
                return redirect(url_for('personal_expenses'))
            else:
                return redirect(url_for('dashboard'))
            
        conn.close()
        return render_template('login.html', error="Username හෝ Password වැරදියි!")
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    month_str = f"{get_sl_today().strftime('%Y-%m')}%"
    
    # 1. Total Sale & Total Orders (All Time) - 🚀 'Returned' ඇතුළත් කර සම්පූර්ණ ගණන ගැනීම
    cursor.execute("SELECT SUM(total), COUNT(id) FROM sales WHERE status IN ('Credit', 'Paid', 'Returned')")
    total_sales_data = cursor.fetchone()
    total_sale_all = total_sales_data[0] or 0.0
    total_orders_all = total_sales_data[1] or 0

    # 2. Total Return & Total Return Orders (All Time)
    cursor.execute("SELECT SUM(return_amount), COUNT(id) FROM returns")
    total_returns_data = cursor.fetchone()
    total_return_all = total_returns_data[0] or 0.0
    total_returns_count = total_returns_data[1] or 0

    # 3. This Month's Sale & Orders - 🚀 'Returned' ඇතුළත් කර සම්පූර්ණ ගණන ගැනීම
    cursor.execute("SELECT SUM(total), COUNT(id) FROM sales WHERE sale_date LIKE ? AND status IN ('Credit', 'Paid', 'Returned')", (month_str,))
    month_sales_data = cursor.fetchone()
    month_sale_total = month_sales_data[0] or 0.0
    month_orders_count = month_sales_data[1] or 0

    # --- Chart Data (Income vs Expenses for Current Month) ---
    # Income (Sales) - 🚀 Chart එකටත් සම්පූර්ණ ගණන දානවා
    cursor.execute("SELECT sale_date, SUM(total) FROM sales WHERE sale_date LIKE ? AND status IN ('Credit', 'Paid', 'Returned') GROUP BY sale_date", (month_str,))
    sales_dict = dict(cursor.fetchall())
    
    # Expenses (Ads)
    cursor.execute("SELECT expense_date, SUM(amount) FROM expenses WHERE expense_date LIKE ? GROUP BY expense_date", (month_str,))
    ads_dict = dict(cursor.fetchall())
    
    # Expenses (Other)
    cursor.execute("SELECT expense_date, SUM(amount) FROM other_expenses WHERE expense_date LIKE ? GROUP BY expense_date", (month_str,))
    other_dict = dict(cursor.fetchall())

    all_dates = sorted(list(set(sales_dict.keys()) | set(ads_dict.keys()) | set(other_dict.keys())))
    
    chart_dates = []
    chart_income = []
    chart_expenses = []
    
    for d in all_dates:
        chart_dates.append(d)
        chart_income.append(sales_dict.get(d, 0.0))
        total_exp = ads_dict.get(d, 0.0) + other_dict.get(d, 0.0)
        chart_expenses.append(total_exp)
        
    conn.close()
    
    return render_template('dashboard.html', 
                           total_sale_all=total_sale_all, total_orders_all=total_orders_all,
                           total_return_all=total_return_all, total_returns_count=total_returns_count,
                           month_sale_total=month_sale_total, month_orders_count=month_orders_count,
                           chart_dates=chart_dates, chart_income=chart_income, chart_expenses=chart_expenses)

@app.route('/items', methods=['GET', 'POST'])
def items():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    today_str = date.today().strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add_new_item':
            item_name = request.form['item_name']
            cursor.execute("INSERT INTO items (item_name) VALUES (?)", (item_name,))
            conn.commit()
            log_activity(session['username'], "Add Item", f"Added: {item_name}")
            
        elif action == 'add_stock':
            # 1. මුලින්ම qty එක සහ අනිත් දේවල් අරගන්න (මෙතන තමයි qty define වෙන්න ඕන)
            qty = int(request.form['add_qty'])
            item_id = request.form['item_id']
            cost_price = request.form['cost_price']
            stock_date = request.form['stock_date']
            
            # 2. ඊට පස්සේ SQL එක දුවන්න
            cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date) VALUES (?, ?, ?, ?, ?)", 
                           (item_id, cost_price, qty, qty, stock_date))
            conn.commit()
            
            # 3. ලොග් එක තියන්න
            log_activity(session['username'], "Add Stock", f"Item ID: {item_id}, Qty: {qty}")
            
        return redirect(url_for('items'))

    # 🎯 නිවැරදි Available Stock ගණනය කිරීම (Ledger එකට සමාන කිරීම)
    cursor.execute("""
        SELECT i.id, i.item_name, 
               (
                   COALESCE((SELECT SUM(qty) FROM stock_batches WHERE item_id = i.id AND (source = 'Manual' OR source IS NULL)), 0) +
                   COALESCE((SELECT SUM(qty) FROM returns WHERE item_id = i.id), 0)
               ) as total_in,
               COALESCE((SELECT SUM(qty) FROM sales WHERE item_id = i.id), 0) as total_out
        FROM items i ORDER BY i.item_name ASC
    """)
    
    items_list = []
    for row in cursor.fetchall():
        item_id = row[0]
        item_name = row[1]
        total_in = row[2]
        total_out = row[3]
        
        # දැනට තියෙන ස්ටොක් එක = (Manual බැච් + Returns) - විකිණුනු ගාණ
        available_stock = total_in - total_out
        items_list.append((item_id, item_name, available_stock))

    cursor.execute('''SELECT b.id, i.item_name, b.stock_date, b.cost_price, b.qty FROM stock_batches b JOIN items i ON b.item_id = i.id WHERE b.source = 'Manual' OR b.source IS NULL ORDER BY b.stock_date DESC, b.id DESC''')
    batches = cursor.fetchall()
    grand_total = sum((b[3] * b[4]) for b in batches if b[4] > 0)
    conn.close()
    return render_template('items.html', items_list=items_list, batches=batches, grand_total=grand_total, today_date=today_str)

@app.route('/delete_batch/<int:batch_id>')
def delete_batch(batch_id):
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stock_batches WHERE id=?", (batch_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('items'))

@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    if request.method == 'POST':
        barcode = request.form['barcode'].strip() or f"M-{int(time.time())}"
        customer = request.form.get('customer', '')
        phone = request.form.get('phone', '')
        status = request.form.get('status', 'Paid')
        item_id = request.form['item_id']
        qty = int(request.form['qty'])
        selling_price = float(request.form['selling_price'])
        sale_date = request.form['sale_date']
        total_value = qty * selling_price
        
        # FIFO ක්‍රමයට cost එක ගණනය කිරීම සහ ස්ටොක් අඩු කිරීම
        cost_at_sale = deduct_fifo(cursor, item_id, qty)
        
        cursor.execute('''INSERT OR IGNORE INTO sales (barcode, customer_name, customer_phone, item_id, qty, selling_price, total, cost_at_sale, sale_date, status) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                       (barcode, customer, phone, item_id, qty, selling_price, total_value, cost_at_sale, sale_date, status))
        conn.commit()
        log_activity(session['username'], "Manual Sale Added", f"Barcode: {barcode}, Qty: {qty}, Total: Rs.{total_value}")
        
        # --- META CAPI: PURCHASE EVENT යැවීම ---
        customer_info = {
            "phone": phone,
            "client_ip": request.remote_addr,
            "client_user_agent": request.headers.get('User-Agent')
        }
        custom_info = {
            "value": total_value,
            "order_id": barcode
        }
        send_meta_capi_event('Purchase', customer_info, custom_info)
        # -------------------------------------------------------------

        return redirect(url_for('sales'))
        
    # 🎯 නිවැරදි Available Stock ගණනය කිරීම (Sales පේජ් එක සඳහා)
    cursor.execute("""
        SELECT i.id, i.item_name, 
               (
                   COALESCE((SELECT SUM(qty) FROM stock_batches WHERE item_id = i.id AND (source = 'Manual' OR source IS NULL)), 0) +
                   COALESCE((SELECT SUM(qty) FROM returns WHERE item_id = i.id), 0)
               ) - 
               COALESCE((SELECT SUM(qty) FROM sales WHERE item_id = i.id), 0) as available_stock
        FROM items i 
        ORDER BY i.item_name ASC
    """)
    all_items = cursor.fetchall()
    
    # 🎯 අලුත්: අවසන් වරට ඇතුලත් කල Orders 10 ගැනීම
    cursor.execute('''
        SELECT s.id, s.customer_name, s.customer_phone, i.item_name, s.qty, s.total, s.status 
        FROM sales s 
        JOIN items i ON s.item_id = i.id 
        ORDER BY s.id DESC 
        LIMIT 10
    ''')
    
    recent_orders_data = []
    columns = ['id', 'customer_name', 'phone', 'item_name', 'qty', 'total_price', 'status']
    for row in cursor.fetchall():
        recent_orders_data.append(dict(zip(columns, row)))
        
    conn.close()
    
    # 🎯 පරණ summary සහ profit දත්ත අයින් කරලා අලුත් recent_orders යැවීම
    return render_template('sales.html', 
                           items=all_items, 
                           today_date=date.today().strftime('%Y-%m-%d'), 
                           recent_orders=recent_orders_data)


@app.route('/delete_sale/<int:sale_id>')
def delete_sale(sale_id):
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, qty, cost_at_sale, barcode FROM sales WHERE id=?", (sale_id,))
    sale = cursor.fetchone()
    if sale:
        cost = sale[2] if sale[2] is not None else 0.0
        unit_cost = cost / sale[1] if (sale[1] and sale[1] > 0) else 0.0
        today_date = date.today().strftime('%Y-%m-%d')
        cursor.execute("INSERT INTO deleted_sales (barcode, customer_name, item_id, qty, selling_price, total, cost_at_sale, sale_date, deleted_date) SELECT barcode, customer_name, item_id, qty, selling_price, total, cost_at_sale, sale_date, ? FROM sales WHERE id=?", (today_date, sale_id))
        cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date, source) VALUES (?, ?, ?, ?, ?, 'Auto')", (sale[0], unit_cost, sale[1], sale[1], today_date))
        cursor.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()
        log_activity(session['username'], "Delete Sale", f"Deleted Sale ID: {sale_id}")
    conn.close()
    return redirect(url_for('sales'))

# --- RETURNS (Simplified via Barcode) ---
@app.route('/returns', methods=['GET', 'POST'])
def handle_returns():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    error_msg = None
    
    if request.method == 'POST':
        barcode = request.form.get('barcode', '').strip()
        return_date = request.form['return_date']
        
        cursor.execute("SELECT id, item_id, qty, total, cost_at_sale, status FROM sales WHERE barcode=?", (barcode,))
        sale = cursor.fetchone()
        if sale:
            if sale[5] == 'Returned':
                error_msg = f"'{barcode}' දරණ ඕඩරය දැනටමත් Return කර ඇත!"
            else:
                # අලුතින් හදපු Error එක නොඑන කෝඩ් එක මෙතන තියෙනවා
                cost = sale[4] if sale[4] is not None else 0.0
                unit_cost = cost / sale[2] if (sale[2] and sale[2] > 0) else 0.0
                
                # ... (කලින් කෝඩ් එක) ...
                cursor.execute("INSERT INTO returns (item_id, qty, return_amount, cost_at_return, return_date, barcode) VALUES (?, ?, ?, ?, ?, ?)", 
                               (sale[1], sale[2], sale[3], cost, return_date, barcode))
                cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date, source) VALUES (?, ?, ?, ?, ?, 'Auto')", (sale[1], unit_cost, sale[2], sale[2], return_date))
                cursor.execute("UPDATE sales SET status='Returned' WHERE barcode=?", (barcode,))
                conn.commit()
                log_activity(session['username'], "Manual Return", f"Barcode: {barcode}")
                
                # --- META CAPI: REFUND EVENT යැවීම ---
                cursor.execute("SELECT customer_phone FROM sales WHERE barcode=?", (barcode,))
                phone_row = cursor.fetchone()
                cust_phone = phone_row[0] if phone_row else ''

                customer_info = {
                    "phone": cust_phone,
                    "client_ip": request.remote_addr,
                    "client_user_agent": request.headers.get('User-Agent')
                }
                custom_info = {
                    "value": float(sale[3]) if sale else 0.0, 
                    "order_id": barcode
                }
                send_meta_capi_event('Refund', customer_info, custom_info)
                # -----------------------------------------------------------

                return redirect(url_for('handle_returns'))
        else:
# ... (කලින් කෝඩ් එක) ...
            error_msg = "Barcode එක පද්ධතියේ නොමැත!"

    # තියෙන Returns ටික අරන් HTML එකට යවනවා
    cursor.execute('''SELECT r.id, i.item_name, r.qty, r.return_amount, r.return_date, r.barcode 
                      FROM returns r JOIN items i ON r.item_id = i.id ORDER BY r.return_date DESC, r.id DESC LIMIT 50''')
    all_returns = cursor.fetchall()
    conn.close()
    
    today_str = date.today().strftime('%Y-%m-%d')
    return render_template('returns.html', returns=all_returns, today_date=today_str, error=error_msg)

@app.route('/delete_return/<int:return_id>')
def delete_return(return_id):
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, qty, barcode FROM returns WHERE id=?", (return_id,))
    ret = cursor.fetchone()
    if ret:
        deduct_fifo(cursor, ret[0], ret[1])
        # Return එක මකද්දී ආපහු ඒක 'Credit' වෙනවා (සල්ලි ලැබුණේ නෑ කියලා හිතලා)
        if ret[2]: cursor.execute("UPDATE sales SET status='Credit' WHERE barcode=?", (ret[2],))
        cursor.execute("DELETE FROM returns WHERE id=?", (return_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('handle_returns'))

# --- AD EXPENSES UPDATED & FIXED ---
@app.route('/expenses', methods=['GET', 'POST'])
def expenses():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    today = get_sl_today()
    today_str = today.strftime('%Y-%m-%d')
    first_day_str = today.replace(day=1).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        action = request.form.get('action')
        item_name = request.form['item_name']
        amount = float(request.form['amount'])
        expense_date = request.form['expense_date']
        
        if action == 'add':
            cursor.execute("INSERT INTO expenses (platform, amount, expense_date) VALUES (?, ?, ?)", (item_name, amount, expense_date))
        elif action == 'edit':
            expense_id = request.form['expense_id']
            cursor.execute("UPDATE expenses SET platform=?, amount=?, expense_date=? WHERE id=?", (item_name, amount, expense_date, expense_id))
            
        conn.commit()
        log_activity(session['username'], "Add/Edit Expense", f"Item: {item_name}")
        return redirect(url_for('expenses'))
        
    # 🎯 Date Filters & Logic
    start_date = request.args.get('start_date', first_day_str)
    end_date = request.args.get('end_date', today_str)
    is_filtered = 'start_date' in request.args
    
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()
    
    # 🎯 1. Summary Calculation (Item-wise & Total for the period)
    cursor.execute("SELECT platform, SUM(amount) FROM expenses WHERE expense_date BETWEEN ? AND ? GROUP BY platform", (start_date, end_date))
    item_totals = cursor.fetchall()
    total_amount = sum([row[1] for row in item_totals])
    
    # 🎯 2. Table Data (Limit 10 if not filtered to avoid slowing down)
    if is_filtered:
        cursor.execute("SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date DESC, id DESC", (start_date, end_date))
    else:
        cursor.execute("SELECT * FROM expenses ORDER BY expense_date DESC, id DESC LIMIT 10")
        
    all_expenses = cursor.fetchall()
    conn.close()
    
    return render_template('expenses.html', expenses=all_expenses, items=items, today_date=today_str, 
                           start_date=start_date, end_date=end_date, item_totals=item_totals, 
                           total_amount=total_amount, is_filtered=is_filtered)

@app.route('/delete_expense/<int:expense_id>')
def delete_expense(expense_id):
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('expenses'))

# --- ADVANCED EXCEL UPLOADS & SEARCH ---
@app.route('/advanced_orders')
def advanced_orders():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, item_name FROM items")
    items = cursor.fetchall()
    search_query = request.args.get('q', '').strip()
    
    if search_query:
        like_q = f"%{search_query}%"

        # වෙනස් කළ SQL පේළිය
        cursor.execute('''SELECT s.id, s.barcode, s.customer_name, s.customer_phone, s.item_id, s.qty, s.selling_price, s.total, s.cost_at_sale, s.sale_date, s.status, i.item_name, s.payment_date 
                          FROM sales s JOIN items i ON s.item_id = i.id 
                          WHERE s.barcode LIKE ? OR s.customer_name LIKE ? OR s.customer_phone LIKE ? 
                          ORDER BY s.id DESC LIMIT 100''', (like_q, like_q, like_q))
        orders = cursor.fetchall()
    else:
        # වෙනස් කළ SQL පේළිය
        cursor.execute('''SELECT s.id, s.barcode, s.customer_name, s.customer_phone, s.item_id, s.qty, s.selling_price, s.total, s.cost_at_sale, s.sale_date, s.status, i.item_name, s.payment_date 
                          FROM sales s JOIN items i ON s.item_id = i.id ORDER BY s.id DESC LIMIT 20''')
        orders = cursor.fetchall()
        
    conn.close()
    return render_template('advanced.html', items=items, orders=orders, search_query=search_query)

@app.route('/edit_advanced_order', methods=['POST'])
def edit_advanced_order():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    sale_id = request.form['sale_id']
    new_barcode = request.form['barcode']
    new_customer = request.form['customer_name']
    new_phone = request.form['customer_phone']
    new_status = request.form['status']
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # 📝 වෙනස 1: මෙහි අගට 'total' (විකුණුම් මිල) ලබා ගැනීමට එකතු කර ඇත
    cursor.execute("SELECT status, item_id, qty, cost_at_sale, barcode, total FROM sales WHERE id=?", (sale_id,))
    sale = cursor.fetchone()
    
    if sale:
        old_status, item_id, qty, cost_at_sale, old_barcode, sale_total = sale
        cost_at_sale = cost_at_sale if cost_at_sale is not None else 0.0
        unit_cost = cost_at_sale / qty if (qty and qty > 0) else 0.0
        today = date.today().strftime('%Y-%m-%d')
        
        if old_status != 'Returned' and new_status == 'Returned':
            # 📝 වෙනස 2: return_amount එකට 'sale_total' (විකුණුම් මිල) යන ලෙස නිවැරදි කර ඇත
            cursor.execute("INSERT INTO returns (item_id, qty, return_amount, cost_at_return, return_date, barcode) VALUES (?, ?, ?, ?, ?, ?)", (item_id, qty, sale_total, cost_at_sale, today, new_barcode))
            cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date, source) VALUES (?, ?, ?, ?, ?, 'Auto')", (item_id, unit_cost, qty, qty, today))
            
        elif old_status == 'Returned' and new_status != 'Returned':
            deduct_fifo(cursor, item_id, qty)
            cursor.execute("DELETE FROM returns WHERE barcode=?", (old_barcode,))
            
        cursor.execute("UPDATE sales SET barcode=?, customer_name=?, customer_phone=?, status=? WHERE id=?", (new_barcode, new_customer, new_phone, new_status, sale_id))
        cursor.execute("UPDATE returns SET barcode=? WHERE barcode=?", (new_barcode, old_barcode))
        
    conn.commit()
    conn.close()
    return redirect(url_for('advanced_orders'))

@app.route('/delete_advanced_order/<int:sale_id>')
def delete_advanced_order(sale_id):
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, qty, status, barcode FROM sales WHERE id=?", (sale_id,))
    sale = cursor.fetchone()
    if sale:
        item_id, qty, status, barcode = sale
        today_date = date.today().strftime('%Y-%m-%d')
        cursor.execute("INSERT INTO deleted_sales (barcode, customer_name, item_id, qty, selling_price, total, cost_at_sale, sale_date, deleted_date) SELECT barcode, customer_name, item_id, qty, selling_price, total, cost_at_sale, sale_date, ? FROM sales WHERE id=?", (today_date, sale_id))
        if status != 'Returned':
            cursor.execute("SELECT cost_at_sale FROM sales WHERE id=?", (sale_id,))
            cost_row = cursor.fetchone()
            cost = cost_row[0] if (cost_row and cost_row[0] is not None) else 0.0
            unit_cost = cost / qty if (qty and qty > 0) else 0.0
            cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date, source) VALUES (?, ?, ?, ?, ?, 'Auto')", (item_id, unit_cost, qty, qty, today_date))
        else:
            cursor.execute("DELETE FROM returns WHERE barcode=?", (barcode,))
        cursor.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('advanced_orders'))

# --- EXCEL TEMPLATES & UPLOADS (Dates Included) ---
@app.route('/download_template/<tmpl_type>')
def download_template(tmpl_type):
    import pandas as pd
    if tmpl_type == 'sales': 
        df = pd.DataFrame(columns=['Sale Date', 'Barcode', 'Customer Name', 'Phone', 'Item ID', 'Qty', 'Total Value'])
    elif tmpl_type == 'returns': 
        df = pd.DataFrame(columns=['Return Date', 'Barcode'])
    elif tmpl_type == 'payments':
        df = pd.DataFrame(columns=['Payment Date', 'Barcode'])
    elif tmpl_type == 'revert_credit':  # අලුතින් එකතු කරපු කොටස
        df = pd.DataFrame(columns=['Barcode'])
    else:
        df = pd.DataFrame()
        
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"{tmpl_type}_template.xlsx", as_attachment=True)

@app.route('/upload_sales', methods=['POST'])
def upload_sales():
    file = request.files['file']
    df = pd.read_excel(file)
    today = date.today().strftime('%Y-%m-%d')
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    for index, row in df.iterrows():
        try:
            # Date එක Clean කිරීම
            raw_date = row.get('Sale Date', None)
            if pd.notna(raw_date): sale_date = pd.to_datetime(str(raw_date)).strftime('%Y-%m-%d')
            else: sale_date = today

            barcode = str(row['Barcode']).strip()
            item_id = int(row['Item ID'])
            
            # Qty සහ Total Value එකේ තියෙන කොමා අයින් කරලා ඉලක්කම් ගැනීම
            q_val = str(row['Qty']).replace(',', '').strip()
            qty = int(float(q_val)) if q_val and q_val.lower() != 'nan' else 1
            
            t_val = str(row['Total Value']).replace(',', '').strip()
            total = float(t_val) if t_val and t_val.lower() != 'nan' else 0.0
            
            selling_price = total / qty if qty > 0 else 0
            
            cost_at_sale = deduct_fifo(cursor, item_id, qty)
            cursor.execute('''INSERT OR IGNORE INTO sales (barcode, customer_name, customer_phone, item_id, qty, selling_price, total, cost_at_sale, sale_date, status) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Credit')''', 
                           (barcode, str(row.get('Customer Name', '')), str(row.get('Phone', '')), item_id, qty, selling_price, total, cost_at_sale, sale_date))
        except Exception as e: 
            continue
            
            barcode = str(row['Barcode']).strip()
            item_id = int(row['Item ID'])
            qty = int(row['Qty'])
            total = float(row['Total Value'])
            selling_price = total / qty if qty > 0 else 0
            
            cost_at_sale = deduct_fifo(cursor, item_id, qty)
            cursor.execute('''INSERT OR IGNORE INTO sales (barcode, customer_name, customer_phone, item_id, qty, selling_price, total, cost_at_sale, sale_date, status) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Credit')''', 
                           (barcode, str(row['Customer Name']), str(row['Phone']), item_id, qty, selling_price, total, cost_at_sale, sale_date))
        except: continue
    conn.commit()
    log_activity(session['username'], "Upload Excel (Sales)", "Uploaded new daily sales via Excel.")
    conn.close()
    return redirect(url_for('advanced_orders'))

@app.route('/upload_returns', methods=['POST'])
def upload_returns():
    file = request.files['file']
    df = pd.read_excel(file)
    today = date.today().strftime('%Y-%m-%d')
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    for index, row in df.iterrows():
        try:
            barcode = str(row['Barcode']).strip()
            raw_date = row.get('Return Date', None)
            if pd.notna(raw_date): return_date = pd.to_datetime(str(raw_date)).strftime('%Y-%m-%d')
            else: return_date = today
            
            cursor.execute("SELECT id, item_id, qty, total, cost_at_sale, status FROM sales WHERE barcode=?", (barcode,))
            sale = cursor.fetchone()
            if sale and sale[5] != 'Returned':
                # මෙතනත් අපි ඒ නිවැරදි කිරීමම කරනවා
                cost = sale[4] if sale[4] is not None else 0.0
                unit_cost = cost / sale[2] if (sale[2] and sale[2] > 0) else 0.0
                
                cursor.execute("INSERT INTO returns (item_id, qty, return_amount, cost_at_return, return_date, barcode) VALUES (?, ?, ?, ?, ?, ?)", 
                               (sale[1], sale[2], sale[3], cost, return_date, barcode))
                cursor.execute("UPDATE sales SET status='Returned' WHERE barcode=?", (barcode,))
                cursor.execute("INSERT INTO stock_batches (item_id, cost_price, qty, remaining_qty, stock_date, source) VALUES (?, ?, ?, ?, ?, 'Auto')", 
                               (sale[1], unit_cost, sale[2], sale[2], return_date))

        except: continue
    conn.commit()
    log_activity(session['username'], "Excel Upload", "Bulk Returns Uploaded")
    conn.close()
    return redirect(url_for('advanced_orders'))

@app.route('/upload_payments', methods=['POST'])
def upload_payments():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    file = request.files['file']
    df = pd.read_excel(file)
    today = date.today().strftime('%Y-%m-%d')
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    for index, row in df.iterrows():
        try:
            barcode = str(row['Barcode']).strip()
            raw_date = row.get('Payment Date', None)
            if pd.notna(raw_date): payment_date = pd.to_datetime(str(raw_date)).strftime('%Y-%m-%d')
            else: payment_date = today
            cursor.execute("UPDATE sales SET status='Paid', payment_date=? WHERE barcode=? AND status='Credit'", (payment_date, barcode))
        except: continue
    conn.commit()
    log_activity(session['username'], "Excel Upload", "Bulk Payments Updated")
    conn.close()
    return redirect(url_for('advanced_orders'))

@app.route('/upload_revert_credit', methods=['POST'])
def upload_revert_credit():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    file = request.files['file']
    import pandas as pd
    df = pd.read_excel(file)
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    for index, row in df.iterrows():
        try:
            barcode = str(row['Barcode']).strip()
            cursor.execute("UPDATE sales SET status='Credit', payment_date=NULL WHERE barcode=? AND status='Paid'", (barcode,))
        except: continue
    conn.commit()
    log_activity(session['username'], "Excel Upload", "Bulk Reverted Paid Orders to Credit")
    conn.close()
    return redirect(url_for('advanced_orders'))

# --- OTHER EXPENSES UPDATED (Date & Edit Options) ---
@app.route('/other_expenses', methods=['GET', 'POST'])
def other_expenses():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    today = get_sl_today()
    today_str = today.strftime('%Y-%m-%d')
    first_day_str = today.replace(day=1).strftime('%Y-%m-%d')
    
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        item_name = request.form.get('item_name', 'Common') 
        description = request.form['description']
        amount = float(request.form['amount'])
        expense_date = request.form['expense_date']
        
        if action == 'add':
            cursor.execute("INSERT INTO other_expenses (item_name, description, amount, expense_date) VALUES (?, ?, ?, ?)", 
                           (item_name, description, amount, expense_date))
        elif action == 'edit':
            expense_id = request.form['expense_id']
            cursor.execute("UPDATE other_expenses SET item_name=?, description=?, amount=?, expense_date=? WHERE id=?", 
                           (item_name, description, amount, expense_date, expense_id))
            
        conn.commit()
        return redirect(url_for('other_expenses'))
        
    # 🎯 Date Filters & Logic
    start_date = request.args.get('start_date', first_day_str)
    end_date = request.args.get('end_date', today_str)
    is_filtered = 'start_date' in request.args
        
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC") 
    items = cursor.fetchall()
    
    # 🎯 1. Summary Calculation
    cursor.execute("SELECT item_name, SUM(amount) FROM other_expenses WHERE expense_date BETWEEN ? AND ? GROUP BY item_name", (start_date, end_date))
    item_totals = cursor.fetchall()
    total_amount = sum([row[1] for row in item_totals])
        
    # 🎯 2. Table Data (Limit 10)
    if is_filtered:
        cursor.execute("SELECT * FROM other_expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date DESC, id DESC", (start_date, end_date))
    else:
        cursor.execute("SELECT * FROM other_expenses ORDER BY expense_date DESC, id DESC LIMIT 10")
        
    all_expenses = cursor.fetchall()
    conn.close()
    
    return render_template('other_expenses.html', expenses=all_expenses, items=items, today_date=today_str,
                           start_date=start_date, end_date=end_date, item_totals=item_totals, 
                           total_amount=total_amount, is_filtered=is_filtered)

@app.route('/delete_other_expense/<int:expense_id>')
def delete_other_expense(expense_id):
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM other_expenses WHERE id=?", (expense_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('other_expenses'))

@app.route('/notes', methods=['GET', 'POST'])
def notes():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add': cursor.execute("INSERT INTO notes (content, color, note_date) VALUES (?, ?, ?)", (request.form['content'], request.form['color'], request.form['note_date']))
        elif action == 'edit': cursor.execute("UPDATE notes SET content=?, note_date=? WHERE id=?", (request.form['content'], request.form['note_date'], request.form['note_id']))
        conn.commit()
        log_activity(session['username'], "Add Note", "Added a new note.")
        return redirect(url_for('notes'))
    cursor.execute("SELECT * FROM notes ORDER BY id DESC")
    all_notes = cursor.fetchall()
    conn.close()
    return render_template('notes.html', notes=all_notes, today_date=date.today().strftime('%Y-%m-%d'))

@app.route('/delete_note/<int:note_id>')
def delete_note(note_id):
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('notes'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# --- SALES REPORT SECTION ---
@app.route('/reports/sales', methods=['GET', 'POST'])
def reports_sales():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # URL එකෙන් Filter පරාමිතීන් (Parameters) ලබාගැනීම
    page = int(request.args.get('page', 1))
    start_date = request.args.get('start_date', date.today().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_id', 'all')
    selected_status = request.args.get('status', 'all')
    offset = (page - 1) * 15

    # Dropdown එකට Item ලිස්ට් එක ලබාගැනීම
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()

    # Dynamic SQL Query එක සෑදීම
    query_conditions = "s.sale_date BETWEEN ? AND ?"
    params = [start_date, end_date]

    if selected_item != 'all':
        query_conditions += " AND s.item_id = ?"
        params.append(selected_item)
        
    if selected_status != 'all':
        query_conditions += " AND s.status = ?"
        params.append(selected_status)

    # Orders Data ලබාගැනීම (වෙනස් වන Query එක අනුව)
    query = f'''SELECT s.id, s.barcode, s.customer_name, s.customer_phone, s.item_id, s.qty, s.selling_price, s.total, s.cost_at_sale, s.sale_date, s.status, i.item_name, s.payment_date 
                FROM sales s JOIN items i ON s.item_id = i.id 
                WHERE {query_conditions} ORDER BY s.sale_date DESC, s.id DESC LIMIT 15 OFFSET ?'''
    cursor.execute(query, params + [offset])
    orders = cursor.fetchall()
    
    # Totals සහ Counts ගණනය කිරීම (Total Orders ඇතුළුව)
    
    # Totals සහ Counts ගණනය කිරීම (Total Orders සහ Returned Status ඇතුළුව)
    cursor.execute(f"SELECT SUM(total), COUNT(id) FROM sales s WHERE {query_conditions} AND s.status IN ('Credit', 'Paid', 'Returned')", params)
    sales_data = cursor.fetchone()
    total_sales = sales_data[0] or 0.0
    total_count = sales_data[1] or 0
    
    cursor.execute(f"SELECT SUM(total), COUNT(id) FROM sales s WHERE {query_conditions} AND s.status='Paid'", params)
    cash_data = cursor.fetchone()
    total_cash = cash_data[0] or 0.0
    cash_count = cash_data[1] or 0
    
    cursor.execute(f"SELECT SUM(total), COUNT(id) FROM sales s WHERE {query_conditions} AND s.status='Credit'", params)
    credit_data = cursor.fetchone()
    total_credit = credit_data[0] or 0.0
    credit_count = credit_data[1] or 0

    # Returns ගණනය කිරීම (barcode එක මත පදනම්ව JOIN කර ඇත)
    cursor.execute(f'''
        SELECT SUM(r.return_amount), COUNT(r.id) 
        FROM returns r 
        JOIN sales s ON r.barcode = s.barcode 
        WHERE {query_conditions}
    ''', params)
    return_data = cursor.fetchone()
    total_return = return_data[0] or 0.0
    return_count = return_data[1] or 0

    conn.close()
    
    return render_template('reports_sales.html', orders=orders, start_date=start_date, end_date=end_date, 
                           page=page, total_sales=total_sales, total_cash=total_cash, 
                           total_credit=total_credit, total_return=total_return, 
                           items=items, selected_item=selected_item, selected_status=selected_status,
                           cash_count=cash_count, credit_count=credit_count, 
                           total_count=total_count, return_count=return_count)

# --- REPORT HUB SECTION ---
@app.route('/reports')
def reports_home():
    if 'username' not in session: return redirect(url_for('login'))
    return render_template('reports_home.html')

# --- RETURN REPORT SECTION ---
@app.route('/reports/returns', methods=['GET', 'POST'])
def reports_returns():
    if 'username' not in session: return redirect(url_for('login'))
    
    start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_id', 'all')
    filter_type = request.args.get('filter_type', 'return_date') # අලුතින් එක් කළ Filter Type එක
    page = int(request.args.get('page', 1))
    offset = (page - 1) * 15
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # 1. භාණ්ඩ ලැයිස්තුව ලබා ගැනීම (Dropdown එකට)
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items_list = cursor.fetchall()
    
    # 2. Main Query එක සහ Total Orders ගණනය කිරීම සඳහා Query එක සැකසීම
    if filter_type == 'sale_date':
        # Sale Date එකෙන් Filter කරන විට Sales Table එක JOIN කරගැනීම
        query_returns = "SELECT r.id, i.item_name, r.qty, r.return_amount, r.return_date, r.barcode, s.sale_date FROM returns r JOIN items i ON r.item_id = i.id JOIN sales s ON r.barcode = s.barcode WHERE s.sale_date BETWEEN ? AND ?"
        query_total = "SELECT COUNT(r.id), SUM(r.return_amount) FROM returns r JOIN sales s ON r.barcode = s.barcode WHERE s.sale_date BETWEEN ? AND ?"
    else:
        # සාමාන්‍ය Return Date එකෙන් Filter කිරීම
        query_returns = "SELECT r.id, i.item_name, r.qty, r.return_amount, r.return_date, r.barcode FROM returns r JOIN items i ON r.item_id = i.id WHERE r.return_date BETWEEN ? AND ?"
        query_total = "SELECT COUNT(r.id), SUM(r.return_amount) FROM returns r WHERE r.return_date BETWEEN ? AND ?"
        
    params = [start_date, end_date]
    
    # 3. Item එකක් තෝරා ඇත්නම් Query එකට එය එකතු කිරීම
    if selected_item != 'all':
        query_returns += " AND r.item_id = ?"
        query_total += " AND r.item_id = ?"
        params.append(selected_item)
        
    # 4. පිළිවෙලට සැකසීම (Order By) - ෆිල්ටර් කරන දවසට අනුව අනුපිළිවෙල සැකසේ
    if filter_type == 'sale_date':
        query_returns += " ORDER BY s.sale_date DESC, r.id DESC LIMIT 15 OFFSET ?"
    else:
        query_returns += " ORDER BY r.return_date DESC, r.id DESC LIMIT 15 OFFSET ?"
        
    params_returns = params + [offset]
    
    # 5. දත්ත ලබා ගැනීම
    cursor.execute(query_returns, params_returns)
    returns = cursor.fetchall()
    
    cursor.execute(query_total, params)
    total_data = cursor.fetchone()
    total_orders = total_data[0] if total_data and total_data[0] else 0
    total_amount = total_data[1] if total_data and total_data[1] else 0.0
    
    conn.close()
    
    return render_template('reports_returns.html', returns=returns, start_date=start_date, end_date=end_date, 
                           items_list=items_list, selected_item=selected_item, page=page, 
                           total_orders=total_orders, total_amount=total_amount, filter_type=filter_type)

# --- AVAILABLE STOCK REPORT UPDATED ---
@app.route('/reports/stock')
def reports_stock():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied!"
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # හැම අයිටම් එකක්ම ගන්නවා
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()
    
    stocks = []  # 🔴 HTML එක බලාපොරොත්තු වෙන 'stocks' කියන නම
    grand_total = 0.0 # 🔴 මුළු වටිනාකම (Grand Total)
    
    for item in items:
        i_id = item[0]
        i_name = item[1]
        
        # 1. Purchases (Manual ඇඩ් කරපු ඒවා පමණක්)
        cursor.execute("SELECT SUM(qty) FROM stock_batches WHERE item_id=? AND (source = 'Manual' OR source IS NULL)", (i_id,))
        purchases = cursor.fetchone()[0] or 0
        
        # 2. Returns (Customer Returns)
        cursor.execute("SELECT SUM(qty) FROM returns WHERE item_id=?", (i_id,))
        ret = cursor.fetchone()[0] or 0
        
        # 3. Sales (විකිණුම්)
        cursor.execute("SELECT SUM(qty) FROM sales WHERE item_id=?", (i_id,))
        sales = cursor.fetchone()[0] or 0
        
        # 🎯 හරියටම නිවැරදි Available Stock එක ගණනය කිරීම
        available = (purchases + ret) - sales
        
        # ස්ටොක් එකේ බඩු තියෙනවා නම් විතරක් රිපෝට් එකට ගන්නවා
        if available > 0:
            # මේ Item එකේ අන්තිමටම ගෙනාපු Unit Cost එක ගන්නවා
            cursor.execute("SELECT cost_price FROM stock_batches WHERE item_id=? AND (source = 'Manual' OR source IS NULL) ORDER BY id DESC LIMIT 1", (i_id,))
            cost_row = cursor.fetchone()
            unit_cost = float(cost_row[0]) if cost_row else 0.0
            
            # Grand Total එකට එකතු කරනවා
            grand_total += (unit_cost * available)
            
            # HTML එක බලාපොරොත්තු වෙන පිළිවෙළට (Name, Unit Cost, Qty) යැවීම
            stocks.append((i_name, unit_cost, available))
        
    conn.close()
    
    # 🔴 'stocks' සහ 'grand_total' දෙකම යවනවා
    return render_template('reports_stock.html', stocks=stocks, grand_total=grand_total)

# 1. Ad Expenses Route
@app.route('/reports/expenses/ad', methods=['GET', 'POST'])
def report_ad_expenses():
    if 'username' not in session: return redirect(url_for('login'))
    
    start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_name', 'all')
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # Dropdown එක සඳහා භාණ්ඩ ලැයිස්තුව ලබා ගැනීම
    cursor.execute("SELECT item_name FROM items ORDER BY item_name ASC")
    items_list = [row[0] for row in cursor.fetchall()]
    
    # 📝 වෙනස: item_name වෙනුවට platform කොලමෙන් දත්ත ලබා ගැනීම
    query = "SELECT id, platform, amount, expense_date FROM expenses WHERE expense_date BETWEEN ? AND ?"
    params = [start_date, end_date]
    
    if selected_item != 'all':
        # 📝 වෙනස: platform එක හරහා filter කිරීම
        query += " AND platform = ?"
        params.append(selected_item)
        
    query += " ORDER BY expense_date DESC, id DESC"
    cursor.execute(query, params)
    expenses = cursor.fetchall()
    
    total_amount = sum([e[2] for e in expenses]) if expenses else 0.0
    
    conn.close()
    return render_template('reports_ad_expenses.html', expenses=expenses, start_date=start_date, end_date=end_date, items_list=items_list, selected_item=selected_item, total_amount=total_amount)

# 2. Other Expenses Route
@app.route('/reports/expenses/other', methods=['GET', 'POST'])
def reports_other_expenses():
    if 'username' not in session: return redirect(url_for('login'))
    
    start_date = request.args.get('start_date', date.today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_name', 'all')
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # other_expenses වගුවට item_name නොමැති නම් එය අලුතින් එක් කිරීම
    try: cursor.execute("ALTER TABLE other_expenses ADD COLUMN item_name TEXT")
    except: pass
    
    # Dropdown එක සඳහා භාණ්ඩ ලැයිස්තුව ලබා ගැනීම
    cursor.execute("SELECT item_name FROM items ORDER BY item_name ASC")
    items_list = [row[0] for row in cursor.fetchall()]
    
    query = "SELECT id, description, amount, expense_date, item_name FROM other_expenses WHERE expense_date BETWEEN ? AND ?"
    params = [start_date, end_date]
    
    if selected_item != 'all':
        query += " AND item_name = ?"
        params.append(selected_item)
        
    query += " ORDER BY expense_date DESC, id DESC"
    cursor.execute(query, params)
    expenses = cursor.fetchall()
    
    total_amount = sum([e[2] for e in expenses]) if expenses else 0.0
    
    conn.close()
    return render_template('reports_other_expenses.html', expenses=expenses, start_date=start_date, end_date=end_date, items_list=items_list, selected_item=selected_item, total_amount=total_amount)

# ==========================================
# Purchase History Report (Admin Only)
# ==========================================

@app.route('/reports/purchases')
def reports_purchases():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    # 🎯 Date සහ Item Filters ලබාගැනීම
    start_date = request.args.get('start_date', get_sl_today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', get_sl_today().strftime('%Y-%m-%d'))
    item_id = request.args.get('item_id', 'All')
    
    page = int(request.args.get('page', 1))
    per_page = 50
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # Dropdown එක සඳහා Items ටික ලබා ගැනීම
    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()
    
    # 🎯 Return වලින් එන ඒවා ඉවත් කර, 'Manual' Add කළ ඒවා පමණක් ලබාගන්නා Query එක
    query = """
        SELECT b.id, i.item_name, b.cost_price, b.qty, b.stock_date, (b.cost_price * b.qty) as total_value 
        FROM stock_batches b
        JOIN items i ON b.item_id = i.id
        WHERE b.stock_date BETWEEN ? AND ? AND (b.source = 'Manual' OR b.source IS NULL)
    """
    params = [start_date, end_date]
    
    if item_id != 'All':
        query += " AND b.item_id = ?"
        params.append(item_id)
        
    query += " ORDER BY b.stock_date DESC, b.id DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    
    cursor.execute(query, params)
    purchases = cursor.fetchall()
    
    # 🎯 මුළු වියදම (Total Purchase Value) ගණනය කිරීම
    total_query = """
        SELECT SUM(b.cost_price * b.qty) 
        FROM stock_batches b
        WHERE b.stock_date BETWEEN ? AND ? AND (b.source = 'Manual' OR b.source IS NULL)
    """
    t_params = [start_date, end_date]
    
    if item_id != 'All':
        total_query += " AND b.item_id = ?"
        t_params.append(item_id)
        
    cursor.execute(total_query, t_params)
    total_value = cursor.fetchone()[0]
    total_value = total_value if total_value else 0.0
    
    conn.close()
    
    return render_template('reports_purchases.html', 
                           purchases=purchases, 
                           items=items, 
                           start_date=start_date, 
                           end_date=end_date, 
                           selected_item=item_id, 
                           total_value=total_value,
                           page=page)


# --- ACTIVITY LOGS ROUTE ---
@app.route('/logs')
def view_logs():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    search_query = request.args.get('q', '').strip()
    if search_query:
        like_q = f"%{search_query}%"
        cursor.execute("SELECT * FROM activity_logs WHERE action LIKE ? OR details LIKE ? OR username LIKE ? ORDER BY timestamp DESC LIMIT 300", (like_q, like_q, like_q))
    else:
        cursor.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 300")
    logs = cursor.fetchall()
    conn.close()
    return render_template('activity_logs.html', logs=logs, search_query=search_query)

# 🎯 අලුත් ඩිස්ක් එකට කෙලින්ම Database එක දාන රහස් පාරක්
@app.route('/upload_db_secret', methods=['GET', 'POST'])
def upload_db_secret():
    if request.method == 'POST':
        file = request.files.get('file')
        if file:
            # ඔයා අප්ලෝඩ් කරන ෆයිල් එක කෙලින්ම මැකෙන්නේ නැති Disk එකට සේව් වෙනවා
            file.save('/var/data/database.db')
            return "✅ පරණ Database එක සාර්ථකව Upload වුණා! දැන් සයිට් එකට ගිහින් ලොග් වෙන්න."
    return '''
    <h2>ඔයාගේ ඇත්තම පරණ database.db ෆයිල් එක මෙතනින් Upload කරන්න</h2>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept=".db">
      <input type="submit" value="Upload Database">
    </form>
    '''

@app.route('/download_items_list')
def download_items_list():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    # අයිටම් ලිස්ට් එක Excel එකක් විදියට ගන්නවා
    df = pd.read_sql_query("SELECT id as 'Item ID', item_name as 'Item Name' FROM items", conn)
    conn.close()
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name="items_list.xlsx", as_attachment=True)

# --- EXCEL DOWNLOAD ROUTE ---
@app.route('/download/sales_excel')
def download_sales_excel():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    
    start_date = request.args.get('start_date', date.today().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_id', 'all')
    selected_status = request.args.get('status', 'all')

    query_conditions = "s.sale_date BETWEEN ? AND ?"
    params = [start_date, end_date]

    if selected_item != 'all':
        query_conditions += " AND s.item_id = ?"
        params.append(selected_item)
    if selected_status != 'all':
        query_conditions += " AND s.status = ?"
        params.append(selected_status)

    # සියලුම විස්තර ගන්නා SQL Query එක
    query = f'''SELECT s.sale_date as 'Date', s.barcode as 'Barcode', s.customer_name as 'Customer', s.customer_phone as 'Phone', i.item_name as 'Item', s.qty as 'Qty', s.selling_price as 'Unit Price (Rs)', s.total as 'Total (Rs)', s.status as 'Status', s.payment_date as 'Payment Date' 
                FROM sales s JOIN items i ON s.item_id = i.id 
                WHERE {query_conditions} ORDER BY s.sale_date DESC, s.id DESC'''
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"Sales_Report_{start_date}_to_{end_date}.xlsx", as_attachment=True)

# --- PDF (PRINT) ROUTE ---
@app.route('/print/sales_pdf')
def print_sales_pdf():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    start_date = request.args.get('start_date', date.today().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.args.get('item_id', 'all')
    selected_status = request.args.get('status', 'all')

    query_conditions = "s.sale_date BETWEEN ? AND ?"
    params = [start_date, end_date]

    if selected_item != 'all':
        query_conditions += " AND s.item_id = ?"
        params.append(selected_item)
    if selected_status != 'all':
        query_conditions += " AND s.status = ?"
        params.append(selected_status)

    query = f'''SELECT s.sale_date, s.barcode, s.customer_name, s.customer_phone, i.item_name, s.qty, s.selling_price, s.total, s.status, s.payment_date 
                FROM sales s JOIN items i ON s.item_id = i.id 
                WHERE {query_conditions} ORDER BY s.sale_date DESC, s.id DESC'''
    cursor.execute(query, params)
    orders = cursor.fetchall()
    
    cursor.execute(f"SELECT SUM(total) FROM sales s WHERE {query_conditions} AND s.status IN ('Credit', 'Paid')", params)
    total_sales = cursor.fetchone()[0] or 0.0
    conn.close()
    
    return render_template('print_sales.html', orders=orders, start_date=start_date, end_date=end_date, total_sales=total_sales)

import io
import xlwt 
from flask import send_file

@app.route('/reports/profit_loss', methods=['GET', 'POST'])
def report_profit_loss():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    conn = sqlite3.connect('/var/data/database.db')
    # ... ඉතිරි කෝඩ් එක වෙනස් කරන්න එපා ...
    cursor = conn.cursor()
    
    # Items ලැයිස්තුව ෆිල්ටර් ඩ්‍රොප්ඩවුන් එකට ගන්න
    cursor.execute("SELECT id, item_name FROM items")
    items_raw = cursor.fetchall()
    items = [{'id': i[0], 'name': i[1]} for i in items_raw]
    
    # default දින සැකසීම
    start_date = request.form.get('start_date', date.today().strftime('%Y-%m-01'))
    end_date = request.form.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.form.get('item_id', 'all')
    
    # 1. Cash Sale සහ ඒ වෙනුවෙන් දරපු Item Cost එක සෙවීම
    query_sales = """
        SELECT s.id, s.sale_date, s.customer_name, s.total, s.cost_at_sale 
        FROM sales s 
        WHERE s.sale_date BETWEEN ? AND ? AND s.status = 'Paid'
    """
    params_sales = [start_date, end_date]
    if selected_item != 'all':
        query_sales += " AND s.item_id = ?"
        params_sales.append(selected_item)
        
    cursor.execute(query_sales, params_sales)
    orders_raw = cursor.fetchall()
    
    total_cash_sales = sum(row[3] for row in orders_raw) if orders_raw else 0.0
    total_item_cost = sum(row[4] for row in orders_raw if row[4] is not None) if orders_raw else 0.0
    
    # 2. Ad Expenses සහ Other Expenses සෙවීම (Item Filter එකත් එක්ක)
    query_ads = "SELECT SUM(amount) FROM expenses WHERE expense_date BETWEEN ? AND ?"
    params_ads = [start_date, end_date]
    
    query_other = "SELECT SUM(amount) FROM other_expenses WHERE expense_date BETWEEN ? AND ?"
    params_other = [start_date, end_date]

    if selected_item != 'all':
        # තෝරාගත් Item ID එකට අදාල Item එකේ නම ඩේටාබේස් එකෙන් සොයා ගැනීම
        cursor.execute("SELECT item_name FROM items WHERE id = ?", (selected_item,))
        item_row = cursor.fetchone()
        if item_row:
            item_name_str = item_row[0]
            
            # Ad expenses වල item_name එක සේව් වෙන්නේ 'platform' column එකේ නිසා
            query_ads += " AND platform = ?"
            params_ads.append(item_name_str)
            
            # Other expenses වල item_name එක සේව් වෙන්නේ 'item_name' column එකේ නිසා
            query_other += " AND item_name = ?"
            params_other.append(item_name_str)

    cursor.execute(query_ads, params_ads)
    total_ads = cursor.fetchone()[0] or 0.0
    
    cursor.execute(query_other, params_other)
    total_other_expenses = cursor.fetchone()[0] or 0.0
    
    # 3. Profit / Loss සූත්‍රය
    gross_profit = total_cash_sales - total_item_cost
    net_profit_loss = gross_profit - (total_ads + total_other_expenses)
    
    # HTML එකට යවන්න Dictionary විදියට Format කිරීම
    orders = [{'id': r[0], 'sale_date': r[1], 'customer_name': r[2], 'total': r[3], 'cost_price': r[4]} for r in orders_raw]
    
    # Excel Download කිරීමට ඉල්ලීමක් ආවොත්
    if request.args.get('download') == 'excel':
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Profit Loss Report')
        
        ws.write(0, 0, "Profit / Loss Report Summary")
        ws.write(1, 0, f"Period: {start_date} to {end_date}")
        ws.write(3, 0, "Total Cash Sales"); ws.write(3, 1, total_cash_sales)
        ws.write(4, 0, "Total Item Cost"); ws.write(4, 1, total_item_cost)
        ws.write(5, 0, "Ad Expenses"); ws.write(5, 1, total_ads)
        ws.write(6, 0, "Other Expenses"); ws.write(6, 1, total_other_expenses)
        ws.write(7, 0, "Net Profit/Loss"); ws.write(7, 1, net_profit_loss)
        
        ws.write(9, 0, "Order ID"); ws.write(9, 1, "Date"); ws.write(9, 2, "Customer"); ws.write(9, 3, "Sale Amount"); ws.write(9, 4, "Cost")
        for i, row in enumerate(orders, start=10):
            ws.write(i, 0, row['id'])
            ws.write(i, 1, row['sale_date'])
            ws.write(i, 2, row['customer_name'])
            ws.write(i, 3, row['total'])
            ws.write(i, 4, row['cost_price'])
            
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, download_name="Profit_Loss_Report.xls", as_attachment=True)

    conn.close()
    
    return render_template('reports_profit_loss.html', 
                           items=items, start_date=start_date, end_date=end_date, selected_item=selected_item,
                           total_cash_sales=total_cash_sales, total_item_cost=total_item_cost,
                           total_ads=total_ads, total_other_expenses=total_other_expenses,
                           net_profit_loss=net_profit_loss, orders=orders)

@app.route('/reports/deleted_sales', methods=['GET', 'POST'])
def reports_deleted_sales():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()

    start_date = request.form.get('start_date', date.today().strftime('%Y-%m-01')) if request.method == 'POST' else request.args.get('start_date', date.today().strftime('%Y-%m-01'))
    end_date = request.form.get('end_date', date.today().strftime('%Y-%m-%d')) if request.method == 'POST' else request.args.get('end_date', date.today().strftime('%Y-%m-%d'))
    selected_item = request.form.get('item_id', 'all') if request.method == 'POST' else request.args.get('item_id', 'all')

    query = "SELECT d.id, d.barcode, d.customer_name, i.item_name, d.qty, d.selling_price, d.total, d.sale_date, d.deleted_date FROM deleted_sales d JOIN items i ON d.item_id = i.id WHERE d.deleted_date BETWEEN ? AND ?"
    params = [start_date, end_date]

    if selected_item != 'all':
        query += " AND d.item_id = ?"
        params.append(selected_item)

    query += " ORDER BY d.deleted_date DESC, d.id DESC"

    cursor.execute(query, params)
    deleted_orders = cursor.fetchall()

    # Excel Download
    if request.args.get('download') == 'excel':
        import pandas as pd
        columns = ['Deleted ID', 'Barcode', 'Customer Name', 'Item Name', 'Qty', 'Unit Price', 'Total', 'Sale Date', 'Deleted Date']
        df = pd.DataFrame(deleted_orders, columns=columns)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return send_file(output, download_name=f"Deleted_Bills_{start_date}_to_{end_date}.xlsx", as_attachment=True)

    conn.close()
    return render_template('reports_deleted_sales.html', items=items, start_date=start_date, end_date=end_date, selected_item=selected_item, deleted_orders=deleted_orders)

# ==========================================
# Stock Statement / Item Ledger (Bank Statement Style)
# ==========================================

@app.route('/reports/stock_statement')
def stock_statement():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied!"

    start_date = request.args.get('start_date', get_sl_today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', get_sl_today().strftime('%Y-%m-%d'))
    item_id = request.args.get('item_id', '')

    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()

    cursor.execute("SELECT id, item_name FROM items ORDER BY item_name ASC")
    items = cursor.fetchall()

    statement_data = []
    opening_balance = 0
    closing_balance = 0
    item_name = ""

    if item_id:
        cursor.execute("SELECT item_name FROM items WHERE id=?", (item_id,))
        item_row = cursor.fetchone()
        
        if item_row:
            item_name = item_row[0]
            all_tx = [] 

            # 1. Purchases (Stock Batches වලින් භාණ්ඩ එකතු වීම - 'Manual' ඒවා පමණි)
            # 🎯 අලුත් වෙනස: 'Manual' ඒව විතරක් ගන්නවා. එතකොට රිටන් බැච් ඩබල් වෙන්නේ නෑ.
            cursor.execute("SELECT id, stock_date, qty FROM stock_batches WHERE item_id=? AND (source = 'Manual' OR source IS NULL)", (item_id,))
            for row in cursor.fetchall():
                t_date = row[1]
                t_qty = row[2]
                all_tx.append({'date': t_date, 'type': 'Stock Purchase', 'in_qty': t_qty, 'out_qty': 0, 'ref': f"Batch #B{row[0]}"})

            # 2. Sales (sales ටේබල් එකෙන් විකිණීම් නිසා ස්ටොක් අඩු වීම)
            cursor.execute("SELECT id, sale_date, qty FROM sales WHERE item_id=?", (item_id,))
            for row in cursor.fetchall():
                t_date = row[1]
                t_qty = row[2]
                all_tx.append({'date': t_date, 'type': 'Sale (Out)', 'in_qty': 0, 'out_qty': t_qty, 'ref': f"Sale #{row[0]}"})

            # 3. Returns (returns ටේබල් එකෙන් නැවත ස්ටොක් එකට එකතු වීම)
            cursor.execute("SELECT id, return_date, qty FROM returns WHERE item_id=?", (item_id,))
            for row in cursor.fetchall():
                t_date = row[1]
                t_qty = row[2]
                all_tx.append({'date': t_date, 'type': 'Customer Return', 'in_qty': t_qty, 'out_qty': 0, 'ref': f"Return #{row[0]}"})

            # දිනය අනුව අනුපිළිවෙලට පෙළගැස්වීම
            all_tx.sort(key=lambda x: x['date'])

            # 🎯 Opening Balance එක ගණනය කිරීම
            running_balance = 0
            for tx in all_tx:
                if tx['date'] < start_date:
                    running_balance += tx['in_qty']
                    running_balance -= tx['out_qty']
                else:
                    break
            
            opening_balance = running_balance

            # 🎯 Statement එක ගොඩනැගීම (start_date සහ end_date අතර)
            running_balance = opening_balance 
            for tx in all_tx:
                if start_date <= tx['date'] <= end_date:
                    running_balance += tx['in_qty']
                    running_balance -= tx['out_qty']
                    tx['balance'] = running_balance
                    statement_data.append(tx)
            
            closing_balance = running_balance

    conn.close()

    return render_template('reports_stock_statement.html',
                           items=items,
                           selected_item=int(item_id) if item_id else '',
                           item_name=item_name,
                           start_date=start_date,
                           end_date=end_date,
                           statement_data=statement_data,
                           opening_balance=opening_balance,
                           closing_balance=closing_balance)

    return render_template('reports_stock_statement.html',
                           items=items,
                           selected_item=int(item_id) if item_id else '',
                           item_name=item_name,
                           start_date=start_date,
                           end_date=end_date,
                           statement_data=statement_data,
                           opening_balance=opening_balance,
                           closing_balance=closing_balance)

# ==========================================
#          META LEADS CRM SYSTEM
# ==========================================
@app.route('/leads')
def leads():
    if 'username' not in session: return redirect(url_for('login'))
    
    start_date = request.args.get('start_date', get_sl_today().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', get_sl_today().strftime('%Y-%m-%d'))
    
    status_filters = request.args.getlist('status')
    if not status_filters: status_filters = ['All']
        
    product_filters = request.args.getlist('product_name')
    if not product_filters: product_filters = ['All']
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    try: cursor.execute("ALTER TABLE leads ADD COLUMN selling_price REAL DEFAULT 0")
    except: pass
    
    cursor.execute("SELECT item_name FROM items ORDER BY item_name ASC")
    items_list = [row[0] for row in cursor.fetchall()]
    
    # ==========================================
    # 🎯 අලුත්: Confirmed Percentage ගණනය කිරීම
    # ==========================================
    stat_query = "SELECT status, COUNT(id) FROM leads WHERE upload_date BETWEEN ? AND ?"
    stat_params = [start_date, end_date]
    
    # Product filter එක විතරක් percentage එකට බලපානවා (Status filter එක නොසලකා හරිමු, 
    # එතකොට තමයි අදාල දවසේ/product එකේ 'සම්පූර්ණ' ප්‍රතිශතය පෙන්වන්නේ)
    if 'All' not in product_filters:
        placeholders = ','.join('?' for _ in product_filters)
        stat_query += f" AND product_name IN ({placeholders})"
        stat_params.extend(product_filters)
        
    stat_query += " GROUP BY status"
    cursor.execute(stat_query, stat_params)
    stat_results = cursor.fetchall()
    
    total_leads_count = 0
    confirmed_count = 0
    
    for row in stat_results:
        status_name = row[0]
        count = row[1]
        total_leads_count += count
        # මෙතන 'Call Back (Confirmed)' වගේ අනිත් ඒවාත් ඕන නම් add කරන්න පුළුවන්. 
        # දැනට 'Confirmed' විතරක් අරන් තියෙනවා.
        if status_name == 'Confirmed':
            confirmed_count += count
            
    confirmed_percentage = round((confirmed_count / total_leads_count * 100), 1) if total_leads_count > 0 else 0
    other_count = total_leads_count - confirmed_count
    # ==========================================

    # Main Data Query
    query = "SELECT id, upload_date, created_time, product_name, customer_name, phone, phone2, address, size, status, remarks, selling_price FROM leads WHERE upload_date BETWEEN ? AND ?"
    params = [start_date, end_date]
    
    if 'All' not in status_filters:
        placeholders = ','.join('?' for _ in status_filters)
        query += f" AND status IN ({placeholders})"
        params.extend(status_filters)
        
    if 'All' not in product_filters:
        placeholders = ','.join('?' for _ in product_filters)
        query += f" AND product_name IN ({placeholders})"
        params.extend(product_filters)
        
    query += " ORDER BY id DESC"
    cursor.execute(query, params)
    all_leads = cursor.fetchall()
    
    if request.args.get('download') == 'excel':
        import pandas as pd
        import io
        
        download_data = []
        for lead in all_leads:
            address_str = lead[7] if lead[7] else ""
            city_str = ""
            if ',' in address_str:
                city_str = address_str.split(',')[-1].strip()
            
            row = [lead[2], lead[4], lead[7], city_str, lead[5], lead[6], lead[8], lead[11], lead[10]]
            download_data.append(row)
            
        columns = ['Created Time', 'Customer Name', 'Address', 'City', 'Phone 1', 'Phone 2', 'Size', 'Price', 'Remarks']
        df = pd.DataFrame(download_data, columns=columns)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return send_file(output, download_name="Leads_Report.xlsx", as_attachment=True)
    
    conn.close()
    
    # 🎯 අලුතින් හදපු Stats ටික HTML එකට යවමු
    return render_template('leads.html', leads=all_leads, items_list=items_list, 
                           start_date=start_date, end_date=end_date, 
                           status_filters=status_filters, product_filters=product_filters,
                           total_leads_count=total_leads_count, confirmed_count=confirmed_count,
                           other_count=other_count, confirmed_percentage=confirmed_percentage)


@app.route('/upload_leads', methods=['POST'])
def upload_leads():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied! ඔබට මෙම පහසුකම භාවිතා කළ නොහැක."
    
    product_name = request.form.get('product_name')
    file = request.files.get('file')
    
    if file:
        import pandas as pd
        df = pd.read_excel(file)
        
        df.columns = df.columns.str.lower().str.strip()
        
        name_col = next((c for c in df.columns if 'name' in c), None)
        address_col = next((c for c in df.columns if 'address' in c or 'city' in c), None)
        created_time_col = next((c for c in df.columns if 'created' in c or 'time' in c), None)
        size_col = next((c for c in df.columns if 'size' in c), None)
        price_col = next((c for c in df.columns if 'price' in c or 'amount' in c or 'total' in c), None)
        
        phone_cols = [c for c in df.columns if 'phone' in c or 'number' in c]
        phone_col = phone_cols[0] if len(phone_cols) > 0 else None
        phone2_col = phone_cols[1] if len(phone_cols) > 1 else None
        
        conn = sqlite3.connect('/var/data/database.db')
        cursor = conn.cursor()
        
        try: cursor.execute("ALTER TABLE leads ADD COLUMN selling_price REAL DEFAULT 0")
        except: pass
        
        today = get_sl_today().strftime('%Y-%m-%d')
        
        # 1. සිස්ටම් එකේ ඇති සාමාන්‍ය නම්බර්ස් (Duplicate පරීක්ෂා කිරීමට)
        cursor.execute("SELECT phone, phone2 FROM leads WHERE status != 'Fake Order'")
        normal_phones = set()
        for row in cursor.fetchall():
            if row[0]: normal_phones.add(row[0])
            if row[1]: normal_phones.add(row[1])
            
        # 2. සිස්ටම් එකේ ඇති Fake Order නම්බර්ස්
        cursor.execute("SELECT phone, phone2 FROM leads WHERE status = 'Fake Order'")
        fake_phones = set()
        for row in cursor.fetchall():
            if row[0]: fake_phones.add(row[0])
            if row[1]: fake_phones.add(row[1])
            
        # 3. මේ දැන් අප්ලෝඩ් කරන Excel එක ඇතුලේ තියෙන නම්බර්ස්
        current_upload_phones = set()
        
        for index, row in df.iterrows():
            raw_name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else ''
            name = " ".join(raw_name.split()).title()
            
            raw_address = str(row[address_col]).strip() if address_col and pd.notna(row[address_col]) else ''
            address = " ".join(raw_address.split()).title()
            
            created_time = str(row[created_time_col]).strip() if created_time_col and pd.notna(row[created_time_col]) else ''
            size = str(row[size_col]).strip() if size_col and pd.notna(row[size_col]) else ''
            
            row_price = 0.0
            if price_col and pd.notna(row[price_col]):
                try:
                    price_val = str(row[price_col]).replace(',', '').strip()
                    row_price = float(price_val)
                except ValueError:
                    row_price = 0.0
            
            phone = str(row[phone_col]).strip() if phone_col and pd.notna(row[phone_col]) else ''
            if phone.endswith('.0'): phone = phone[:-2]
            
            phone2 = str(row[phone2_col]).strip() if phone2_col and pd.notna(row[phone2_col]) else ''
            if phone2.endswith('.0'): phone2 = phone2[:-2]
            
            if phone:
                # 🎯 එකම Excel එක ඇතුලෙම එකම නම්බර් එක දෙපාරක් තිබ්බොත් දෙවැනි එක අයින් කිරීම
                if phone in current_upload_phones:
                    continue
                    
                lead_status = 'Pending'
                remarks = ''
                
                # 🎯 ෆේක් නම්බර් එකක් නම්
                if phone in fake_phones or (phone2 and phone2 in fake_phones):
                    lead_status = 'Fake Order'
                    remarks = '⚠️ Warning: Fake Order'
                
                # 🎯 පරණ කස්ටමර් කෙනෙක් නම් (Duplicate) අයින් කරන්නේ නෑ, Status එක Duplicate කියලා දානවා
                elif phone in normal_phones or (phone2 and phone2 in normal_phones):
                    lead_status = 'Duplicate'
                    remarks = '🔄 Returning Customer (Duplicate)'
                
                # දත්ත ගොනුවට ඇතුළත් කිරීම
                cursor.execute("""
                    INSERT INTO leads 
                    (upload_date, created_time, product_name, customer_name, phone, phone2, address, size, status, remarks, selling_price) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (today, created_time, product_name, name, phone, phone2, address, size, lead_status, remarks, row_price))
                
                current_upload_phones.add(phone)
                
        conn.commit()
        conn.close()
        
    return redirect(url_for('leads'))


# --- Lead එකක් Update කිරීම (Filters මතක තබා ගනී) ---
# --- Lead එකක් සහ එහි මිල (Price) Update කිරීමේ කොටස ---
@app.route('/edit_lead', methods=['POST'])
def edit_lead():
    if 'username' not in session: return redirect(url_for('login'))
    
    lead_id = request.form['lead_id']
    customer_name = request.form['customer_name']
    address = request.form['address']
    phone1 = request.form['phone1']
    phone2 = request.form['phone2']
    size = request.form['size']
    new_status = request.form['status']
    remarks = request.form['remarks']
    selling_price_str = request.form.get('selling_price', '0').strip()
    selling_price = float(selling_price_str) if selling_price_str else 0.0
    
    current_start_date = request.form.get('current_start_date')
    current_end_date = request.form.get('current_end_date')
    
    # 🎯 අලුත්: Modal එකෙන් එන Multi-Filters ලබාගැනීම
    current_product_filters = request.form.getlist('current_product_filter')
    current_status_filters = request.form.getlist('current_status_filter')
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute('''UPDATE leads SET 
                      customer_name=?, address=?, phone=?, phone2=?, size=?, status=?, remarks=?, selling_price=? 
                      WHERE id=?''', 
                   (customer_name, address, phone1, phone2, size, new_status, remarks, selling_price, lead_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('leads', start_date=current_start_date, end_date=current_end_date, product_name=current_product_filters, status=current_status_filters))

# --- Admin සඳහා පමණක් Lead එකක් මකා දැමීම (Filters මතක තබා ගනී) ---
@app.route('/delete_lead/<int:lead_id>')
def delete_lead(lead_id):
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') != 'admin': return "Access Denied!"
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    product_filters = request.args.getlist('product_name')
    status_filters = request.args.getlist('status')
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('leads', start_date=start_date, end_date=end_date, product_name=product_filters, status=status_filters))              

# ==========================================
# Print Bills Section (Postal & Courier)
# ==========================================

@app.route('/print_bills')
def print_bills():
    if 'username' not in session: return redirect(url_for('login'))
    
    # 🎯 අලුත්: Date Filters ලබාගැනීම (Default විදිහට මේ මාසේ මුල ඉඳන් අද වෙනකම්)
    start_date = request.args.get('start_date', get_sl_today().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', get_sl_today().strftime('%Y-%m-%d'))
    product_filter = request.args.get('product_name', 'All')
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT item_name FROM items ORDER BY item_name ASC")
    items_list = [row[0] for row in cursor.fetchall()]
    
    # Date සහ Product එක අනුව Confirmed Orders ගැනීම
    query = "SELECT id, upload_date, product_name, customer_name, phone, phone2, address, size, selling_price FROM leads WHERE status='Confirmed' AND upload_date BETWEEN ? AND ?"
    params = [start_date, end_date]
    
    if product_filter != 'All':
        query += " AND product_name=?"
        params.append(product_filter)
        
    query += " ORDER BY id DESC"
    
    cursor.execute(query, params)
    confirmed_leads = cursor.fetchall()
    conn.close()
    
    return render_template('print_bills.html', leads=confirmed_leads, items_list=items_list, product_filter=product_filter, start_date=start_date, end_date=end_date)

# === DOMEX COURIER CREDENTIALS ===
DOMEX_API_KEY = "cgU70rMwYDvX9dYjdJfwH8XR68kvJJ1o" 
DOMEX_BASE_URL = "https://www.connectmesecure.com/api/CustomerInwards"

@app.route('/generate_domex_bills', methods=['POST'])
def generate_domex_bills():
    if 'username' not in session: return redirect(url_for('login'))
    
    selected_ids = request.form.getlist('selected_leads')
    sender_type = request.form.get('sender')
    
    if not selected_ids:
        return "කිසිදු Order එකක් තෝරාගෙන නැත! කරුණාකර ආපසු ගොස් Orders තෝරන්න."

    # 🎯 වෙනස 1: Button එක අනුව Barcode Prefix එක සහ Base Number එක වෙන් කිරීම
    if sender_type == 'YLS':
        domex_cust_code = 'B00506'
        sender_name = f'YOUR LOVING STORE ({domex_cust_code})'
        sender_address = 'MOLAGODA, KEGALLE.'
        sender_phone = '0767115299'
        barcode_prefix = "LS"
        base_num = 2850 # YLS සඳහා පටන් ගන්නා අංකය (මෙතනින් +1 වී 2851 වේ)
    else:
        domex_cust_code = 'C0034'
        sender_name = f'UNIQUE PRODUCTS ({domex_cust_code})' 
        sender_address = 'MOLAGODA, KEGALLE.'
        sender_phone = '0789909808'
        barcode_prefix = "UP"
        base_num = 4884 # UP සඳහා පටන් ගන්නා අංකය (මෙතනින් +1 වී 4885 වේ)

    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # 🎯 වෙනස 2: අදාල Prefix එක (LS හෝ UP) තියෙන ඒවා පමණක් Database එකෙන් සෙවීම
    cursor.execute("SELECT tracking_no FROM leads WHERE tracking_no LIKE ?", (f"{barcode_prefix}%",))
    rows = cursor.fetchall()
    
    last_num = base_num 
    for r in rows:
        t_no = r[0]
        if t_no and t_no.startswith(barcode_prefix):
            try:
                # මුල් අකුරු 2 (LS හෝ UP) අයින් කරලා ඉලක්කම ගන්නවා
                num = int(t_no[2:])
                if num > last_num:
                    last_num = num
            except:
                pass

    placeholders = ','.join('?' for _ in selected_ids)
    cursor.execute(f"SELECT id, product_name, customer_name, phone, phone2, address, size, selling_price, tracking_no FROM leads WHERE id IN ({placeholders})", selected_ids)
    leads = cursor.fetchall()
    
    headers = {
        'x-api-key': DOMEX_API_KEY,
        'Content-Type': 'application/json'
    }
    
    success_bills = []
    api_errors = []
    
    for lead in leads:
        lead_id, product_name, customer_name, phone, phone2, address, size, selling_price, old_tracking_no = lead
        
        city = address.split(',')[-1].strip() if ',' in address else address.strip()
        if not city: city = "Kegalle"
        
        charge = float(selling_price) if selling_price else 0.0
        if charge <= 0: charge = 1.0 
        
        # 🎯 වෙනස 3: අදාල Prefix එක (LS හෝ UP) එක්ක අලුත් බාකෝඩ් එක ජෙනරේට් කිරීම
        if not old_tracking_no or not str(old_tracking_no).startswith(barcode_prefix):
            last_num += 1
            new_tracking_no = f"{barcode_prefix}{str(last_num).zfill(9)}"
        else:
            new_tracking_no = old_tracking_no
            
        payload = {
            "trackingNo": new_tracking_no,
            "paymentMethod": "Cash",
            "itemType": "PCKG",
            "customerCode": domex_cust_code,
            "senderName": sender_name[:250],
            "senderAddress": sender_address[:250],
            "senderContactNo": sender_phone[:15],
            "receiverName": customer_name[:350] if customer_name else "Customer",
            "receiverAddress": address[:350] if address else "No Address",
            "receiverCity": city[:250],
            "receiverContactNo1": phone[:250] if phone else "0000000000",
            "receiverContactNo2": phone2[:250] if phone2 else "",
            "packageDesc": f"{product_name} x 1 | URGENT"[:250],
            "weight": 0.3,
            "createdUser": session['username'][:250],
            "totalCharges": charge,
            "noOfPcs": 1
        }
        
        try:
            response = requests.post(f"{DOMEX_BASE_URL}/setCustomerDataEntry", json=payload, headers=headers)
            
            print(f"\n🚀 === DOMEX API TEST (Order #{lead_id}) ===")
            print(f"Account: {sender_type} | Customer Code: {domex_cust_code}")
            print(f"Tracking No: {new_tracking_no}")
            print(f"Domex Status Code: {response.status_code}")
            print(f"Domex Reply Body: {response.text}")
            print("==========================================\n")

            if response.status_code == 200:
                res_data = response.json()
                
                if res_data.get('errorCode') == 200: 
                    cursor.execute("UPDATE leads SET tracking_no=?, courier='Domex' WHERE id=?", (new_tracking_no, lead_id))
                    success_bills.append({
                        'tracking_no': new_tracking_no,
                        'customer_name': customer_name,
                        'address': address,
                        'city': city,
                        'phone': phone,
                        'phone2': phone2,
                        'product_name': product_name,
                        'selling_price': selling_price,
                        'sender_name': sender_name,
                        'sender_address': sender_address,
                        'sender_phone': sender_phone,
                        'date': get_sl_today().strftime('%m/%d/%Y, %I:%M:%S %p')
                    })
                
                elif res_data.get('errorCode') == 218:
                    cursor.execute("UPDATE leads SET tracking_no=NULL, courier=NULL WHERE id=?", (lead_id,))
                    api_errors.append(f"Order #{lead_id} ෆේල් වුණා: {new_tracking_no} Barcode එක දැනටමත් Domex එකේ තියෙනවා! අපි ඒක Reset කළා, ආයෙත් මේ Order එක තෝරලා යවන්න.")
                
                else:
                    api_errors.append(f"Order #{lead_id} API Error: {res_data.get('message', 'Unknown Error')}")
            
            elif response.status_code == 400:
                res_data = response.json()
                err_msg = ""
                if 'errors' in res_data:
                    for field, msgs in res_data['errors'].items():
                        err_msg += f"{field}: {', '.join(msgs)} | "
                api_errors.append(f"Order #{lead_id} රිජෙක්ට් වුණා: {err_msg} (Barcode: {new_tracking_no})")
            
            else:
                api_errors.append(f"Order #{lead_id} Server Error: {response.status_code}")
                
        except Exception as e:
            api_errors.append(f"Order #{lead_id} Failed to connect API: {str(e)}")
            
    conn.commit()
    conn.close()
    
    return render_template('domex_print_layout.html', bills=success_bills, api_errors=api_errors)

@app.route('/generate_postal_bills', methods=['POST'])
def generate_postal_bills():
    if 'username' not in session: return redirect(url_for('login'))
    
    selected_ids = request.form.getlist('selected_leads')
    # 🎯 අලුත්: එබූ බොත්තම (YLS ද UP ද) හඳුනාගැනීම
    sender_type = request.form.get('sender')
    
    if not selected_ids:
        return "කිසිදු Order එකක් තෝරාගෙන නැත! කරුණාකර ආපසු ගොස් Orders තෝරන්න."

    # 🎯 අලුත්: Sender ගේ විස්තර වෙන් කිරීම
    if sender_type == 'YLS':
        sender_info = {
            'name': 'Your Loving Store,',
            'add1': 'Mangalagama,',
            'add2': 'Molagoda.',
            'phone': '0767115299'
        }
    else:
        sender_info = {
            'name': 'Unique Products,',
            'add1': 'Mangalagama,',
            'add2': 'Molagoda.',
            'phone': '0789909808'
        }

    placeholders = ','.join('?' for _ in selected_ids)
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    query = f"SELECT id, product_name, customer_name, phone, phone2, address, size, selling_price FROM leads WHERE id IN ({placeholders}) ORDER BY product_name ASC, id ASC"
    cursor.execute(query, selected_ids)
    selected_leads = cursor.fetchall()
    conn.close()

    bills_data = []
    product_counters = {}

    for lead in selected_leads:
        lead_id, product_name, customer_name, phone, phone2, address, size, selling_price = lead
        
        if product_name not in product_counters:
            product_counters[product_name] = 1
        else:
            product_counters[product_name] += 1
            
        order_num = product_counters[product_name]
        
        bills_data.append({
            'order_num': order_num,
            'product_name': product_name,
            'customer_name': customer_name,
            'phone': phone,
            'phone2': phone2,
            'address': address,
            'size': size,
            'selling_price': selling_price
        })

    # sender_info එක HTML එකට යැවීම
    return render_template('postal_print_layout.html', bills=bills_data, sender=sender_info)


# ==========================================
# Post Office Excel Generation
# ==========================================

@app.route('/generate_post_excel', methods=['POST'])
def generate_post_excel():
    if 'username' not in session: return redirect(url_for('login'))
    
    selected_ids = request.form.getlist('selected_leads')
    sender_type = request.form.get('sender')
    
    if not selected_ids:
        return "කිසිදු Order එකක් තෝරාගෙන නැත! කරුණාකර ආපසු ගොස් Orders තෝරන්න."

    # Column C සඳහා Sender විස්තර සහ Column G සඳහා බර
    if sender_type == 'YLS':
        sender_str = "Indika Sandakelum,Mangalagama,Molagoda, Kegalle 767115299"
        weight = 250
    else:
        sender_str = "Vimukthi Chathuranga,Mangalagama,Molagoda, Kegalle 789909808"
        weight = 175

    placeholders = ','.join('?' for _ in selected_ids)
    
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    query = f"SELECT id, product_name, customer_name, phone, phone2, address, size, selling_price FROM leads WHERE id IN ({placeholders}) ORDER BY product_name ASC, id ASC"
    cursor.execute(query, selected_ids)
    selected_leads = cursor.fetchall()
    conn.close()

    excel_data = []
    
    # Column A සඳහා අද දිනය ලබා ගැනීම
    today_str = get_sl_today().strftime('%Y-%m-%d')
    
    for index, lead in enumerate(selected_leads, start=1):
        customer_name = lead[2]
        phone = lead[3]
        phone2 = lead[4]
        address = lead[5]
        selling_price = lead[7]
        
        # Column E සඳහා City එක වෙන් කර ගැනීම
        city_str = ""
        if ',' in address:
            city_str = address.split(',')[-1].strip()
        else:
            city_str = address.strip()
        
        # Column D සඳහා Receiver විස්තර සෑදීම
        phone_str = phone
        if phone2: phone_str += f"/{phone2}"
        receiver_str = f"{customer_name}/{address}/{phone_str}"
        
        # අලුත් Excel Format එකට අනුව පේළිය (Row) සැකසීම
        row = [
            today_str,       # Column A - Date
            index,           # Column B - Number (1, 2, 3...)
            sender_str,      # Column C - Sender Details
            receiver_str,    # Column D - Receiver Details
            city_str,        # Column E - City
            selling_price,   # Column F - Total Amount
            weight,          # Column G - Weight (250 or 175)
            ""               # Column H - Empty
        ]
        excel_data.append(row)
        
    # Excel එකේ උඩින්ම වැටෙන Headers ටික
    columns = [
        'Date',                                                         # A
        'NO (Start From 1) Write this number on the Parcel',            # B
        'Sender',                                                       # C
        'Receiver',                                                     # D
        'Postal City',                                                  # E
        'Pay Back Value (For COD)',                                     # F
        'Weight in grams',                                              # G
        'Barcode'                                                       # H
    ]
    
    import pandas as pd
    import io
    
    df = pd.DataFrame(excel_data, columns=columns)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    
    filename = f"PostOffice_{sender_type}_{today_str}.xlsx"
    return send_file(output, download_name=filename, as_attachment=True)

@app.route('/api/search')
def global_search():
    if 'username' not in session: return jsonify([])
    
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2: return jsonify([]) # අකුරු 2කට වඩා ගැහුවම තමයි Search වෙන්නේ
        
    like_q = f"%{q}%"
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    results = []
    
    # 1. Sales වගුවෙන් සෙවීම (Barcode, Name, Phone)
    cursor.execute('''
        SELECT s.barcode, s.customer_name, s.customer_phone, i.item_name, s.sale_date, s.status, s.total 
        FROM sales s 
        JOIN items i ON s.item_id = i.id 
        WHERE s.barcode LIKE ? OR s.customer_name LIKE ? OR s.customer_phone LIKE ?
        ORDER BY s.sale_date DESC LIMIT 5
    ''', (like_q, like_q, like_q))
    
    for row in cursor.fetchall():
        results.append({
            'type': 'Manual Sale',
            'id': row[0],
            'name': row[1] or '-',
            'phone': row[2] or '-',
            'address': 'N/A', # Manual Sales වල Address සේව් වෙන්නේ නෑ
            'item': row[3],
            'date': row[4],
            'status': row[5],
            'price': row[6]
        })
        
    # 2. Leads වගුවෙන් සෙවීම (Name, Phone, Phone2, Address)
    cursor.execute('''
        SELECT id, customer_name, phone, phone2, address, product_name, upload_date, status, selling_price 
        FROM leads 
        WHERE customer_name LIKE ? OR phone LIKE ? OR phone2 LIKE ? OR address LIKE ?
        ORDER BY id DESC LIMIT 5
    ''', (like_q, like_q, like_q, like_q))
    
    for row in cursor.fetchall():
        phone_str = str(row[2]) if row[2] else ''
        if row[3]: phone_str += f" / {row[3]}"
        
        results.append({
            'type': 'Meta Lead',
            'id': f"L-{row[0]}",
            'name': row[1] or '-',
            'phone': phone_str,
            'address': row[4] or '-',
            'item': row[5],
            'date': row[6],
            'status': row[7],
            'price': row[8]
        })
        
    conn.close()
    return jsonify(results)

    # ==========================================
# 🚀 PWA (Progressive Web App) Config
# ==========================================
@app.route('/manifest.json')
def manifest():
    manifest_data = {
        "name": "Your Loving Store CRM",
        "short_name": "YLS CRM",
        "start_url": "/dashboard",
        "display": "standalone",
        "background_color": "#1e293b",
        "theme_color": "#1e293b",
        "icons": [
            {
                "src": "/static/logo.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/logo.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return jsonify(manifest_data)

@app.route('/sw.js')
def service_worker():
    sw_js = """
    self.addEventListener('install', (e) => {
        console.log('[Service Worker] Installed Successfully');
    });
    self.addEventListener('fetch', (e) => {
        e.respondWith(fetch(e.request));
    });
    """
    return app.response_class(sw_js, mimetype='application/javascript')

@app.route('/personal', methods=['GET', 'POST'])
def personal_expenses():
    # 'madusanka_personal' කියන අලුත් යූසර්ට විතරක් මේකට එන්න පුළුවන්
    if 'username' not in session or session.get('username') != 'madusanka_personal':
        return "Access Denied! 🚫 මෙම පිටුව බැලීමට ඔබට අවසර නැත."
        
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    
    # Date Filters (පෙරනිමියෙන් මේ මාසයේ මුල සිට අද දක්වා)
    today = date.today()
    start_date = request.args.get('start_date', today.replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', today.strftime('%Y-%m-%d'))
    
    if request.method == 'POST':
        e_date = request.form['expense_date']
        category = request.form['category']
        desc = request.form['description']
        amount = float(request.form['amount'])
        
        cursor.execute("INSERT INTO personal_expenses (expense_date, category, description, amount) VALUES (?, ?, ?, ?)", 
                       (e_date, category, desc, amount))
        conn.commit()
        return redirect(url_for('personal_expenses', start_date=start_date, end_date=end_date))
        
    # දත්ත ලබා ගැනීම
    cursor.execute("SELECT id, expense_date, category, description, amount FROM personal_expenses WHERE expense_date BETWEEN ? AND ? ORDER BY expense_date DESC, id DESC", (start_date, end_date))
    expenses = cursor.fetchall()
    
    total_amount = sum([row[4] for row in expenses])
    
    # Chart එක සඳහා දත්ත (Category අනුව වියදම් වෙන් කිරීම)
    cursor.execute("SELECT category, SUM(amount) FROM personal_expenses WHERE expense_date BETWEEN ? AND ? GROUP BY category", (start_date, end_date))
    chart_data_raw = cursor.fetchall()
    chart_labels = [row[0] for row in chart_data_raw]
    chart_values = [row[1] for row in chart_data_raw]
    
    conn.close()
    
    return render_template('personal_expenses.html', expenses=expenses, total_amount=total_amount, 
                           start_date=start_date, end_date=end_date, 
                           chart_labels=chart_labels, chart_values=chart_values)

@app.route('/delete_personal_expense/<int:exp_id>')
def delete_personal_expense(exp_id):
    if 'username' not in session or session.get('username') != 'madusanka_personal':
        return redirect(url_for('login'))
    conn = sqlite3.connect('/var/data/database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personal_expenses WHERE id=?", (exp_id,))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('personal_expenses'))

if __name__ == '__main__':
    app.run(debug=True)
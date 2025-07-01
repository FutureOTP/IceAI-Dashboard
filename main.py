import os
import json
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, session, redirect, url_for, request, jsonify, flash
from flask_cors import CORS
from dotenv import load_dotenv
import hashlib
import hmac
import sqlite3
from functools import wraps

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "iceai_ultra_secure_key_2024")

CORS(app)

# Discord OAuth2 Configuration
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET") 
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
DISCORD_API_BASE = "https://discord.com/api"
SELLHUB_SECRET = os.getenv("SELLHUB_SECRET", "")

# Database initialization
def init_db():
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id TEXT PRIMARY KEY, username TEXT, avatar TEXT, discriminator TEXT,
                  verified INTEGER DEFAULT 0, verification_code TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Vouches table (enhanced for R6 trading)
    c.execute('''CREATE TABLE IF NOT EXISTS vouches
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, target_user_id TEXT,
                  message TEXT, rating INTEGER, trade_type TEXT, account_rank TEXT,
                  price REAL, payment_method TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Tickets table
    c.execute('''CREATE TABLE IF NOT EXISTS tickets
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ticket_type TEXT,
                  status TEXT DEFAULT 'open', subject TEXT, description TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, closed_at TIMESTAMP)''')
    
    # Invites table
    c.execute('''CREATE TABLE IF NOT EXISTS invites
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, inviter_id TEXT, invited_id TEXT,
                  invite_code TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Giveaways table
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT,
                  prize TEXT, winners_count INTEGER, end_time TIMESTAMP,
                  channel_id TEXT, message_id TEXT, status TEXT DEFAULT 'active')''')
    
    # Moderation logs table
    c.execute('''CREATE TABLE IF NOT EXISTS mod_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, user_id TEXT,
                  moderator_id TEXT, reason TEXT, duration INTEGER,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Settings table
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Auto-responder table
    c.execute('''CREATE TABLE IF NOT EXISTS autoresponder
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_phrase TEXT,
                  response TEXT, embed_enabled INTEGER DEFAULT 0,
                  embed_data TEXT, enabled INTEGER DEFAULT 1)''')
    
    # Webhook logs table
    c.execute('''CREATE TABLE IF NOT EXISTS webhook_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, data TEXT,
                  processed INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # R6 Accounts table
    c.execute('''CREATE TABLE IF NOT EXISTS r6_accounts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id TEXT, title TEXT,
                  rank TEXT, level INTEGER, operators_count INTEGER, renown INTEGER,
                  r6_credits INTEGER, price REAL, description TEXT, status TEXT DEFAULT 'available',
                  images TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # R6 Market transactions
    c.execute('''CREATE TABLE IF NOT EXISTS r6_transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id TEXT, seller_id TEXT,
                  account_id INTEGER, price REAL, status TEXT DEFAULT 'pending',
                  payment_method TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                  completed_at TIMESTAMP)''')
    
    # R6 Scammer database
    c.execute('''CREATE TABLE IF NOT EXISTS scammer_reports
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, reported_user_id TEXT, reporter_id TEXT,
                  reason TEXT, evidence TEXT, discord_tag TEXT, status TEXT DEFAULT 'pending',
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # R6 Market alerts
    c.execute('''CREATE TABLE IF NOT EXISTS market_alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, alert_type TEXT,
                  max_price REAL, min_rank TEXT, operators_required TEXT,
                  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    conn.commit()
    conn.close()

# Authentication decorator
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/login")
def login():
    discord_auth_url = f"{DISCORD_API_BASE}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    return redirect(discord_auth_url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        flash("Authentication failed", "error")
        return redirect("/")

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code", 
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify guilds"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        # Get access token
        token_res = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
        if token_res.status_code != 200:
            flash("Failed to authenticate with Discord", "error")
            return redirect("/")

        access_token = token_res.json().get("access_token")

        # Get user info
        user_res = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"}
        )

        if user_res.status_code != 200:
            flash("Failed to fetch user info", "error")
            return redirect("/")

        user = user_res.json()
        
        # Store user in database
        conn = sqlite3.connect('iceai.db')
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO users (id, username, avatar, discriminator) VALUES (?, ?, ?, ?)",
                  (user["id"], user["username"], user["avatar"], user.get("discriminator", "0000")))
        conn.commit()
        conn.close()
        
        session["user"] = {
            "id": user["id"],
            "username": user["username"], 
            "avatar": user["avatar"],
            "discriminator": user.get("discriminator", "0000")
        }
        
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))
        
    except Exception as e:
        flash("An error occurred during authentication", "error")
        return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully", "info")
    return redirect("/")

@app.route("/dashboard")
@require_login
def dashboard():
    user = session.get("user")
    
    # Get stats from database
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    # Get R6 specific stats
    c.execute("SELECT COUNT(*) FROM r6_accounts WHERE seller_id = ?", (user["id"],))
    accounts_listed = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM r6_transactions WHERE buyer_id = ? OR seller_id = ?", (user["id"], user["id"]))
    total_trades = c.fetchone()[0]
    
    c.execute("SELECT SUM(price) FROM r6_transactions WHERE seller_id = ? AND status = 'completed'", (user["id"],))
    total_earnings = c.fetchone()[0] or 0
    
    c.execute("SELECT AVG(rating) FROM vouches WHERE target_user_id = ?", (user["id"],))
    avg_rating = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ?", (user["id"],))
    ticket_count = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM invites WHERE inviter_id = ?", (user["id"],))
    invite_count = c.fetchone()[0]
    
    conn.close()
    
    stats = {
        "vouches": vouch_count,
        "tickets": ticket_count, 
        "invites": invite_count,
        "accounts_listed": accounts_listed,
        "total_trades": total_trades,
        "total_earnings": total_earnings,
        "avg_rating": round(avg_rating, 1) if avg_rating else 0,
        "member_since": "2024"
    }
    
    return render_template("dashboard.html", user=user, stats=stats)

# Moderation Routes
@app.route("/moderation")
@require_login
def moderation():
    return render_template("moderation.html", user=session.get("user"))

@app.route("/api/moderation/settings", methods=["GET", "POST"])
@require_login
def moderation_settings():
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    if request.method == "POST":
        data = request.json
        for key, value in data.items():
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                     (f"mod_{key}", json.dumps(value)))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    # GET request - return current settings
    c.execute("SELECT key, value FROM settings WHERE key LIKE 'mod_%'")
    settings = {}
    for row in c.fetchall():
        key = row[0].replace("mod_", "")
        settings[key] = json.loads(row[1])
    
    conn.close()
    return jsonify(settings)

# Tickets Routes
@app.route("/tickets")
@require_login
def tickets():
    user = session.get("user")
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
    user_tickets = c.fetchall()
    conn.close()
    
    return render_template("tickets.html", user=user, tickets=user_tickets)

@app.route("/api/tickets/create", methods=["POST"])
@require_login
def create_ticket():
    data = request.json
    user = session.get("user")
    
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("INSERT INTO tickets (user_id, ticket_type, subject, description) VALUES (?, ?, ?, ?)",
              (user["id"], data["type"], data["subject"], data["description"]))
    ticket_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "ticket_id": ticket_id})

# Verification Routes
@app.route("/verification")
@require_login
def verification():
    return render_template("verification.html", user=session.get("user"))

@app.route("/api/verification/verify", methods=["POST"])
@require_login
def verify_user():
    user = session.get("user")
    verification_code = request.json.get("code")
    
    # Simple verification logic (in production, you'd have a more complex system)
    if verification_code == "VERIFY123":
        conn = sqlite3.connect('iceai.db')
        c = conn.cursor()
        c.execute("UPDATE users SET verified = 1 WHERE id = ?", (user["id"],))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Verification successful!"})
    
    return jsonify({"success": False, "message": "Invalid verification code"})

# Vouches Routes
@app.route("/vouches")
@require_login
def vouches():
    user = session.get("user")
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("SELECT * FROM vouches WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
    user_vouches = c.fetchall()
    conn.close()
    
    return render_template("vouches.html", user=user, vouches=user_vouches)

@app.route("/api/vouches/create", methods=["POST"])
@require_login
def create_vouch():
    data = request.json
    user = session.get("user")
    
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("""INSERT INTO vouches (user_id, target_user_id, message, rating, trade_type, account_rank, price, payment_method) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (user["id"], data["target"], data["message"], data["rating"], 
               data.get("trade_type", ""), data.get("account_rank", ""), 
               data.get("price", 0), data.get("payment_method", "")))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})

@app.route("/api/vouches/export")
@require_login
def export_vouches():
    user = session.get("user")
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("SELECT * FROM vouches WHERE user_id = ?", (user["id"],))
    vouches = c.fetchall()
    conn.close()
    
    # Convert to CSV format
    csv_data = "ID,Target User,Message,Rating,Trade Type,Account Rank,Price,Payment Method,Date\n"
    for vouch in vouches:
        csv_data += f"{vouch[0]},{vouch[2]},{vouch[3]},{vouch[4]},{vouch[5] or ''},{vouch[6] or ''},{vouch[7] or 0},{vouch[8] or ''},{vouch[9]}\n"
    
    response = app.response_class(
        response=csv_data,
        status=200,
        mimetype='text/csv'
    )
    response.headers["Content-Disposition"] = "attachment; filename=vouches.csv"
    return response

# Giveaways Routes
@app.route("/giveaways")
@require_login
def giveaways():
    return render_template("giveaways.html", user=session.get("user"))

@app.route("/api/giveaways/create", methods=["POST"])
@require_login
def create_giveaway():
    data = request.json
    
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("INSERT INTO giveaways (title, description, prize, winners_count, end_time, channel_id) VALUES (?, ?, ?, ?, ?, ?)",
              (data["title"], data["description"], data["prize"], data["winners"], 
               data["end_time"], data["channel"]))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})

# R6 Marketplace Routes
@app.route("/marketplace")
@require_login
def marketplace():
    return render_template("marketplace.html", user=session.get("user"))

@app.route("/api/marketplace/accounts", methods=["GET", "POST"])
@require_login
def marketplace_accounts():
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    if request.method == "POST":
        data = request.json
        user = session.get("user")
        c.execute("""INSERT INTO r6_accounts 
                     (seller_id, title, rank, level, operators_count, renown, r6_credits, price, description) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user["id"], data["title"], data["rank"], data["level"], 
                   data["operators"], data["renown"], data["credits"], data["price"], data["description"]))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    # GET request
    c.execute("SELECT * FROM r6_accounts WHERE status = 'available' ORDER BY created_at DESC")
    accounts = c.fetchall()
    conn.close()
    
    return jsonify([{
        "id": a[0], "title": a[2], "rank": a[3], "level": a[4],
        "operators": a[5], "renown": a[6], "credits": a[7], 
        "price": a[8], "description": a[9], "created_at": a[11]
    } for a in accounts])

# Auto-Responder Routes
@app.route("/autoresponder")
@require_login
def autoresponder():
    return render_template("autoresponder.html", user=session.get("user"))

@app.route("/api/autoresponder", methods=["GET", "POST"])
@require_login
def autoresponder_api():
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    if request.method == "POST":
        data = request.json
        c.execute("INSERT INTO autoresponder (trigger_phrase, response, embed_enabled, embed_data) VALUES (?, ?, ?, ?)",
                  (data["trigger"], data["response"], data.get("embed_enabled", 0), 
                   json.dumps(data.get("embed_data", {}))))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    # GET request
    c.execute("SELECT * FROM autoresponder WHERE enabled = 1")
    responses = c.fetchall()
    conn.close()
    
    return jsonify([{
        "id": r[0], "trigger": r[1], "response": r[2], 
        "embed_enabled": r[3], "embed_data": json.loads(r[4] or "{}")
    } for r in responses])

# Webhooks
@app.route("/webhook/sellhub", methods=["POST"])
def sellhub_webhook():
    signature = request.headers.get('X-Signature')
    if not signature or not SELLHUB_SECRET:
        return "Unauthorized", 401
    
    # Verify webhook signature
    expected_signature = hmac.new(
        SELLHUB_SECRET.encode(),
        request.data,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, expected_signature):
        return "Invalid signature", 401
    
    data = request.json
    
    # Log webhook data
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    c.execute("INSERT INTO webhook_logs (source, data) VALUES (?, ?)",
              ("sellhub", json.dumps(data)))
    conn.commit()
    conn.close()
    
    # Process the webhook (send to Discord, etc.)
    # This would integrate with your Discord bot
    
    return "OK", 200

# API Routes for Settings
@app.route("/api/settings/<category>", methods=["GET", "POST"])
@require_login
def settings_api(category):
    conn = sqlite3.connect('iceai.db')
    c = conn.cursor()
    
    if request.method == "POST":
        data = request.json
        for key, value in data.items():
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                     (f"{category}_{key}", json.dumps(value)))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    
    # GET request
    c.execute("SELECT key, value FROM settings WHERE key LIKE ?", (f"{category}_%",))
    settings = {}
    for row in c.fetchall():
        key = row[0].replace(f"{category}_", "")
        settings[key] = json.loads(row[1])
    
    conn.close()
    return jsonify(settings)

# Initialize database on startup
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
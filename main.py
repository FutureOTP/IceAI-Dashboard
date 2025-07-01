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
import secrets
import logging

# Load environment variables
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))

CORS(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Discord OAuth2 Configuration
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET") 
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
DISCORD_API_BASE = "https://discord.com/api"
SELLHUB_SECRET = os.getenv("SELLHUB_SECRET", "")

# Validate required environment variables
required_env_vars = ["DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DISCORD_REDIRECT_URI"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    logger.error(f"Missing required environment variables: {missing_vars}")
    raise ValueError(f"Missing required environment variables: {missing_vars}")

# Database initialization with error handling
def init_db():
    try:
        conn = sqlite3.connect('iceai.db')
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id TEXT PRIMARY KEY, username TEXT, avatar TEXT, discriminator TEXT,
                      verified INTEGER DEFAULT 0, verification_code TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Vouches table (enhanced for R6 trading)
        c.execute('''CREATE TABLE IF NOT EXISTS vouches
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, target_user_id TEXT,
                      message TEXT, rating INTEGER CHECK(rating >= 1 AND rating <= 5), 
                      trade_type TEXT, account_rank TEXT, price REAL CHECK(price >= 0), 
                      payment_method TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # Tickets table
        c.execute('''CREATE TABLE IF NOT EXISTS tickets
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, ticket_type TEXT,
                      status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'pending')), 
                      subject TEXT NOT NULL, description TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, closed_at TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # Invites table
        c.execute('''CREATE TABLE IF NOT EXISTS invites
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, inviter_id TEXT, invited_id TEXT,
                      invite_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(inviter_id) REFERENCES users(id))''')
        
        # Giveaways table
        c.execute('''CREATE TABLE IF NOT EXISTS giveaways
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT,
                      prize TEXT NOT NULL, winners_count INTEGER CHECK(winners_count > 0), 
                      end_time TIMESTAMP, channel_id TEXT, message_id TEXT, 
                      status TEXT DEFAULT 'active' CHECK(status IN ('active', 'ended', 'cancelled')))''')
        
        # Moderation logs table
        c.execute('''CREATE TABLE IF NOT EXISTS mod_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, user_id TEXT,
                      moderator_id TEXT, reason TEXT, duration INTEGER,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id),
                      FOREIGN KEY(moderator_id) REFERENCES users(id))''')
        
        # Settings table
        c.execute('''CREATE TABLE IF NOT EXISTS settings
                     (key TEXT PRIMARY KEY, value TEXT)''')
        
        # Auto-responder table
        c.execute('''CREATE TABLE IF NOT EXISTS autoresponder
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_phrase TEXT NOT NULL,
                      response TEXT NOT NULL, embed_enabled INTEGER DEFAULT 0,
                      embed_data TEXT, enabled INTEGER DEFAULT 1)''')
        
        # Webhook logs table
        c.execute('''CREATE TABLE IF NOT EXISTS webhook_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, data TEXT,
                      processed INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # R6 Accounts table
        c.execute('''CREATE TABLE IF NOT EXISTS r6_accounts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, seller_id TEXT, title TEXT NOT NULL,
                      rank TEXT, level INTEGER CHECK(level >= 0), operators_count INTEGER CHECK(operators_count >= 0), 
                      renown INTEGER CHECK(renown >= 0), r6_credits INTEGER CHECK(r6_credits >= 0), 
                      price REAL CHECK(price >= 0), description TEXT, 
                      status TEXT DEFAULT 'available' CHECK(status IN ('available', 'sold', 'pending')),
                      images TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(seller_id) REFERENCES users(id))''')
        
        # R6 Market transactions
        c.execute('''CREATE TABLE IF NOT EXISTS r6_transactions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, buyer_id TEXT, seller_id TEXT,
                      account_id INTEGER, price REAL CHECK(price >= 0), 
                      status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'completed', 'cancelled')),
                      payment_method TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      completed_at TIMESTAMP,
                      FOREIGN KEY(buyer_id) REFERENCES users(id),
                      FOREIGN KEY(seller_id) REFERENCES users(id),
                      FOREIGN KEY(account_id) REFERENCES r6_accounts(id))''')
        
        # R6 Scammer database
        c.execute('''CREATE TABLE IF NOT EXISTS scammer_reports
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, reported_user_id TEXT, reporter_id TEXT,
                      reason TEXT NOT NULL, evidence TEXT, discord_tag TEXT, 
                      status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'verified', 'rejected')),
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(reporter_id) REFERENCES users(id))''')
        
        # R6 Market alerts
        c.execute('''CREATE TABLE IF NOT EXISTS market_alerts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, alert_type TEXT,
                      max_price REAL CHECK(max_price >= 0), min_rank TEXT, operators_required TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def get_db_connection():
    """Get database connection with error handling"""
    try:
        conn = sqlite3.connect('iceai.db')
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

# Authentication decorator
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def validate_input(data, required_fields):
    """Validate input data"""
    errors = []
    for field in required_fields:
        if field not in data or not data[field] or str(data[field]).strip() == "":
            errors.append(f"{field} is required")
    return errors

# Routes
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/login")
def login():
    try:
        discord_auth_url = f"{DISCORD_API_BASE}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"
        return redirect(discord_auth_url)
    except Exception as e:
        logger.error(f"Login error: {e}")
        flash("An error occurred during login", "error")
        return redirect("/")

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        flash("Authentication failed: No code received", "error")
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
        token_res = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers, timeout=10)
        if token_res.status_code != 200:
            logger.error(f"Token request failed: {token_res.status_code} - {token_res.text}")
            flash("Failed to authenticate with Discord", "error")
            return redirect("/")

        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            logger.error("No access token received")
            flash("Authentication failed", "error")
            return redirect("/")

        # Get user info
        user_res = requests.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if user_res.status_code != 200:
            logger.error(f"User info request failed: {user_res.status_code}")
            flash("Failed to fetch user info", "error")
            return redirect("/")

        user = user_res.json()
        
        # Validate user data
        if not user.get("id") or not user.get("username"):
            logger.error("Invalid user data received")
            flash("Invalid user data received", "error")
            return redirect("/")
        
        # Store user in database
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO users (id, username, avatar, discriminator) VALUES (?, ?, ?, ?)",
                      (user["id"], user["username"], user.get("avatar"), user.get("discriminator", "0000")))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error storing user: {e}")
            flash("An error occurred during registration", "error")
            return redirect("/")
        finally:
            if conn:
                conn.close()
        
        session["user"] = {
            "id": user["id"],
            "username": user["username"], 
            "avatar": user.get("avatar"),
            "discriminator": user.get("discriminator", "0000")
        }
        
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during authentication: {e}")
        flash("Network error during authentication", "error")
        return redirect("/")
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")
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
    
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        # Get R6 specific stats with error handling
        c.execute("SELECT COUNT(*) FROM r6_accounts WHERE seller_id = ?", (user["id"],))
        accounts_listed = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM r6_transactions WHERE buyer_id = ? OR seller_id = ?", (user["id"], user["id"]))
        total_trades = c.fetchone()[0] or 0
        
        c.execute("SELECT COALESCE(SUM(price), 0) FROM r6_transactions WHERE seller_id = ? AND status = 'completed'", (user["id"],))
        total_earnings = c.fetchone()[0] or 0
        
        c.execute("SELECT AVG(rating) FROM vouches WHERE target_user_id = ?", (user["id"],))
        avg_rating_result = c.fetchone()[0]
        avg_rating = avg_rating_result if avg_rating_result else 0
        
        c.execute("SELECT COUNT(*) FROM tickets WHERE user_id = ?", (user["id"],))
        ticket_count = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM invites WHERE inviter_id = ?", (user["id"],))
        invite_count = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM vouches WHERE target_user_id = ?", (user["id"],))
        vouch_count = c.fetchone()[0] or 0
        
        stats = {
            "vouches": vouch_count,
            "tickets": ticket_count, 
            "invites": invite_count,
            "accounts_listed": accounts_listed,
            "total_trades": total_trades,
            "total_earnings": float(total_earnings),
            "avg_rating": round(float(avg_rating), 1) if avg_rating else 0,
            "member_since": "2024"
        }
        
    except sqlite3.Error as e:
        logger.error(f"Database error in dashboard: {e}")
        stats = {
            "vouches": 0, "tickets": 0, "invites": 0, "accounts_listed": 0,
            "total_trades": 0, "total_earnings": 0, "avg_rating": 0, "member_since": "2024"
        }
        flash("Error loading dashboard data", "warning")
    finally:
        if conn:
            conn.close()
    
    return render_template("dashboard.html", user=user, stats=stats)

# Moderation Routes
@app.route("/moderation")
@require_login
def moderation():
    return render_template("moderation.html", user=session.get("user"))

@app.route("/api/moderation/settings", methods=["GET", "POST"])
@require_login
def moderation_settings():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            for key, value in data.items():
                if not key or not isinstance(key, str):
                    continue
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                         (f"mod_{key}", json.dumps(value)))
            conn.commit()
            return jsonify({"success": True})
        
        # GET request - return current settings
        c.execute("SELECT key, value FROM settings WHERE key LIKE 'mod_%'")
        settings = {}
        for row in c.fetchall():
            key = row[0].replace("mod_", "")
            try:
                settings[key] = json.loads(row[1])
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in settings for key: {key}")
                continue
        
        return jsonify(settings)
        
    except sqlite3.Error as e:
        logger.error(f"Database error in moderation settings: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error in moderation settings: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# Tickets Routes
@app.route("/tickets")
@require_login
def tickets():
    user = session.get("user")
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
        user_tickets = c.fetchall()
        return render_template("tickets.html", user=user, tickets=user_tickets)
    except sqlite3.Error as e:
        logger.error(f"Database error in tickets: {e}")
        flash("Error loading tickets", "error")
        return render_template("tickets.html", user=user, tickets=[])
    finally:
        if conn:
            conn.close()

@app.route("/api/tickets/create", methods=["POST"])
@require_login
def create_ticket():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Validate input
        errors = validate_input(data, ["type", "subject", "description"])
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400
            
        user = session.get("user")
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO tickets (user_id, ticket_type, subject, description) VALUES (?, ?, ?, ?)",
                  (user["id"], data["type"], data["subject"], data["description"]))
        ticket_id = c.lastrowid
        conn.commit()
        
        return jsonify({"success": True, "ticket_id": ticket_id})
        
    except sqlite3.Error as e:
        logger.error(f"Database error creating ticket: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error creating ticket: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# Verification Routes
@app.route("/verification")
@require_login
def verification():
    return render_template("verification.html", user=session.get("user"))

@app.route("/api/verification/verify", methods=["POST"])
@require_login
def verify_user():
    try:
        data = request.get_json()
        if not data or not data.get("code"):
            return jsonify({"success": False, "message": "Verification code is required"}), 400
            
        user = session.get("user")
        verification_code = data.get("code")
        
        # Simple verification logic (in production, you'd have a more complex system)
        if verification_code == "VERIFY123":
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE users SET verified = 1 WHERE id = ?", (user["id"],))
            conn.commit()
            return jsonify({"success": True, "message": "Verification successful!"})
        
        return jsonify({"success": False, "message": "Invalid verification code"})
        
    except sqlite3.Error as e:
        logger.error(f"Database error in verification: {e}")
        return jsonify({"success": False, "message": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error in verification: {e}")
        return jsonify({"success": False, "message": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# Vouches Routes
@app.route("/vouches")
@require_login
def vouches():
    user = session.get("user")
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM vouches WHERE user_id = ? ORDER BY created_at DESC", (user["id"],))
        user_vouches = c.fetchall()
        return render_template("vouches.html", user=user, vouches=user_vouches)
    except sqlite3.Error as e:
        logger.error(f"Database error in vouches: {e}")
        flash("Error loading vouches", "error")
        return render_template("vouches.html", user=user, vouches=[])
    finally:
        if conn:
            conn.close()

@app.route("/api/vouches/create", methods=["POST"])
@require_login
def create_vouch():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Validate input
        errors = validate_input(data, ["target", "message", "rating"])
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400
            
        # Validate rating
        rating = data.get("rating")
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return jsonify({"error": "Rating must be between 1 and 5"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid rating format"}), 400
            
        user = session.get("user")
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""INSERT INTO vouches (user_id, target_user_id, message, rating, trade_type, account_rank, price, payment_method) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                  (user["id"], data["target"], data["message"], rating, 
                   data.get("trade_type", ""), data.get("account_rank", ""), 
                   data.get("price", 0), data.get("payment_method", "")))
        conn.commit()
        
        return jsonify({"success": True})
        
    except sqlite3.Error as e:
        logger.error(f"Database error creating vouch: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error creating vouch: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

@app.route("/api/vouches/export")
@require_login
def export_vouches():
    try:
        user = session.get("user")
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM vouches WHERE user_id = ?", (user["id"],))
        vouches = c.fetchall()
        
        # Convert to CSV format
        csv_data = "ID,Target User,Message,Rating,Trade Type,Account Rank,Price,Payment Method,Date\n"
        for vouch in vouches:
            # Escape CSV values
            values = [
                str(vouch[0]),
                str(vouch[2]).replace('"', '""'),
                str(vouch[3]).replace('"', '""'),
                str(vouch[4]),
                str(vouch[5] or '').replace('"', '""'),
                str(vouch[6] or '').replace('"', '""'),
                str(vouch[7] or 0),
                str(vouch[8] or '').replace('"', '""'),
                str(vouch[9])
            ]
            csv_data += ','.join(f'"{v}"' for v in values) + '\n'
        
        response = app.response_class(
            response=csv_data,
            status=200,
            mimetype='text/csv'
        )
        response.headers["Content-Disposition"] = "attachment; filename=vouches.csv"
        return response
        
    except sqlite3.Error as e:
        logger.error(f"Database error exporting vouches: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error exporting vouches: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# Giveaways Routes
@app.route("/giveaways")
@require_login
def giveaways():
    return render_template("giveaways.html", user=session.get("user"))

@app.route("/api/giveaways/create", methods=["POST"])
@require_login
def create_giveaway():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        # Validate input
        errors = validate_input(data, ["title", "prize", "winners", "end_time", "channel"])
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400
            
        # Validate winners count
        try:
            winners = int(data["winners"])
            if winners <= 0:
                return jsonify({"error": "Winners count must be positive"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid winners count"}), 400
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT INTO giveaways (title, description, prize, winners_count, end_time, channel_id) VALUES (?, ?, ?, ?, ?, ?)",
                  (data["title"], data.get("description", ""), data["prize"], winners, 
                   data["end_time"], data["channel"]))
        conn.commit()
        
        return jsonify({"success": True})
        
    except sqlite3.Error as e:
        logger.error(f"Database error creating giveaway: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error creating giveaway: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# R6 Marketplace Routes
@app.route("/marketplace")
@require_login
def marketplace():
    return render_template("marketplace.html", user=session.get("user"))

@app.route("/api/marketplace/accounts", methods=["GET", "POST"])
@require_login
def marketplace_accounts():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            # Validate input
            errors = validate_input(data, ["title", "rank", "level", "price"])
            if errors:
                return jsonify({"error": "Validation failed", "details": errors}), 400
                
            # Validate numeric fields
            try:
                level = int(data["level"])
                price = float(data["price"])
                operators = int(data.get("operators", 0))
                renown = int(data.get("renown", 0))
                credits = int(data.get("credits", 0))
                
                if level < 0 or price < 0 or operators < 0 or renown < 0 or credits < 0:
                    return jsonify({"error": "Numeric values must be non-negative"}), 400
                    
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid numeric values"}), 400
                
            user = session.get("user")
            c.execute("""INSERT INTO r6_accounts 
                         (seller_id, title, rank, level, operators_count, renown, r6_credits, price, description) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                      (user["id"], data["title"], data["rank"], level, 
                       operators, renown, credits, price, data.get("description", "")))
            conn.commit()
            return jsonify({"success": True})
        
        # GET request
        c.execute("SELECT * FROM r6_accounts WHERE status = 'available' ORDER BY created_at DESC LIMIT 100")
        accounts = c.fetchall()
        
        return jsonify([{
            "id": a[0], "title": a[2], "rank": a[3], "level": a[4],
            "operators": a[5], "renown": a[6], "credits": a[7], 
            "price": a[8], "description": a[9], "created_at": a[11]
        } for a in accounts])
        
    except sqlite3.Error as e:
        logger.error(f"Database error in marketplace: {e}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logger.error(f"Error in marketplace: {e}")
        return jsonify({"error": "Server error"}), 500
    finally:
        if conn:
            conn.close()

# Auto-Responder Routes
@app.route("/autoresponder")
@require_login
def autoresponder():
    return render_template("autoresponder.html", user=session.get("user"))

@app.route("/api/autoresponder", methods=["GET", "POST"])
@require_login
def autoresponder_api():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        
        if request.method == "POST":
            data = request.get_json()
            if not data:
                return jsonify({"error": "No data provided"}), 400
                
            # Validate input
            errors = validate_input(data, ["trigger", "response"])
            if errors:
                return jsonify({"error": "Validation failed", "details": errors}), 400
                
            c.execute("INSERT INTO autoresponder (trigger_phrase, response, embed_enabled, embed_data) VALUES (?, ?, ?, ?)",
                      (data["trigger"], data["response"], data.get("embed_enabled", 0), 
                       json.dumps(data.get("embed_data", {}))))
            conn.commit()
            return jsonify({"success": True})
        
        # GET request
        c.execute("SELECT * FROM autoresponder WHERE enabled = 1 ORDER BY id DESC LIMIT 100")
        responses = c.fetchall()
        
        return jsonify([{
            "id": r[0], "trigger": r[1], "response": r[2], 
            "embed_enabled": r[3],
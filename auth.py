import requests
import sqlite3
import logging
from functools import wraps
from flask import session, redirect, url_for, flash, request

from config import Config
from database import get_db_connection

logger = logging.getLogger(__name__)

def require_login(f):
    """Authentication decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access this page", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def authenticate_with_discord(code):
    """Handle Discord OAuth2 authentication"""
    data = {
        "client_id": Config.DISCORD_CLIENT_ID,
        "client_secret": Config.DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code", 
        "code": code,
        "redirect_uri": Config.DISCORD_REDIRECT_URI,
        "scope": "identify guilds"
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        # Get access token
        token_res = requests.post(f"{Config.DISCORD_API_BASE}/oauth2/token", 
                                data=data, headers=headers, timeout=10)
        
        if token_res.status_code != 200:
            logger.error(f"Token request failed: {token_res.status_code}")
            return None, "Failed to authenticate with Discord"

        token_data = token_res.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            return None, "No access token received"

        # Get user info
        user_res = requests.get(
            f"{Config.DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )

        if user_res.status_code != 200:
            return None, "Failed to fetch user info"

        user = user_res.json()
        
        if not user.get("id") or not user.get("username"):
            return None, "Invalid user data received"
        
        # Store user in database
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO users (id, username, avatar, discriminator) VALUES (?, ?, ?, ?)",
                      (user["id"], user["username"], user.get("avatar"), user.get("discriminator", "0000")))
            conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error storing user: {e}")
            return None, "Database error during registration"
        finally:
            if conn:
                conn.close()
        
        return user, None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error during authentication: {e}")
        return None, "Network error during authentication"
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")
        return None, "An error occurred during authentication"
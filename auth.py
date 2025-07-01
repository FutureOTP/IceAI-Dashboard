import os
import requests
from flask import Blueprint, redirect, request, session, url_for
from functools import wraps

auth_blueprint = Blueprint("auth", __name__)

# Discord OAuth2 Config
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI")
DISCORD_API_BASE = "https://discord.com/api"

# Login → Discord Authorization
@auth_blueprint.route("/login")
def login():
    discord_auth_url = f"{DISCORD_API_BASE}/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify"
    return redirect(discord_auth_url)

# Callback → Token Exchange → User Fetch
@auth_blueprint.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect("/")

    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "scope": "identify"
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Get access token
    token_res = requests.post(f"{DISCORD_API_BASE}/oauth2/token", data=data, headers=headers)
    if token_res.status_code != 200:
        return "Failed to authenticate with Discord", 400

    access_token = token_res.json().get("access_token")

    # Get user info
    user_res = requests.get(
        f"{DISCORD_API_BASE}/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if user_res.status_code != 200:
        return "Failed to fetch user info", 400

    user = user_res.json()
    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "avatar": user["avatar"],
        "discriminator": user["discriminator"]
    }

    return redirect(url_for("dashboard.dashboard"))

# Logout → Clear session
@auth_blueprint.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# Decorator to protect routes like /dashboard
def require_login(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

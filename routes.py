from flask import render_template, session, redirect, url_for, request, jsonify, flash
from auth import require_login, authenticate_with_discord
from config import Config
from services import DashboardService, TicketService, VouchService, MarketplaceService
import logging

logger = logging.getLogger(__name__)

def register_routes(app):
    """Register all application routes"""
    
    @app.route("/")
    def index():
        if session.get("user"):
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    @app.route("/login")
    def login():
        try:
            discord_auth_url = f"{Config.DISCORD_API_BASE}/oauth2/authorize?client_id={Config.DISCORD_CLIENT_ID}&redirect_uri={Config.DISCORD_REDIRECT_URI}&response_type=code&scope=identify%20guilds"
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

        user, error = authenticate_with_discord(code)
        if error:
            flash(error, "error")
            return redirect("/")
        
        session["user"] = {
            "id": user["id"],
            "username": user["username"], 
            "avatar": user.get("avatar"),
            "discriminator": user.get("discriminator", "0000")
        }
        
        flash(f"Welcome back, {user['username']}!", "success")
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        flash("You have been logged out successfully", "info")
        return redirect("/")

    @app.route("/dashboard")
    @require_login
    def dashboard():
        user = session.get("user")
        stats = DashboardService.get_user_stats(user["id"])
        return render_template("dashboard.html", user=user, stats=stats)

    # Tickets Routes
    @app.route("/tickets")
    @require_login
    def tickets():
        user = session.get("user")
        user_tickets = TicketService.get_user_tickets(user["id"])
        return render_template("tickets.html", user=user, tickets=user_tickets)

    @app.route("/api/tickets/create", methods=["POST"])
    @require_login
    def create_ticket():
        data = request.get_json()
        user = session.get("user")
        return TicketService.create_ticket(user["id"], data)

    # Vouches Routes
    @app.route("/vouches")
    @require_login
    def vouches():
        user = session.get("user")
        user_vouches = VouchService.get_user_vouches(user["id"])
        return render_template("vouches.html", user=user, vouches=user_vouches)

    @app.route("/api/vouches/create", methods=["POST"])
    @require_login
    def create_vouch():
        data = request.get_json()
        user = session.get("user")
        return VouchService.create_vouch(user["id"], data)

    # Marketplace Routes
    @app.route("/marketplace")
    @require_login
    def marketplace():
        return render_template("marketplace.html", user=session.get("user"))

    @app.route("/api/marketplace/accounts", methods=["GET", "POST"])
    @require_login
    def marketplace_accounts():
        if request.method == "POST":
            data = request.get_json()
            user = session.get("user")
            return MarketplaceService.create_account_listing(user["id"], data)
        else:
            return MarketplaceService.get_accounts()

    # Simple template routes
    template_routes = [
        ("/moderation", "moderation.html"),
        ("/verification", "verification.html"), 
        ("/giveaways", "giveaways.html"),
        ("/autoresponder", "autoresponder.html")
    ]
    
    for route, template in template_routes:
        app.add_url_rule(route, route.strip("/"), 
                        lambda t=template: render_template(t, user=session.get("user")),
                        methods=["GET"])
        # Apply login requirement
        app.view_functions[route.strip("/")] = require_login(app.view_functions[route.strip("/")])
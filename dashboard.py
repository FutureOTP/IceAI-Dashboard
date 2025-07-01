from flask import Blueprint, render_template, session, redirect, url_for
from auth import require_login

dashboard_blueprint = Blueprint("dashboard", __name__)

@dashboard_blueprint.route("/dashboard")
@require_login
def dashboard():
    user = session.get("user")
    return render_template("dashboard.html", user=user)

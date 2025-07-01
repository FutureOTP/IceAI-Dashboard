import os
from flask import Flask, render_template, session, redirect, url_for
from flask_cors import CORS
from dotenv import load_dotenv

from auth import auth_blueprint, require_login
from dashboard import dashboard_blueprint

# Load .env variables
load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("SECRET_KEY", "iceai_secret")

CORS(app)

# Register blueprints
app.register_blueprint(auth_blueprint)
app.register_blueprint(dashboard_blueprint)

# 🔐 Redirect to dashboard if logged in, else show login screen
@app.route("/")
def index():
    if session.get("user"):
        return redirect(url_for("dashboard.dashboard"))
    return render_template("login.html")

# 👥 Login redirect route
@app.route("/login")
def login_redirect():
    return redirect(url_for("auth.login"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

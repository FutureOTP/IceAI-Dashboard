from flask import Flask, render_template
from flask_cors import CORS
import os

# Import route modules
from auth import auth_blueprint
from dashboard import dashboard_blueprint
from webhooks import webhooks_blueprint

app = Flask(__name__, template_folder='templates', static_folder='static')
CORS(app)

app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret")

# Register Blueprints
app.register_blueprint(auth_blueprint)
app.register_blueprint(dashboard_blueprint)
app.register_blueprint(webhooks_blueprint)

@app.route("/")
def index():
    return render_template("login.html")

# Gunicorn entry point
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

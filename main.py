from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_cors import CORS

# ✅ Define the app at the global level
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = "your_secret_key"
CORS(app)

@app.route("/")
def index():
    if session.get("user"):
        return redirect("/dashboard")
    return render_template("login.html")


# ✅ Keep this at the bottom for local dev, but it’s ignored by gunicorn
if __name__ == "__main__":
    app.run(debug=True)

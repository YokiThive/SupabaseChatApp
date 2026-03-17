import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY env var")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            response = supabase.auth.sign_in_with_password({"email": email, "password": password})
            session["user"] = response.user.email
            session["user_id"] = response.user.id
            session["username"] = response.user.user_metadata.get("username", "User")
            return redirect(url_for("chat_page"))

        except Exception:
            flash("Invalid email or password")
            return redirect(url_for("login"))

    return render_template(
        "login.html",
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_KEY,
        redirect_url=url_for("auth_callback", _external=True))

#confirm email disabled
@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        try:
            supabase.auth.sign_up({"email": email, "password": password,
                                  "options":{
                                      "data": {
                                          "name": name,
                                          "username": username
                                      }}
                                  })
            flash("User created successfully")
            return redirect(url_for("login"))

        except Exception as e:
            #flash("Registration failed")
            flash(str(e))
            return redirect(url_for("register"))

    return render_template(
        "register.html",
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_KEY,
        redirect_url=url_for("auth_callback", _external=True)
    )

@app.route("/chatpage")
def chat_page():
    if "user" not in session: #if not logged in, don't give access
        return redirect(url_for("login"))

    #fetch all messages, ordered by timestamp
    #use 'limit' for loading the newest num of messages
    response = supabase.table("messages").select("*").order("created_at").limit(100).execute()
    messages = response.data if response.data else [] #if no messages then use empty list
    for msg in messages:
        timestamp = msg["created_at"]
        date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        msg["created_at"] = date.strftime("%H:%M") #5:20 time

    return render_template(
        "chatpage.html",
        messages=messages,
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_KEY
    )

@app.route("/send-message", methods=["POST"])
def send_message():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    #checks login, empty message, max length, inserts, and finally returns JSON
    data = request.get_json()
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400
    if len(message) > 500:
        return jsonify({"error": "Message is too long"}), 400

    try:
        supabase.table("messages").insert({
            "sender": session["user"],
            "sender_name": session["username"],
            "content": message
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/google-session", methods=["POST"])
def google_session():
    data = request.get_json()
    session["user"] = data["email"]
    session["user_id"] = data["user_id"]
    session["username"] = data["username"]
    return jsonify({"success": True})

@app.route("/auth/callback")
def auth_callback():
    return render_template(
        "auth_callback.html",
        supabase_url=SUPABASE_URL,
        supabase_anon_key=SUPABASE_KEY)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run()
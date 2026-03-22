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
            session["access_token"] = response.session.access_token
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

    #image
    image_url = None
    if "image" in request.files:
        file = request.files["image"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        allowed_file_type = {"png", "jpg", "jpeg", "gif", "webp"}
        ext = file.filename.rsplit(".", 1)[1].lower()

        if ext not in allowed_file_type:
            return jsonify({"error": "Invalid file type"}), 400

        #max cap to 5MB
        file_bytes = file.read()
        if len(file_bytes) > 5 * 1024 * 1024:
            return jsonify({"error": "Max file size is 5MB"}), 400

        #filename using username, timestamp, and file extension
        filename = f"{session['user']}_{int(datetime.now().timestamp())}.{ext}"
        supabase.storage.from_("chat-images").upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": file.content_type}
        )
        image_url = supabase.storage.from_("chat-images").get_public_url(filename)

    #text messages
    #checks login, empty message, max length, inserts, and finally returns JSON
    message = request.form.get("message", "").strip()
    if not message and not image_url:
        return jsonify({"error": "Message or image is required"}), 400
    if len(message) > 500:
        return jsonify({"error": "Message is too long"}), 400

    try:
        supabase.table("messages").insert({
            "sender": session["user"],
            "sender_name": session["username"],
            "content": message,
            "image_url": image_url
        }).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/get-messages")
def get_messages():
    if "user" not in session:
        return jsonify({"error": "Not authenticated"}), 401

    response = supabase.table("messages").select("*").order("created_at").limit(100).execute()
    messages = response.data if response.data else []
    return jsonify(messages)

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
    #doesn't hold user's token, so won't invalidate their session -> need to pass their token
    try:
        access_token = session.get("access_token")
        if access_token:
            supabase.auth.admin.sign_out(access_token)
    except Exception:
        pass
    session.clear()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run()
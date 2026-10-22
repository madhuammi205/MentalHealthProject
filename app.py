
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from google import genai
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

import os
import time
import sqlite3
import json
import re
from datetime import datetime, timezone

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(32)

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mindcare.db")

api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    print("Gemini API key loaded successfully.")
    client = genai.Client(api_key=api_key)
else:
    print("ERROR: Gemini API key not found.")
    client = None


# DATABASE CONNECTION
def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def current_time():
    return datetime.now(timezone.utc).isoformat()


# CREATE DATABASE TABLES
def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL UNIQUE,
                user_id INTEGER NOT NULL,
                stress_percentage INTEGER,
                summary TEXT NOT NULL,
                guidance TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );
        """)


init_db()


# GEMINI HELPER
def ask_gemini(prompt):
    if not client:
        return None

    try:
        start = time.time()

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        elapsed = time.time() - start
        print(f"Gemini response time: {elapsed:.2f} seconds")

        if response.text:
            return response.text.strip()

    except Exception as error:
        print("GEMINI ERROR:", error)

    return None


# HOME PAGE
@app.route("/")
def home():
    return render_template("home.html")


# REGISTER ACCOUNT
@app.route("/register", methods=["GET", "POST"])
def register():
    error = ""

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            error = "Use 3–30 letters, numbers or underscores for your username."

        elif len(email) > 254 or not re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+", email
        ):
            error = "Please enter a valid email address."

        elif len(password) < 8 or len(password) > 128:
            error = "Password must contain 8–128 characters."

        else:
            try:
                with get_db() as db:
                    db.execute("""
                        INSERT INTO users
                        (username, email, password_hash, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (
                        username,
                        email,
                        generate_password_hash(password),
                        current_time()
                    ))

                return redirect(url_for("login"))

            except sqlite3.IntegrityError:
                error = "That username or email is already registered."

    return render_template("register.html", error=error)


# LOGIN
@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        identity = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute("""
                SELECT * FROM users
                WHERE username = ? COLLATE NOCASE
                   OR email = ? COLLATE NOCASE
            """, (identity, identity)).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("chat"))

        error = "Invalid username/email or password."

    return render_template("login.html", error=error)


# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# EXISTING ASSESSMENT PAGE
@app.route("/assessment")
def assessment():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("assessment.html")


# EXISTING ASSESSMENT RESULT
@app.route("/result", methods=["POST"])
def result():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    score = 0
    questions = [
        "q1", "q2", "q3", "q4", "q5",
        "q6", "q7", "q8", "q9", "q10"
    ]

    for question in questions:
        answer = request.form.get(question)

        if answer not in ["0", "1", "3", "4"]:
            return "Please answer all questions.", 400

        score += int(answer)

    if score <= 10:
        status = "Normal"
        guidance = [
            "Maintain a healthy daily routine.",
            "Get adequate sleep and regular physical activity.",
            "Spend time doing activities you enjoy."
        ]
    elif score <= 20:
        status = "Mild Stress"
        guidance = [
            "Take short breaks during study or work.",
            "Practice relaxation exercises.",
            "Maintain regular sleep and meal schedules."
        ]
    elif score <= 30:
        status = "Moderate Stress"
        guidance = [
            "Take time to rest and manage your workload.",
            "Try mindfulness activities.",
            "Talk to someone you trust if overwhelmed."
        ]
    else:
        status = "High Stress"
        guidance = [
            "Prioritize rest and self-care.",
            "Talk to someone you trust.",
            "Consider speaking with a qualified professional."
        ]

    prompt = f"""
Provide 3 or 4 practical, supportive wellness suggestions.

The project-designed questionnaire score is {score} out of 40.

Do not diagnose or claim this score proves a medical condition.
Return short bullet points.
"""

    ai_guidance = ask_gemini(prompt) or (
        "AI guidance is temporarily unavailable. Please try again later."
    )

    return render_template(
        "result.html",
        score=score,
        status=status,
        guidance=guidance,
        ai_guidance=ai_guidance
    )


# START A NEW CHAT
@app.route("/chat")
def chat():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO conversations
            (user_id, started_at, status)
            VALUES (?, ?, 'active')
        """, (user_id, current_time()))

        conversation_id = cursor.lastrowid

        opening = (
            "Welcome to MindCare 💜 How have you been feeling emotionally "
            "lately, and is there anything in particular that's been "
            "on your mind?"
        )

        db.execute("""
            INSERT INTO messages
            (conversation_id, user_id, role, content, created_at)
            VALUES (?, ?, 'assistant', ?, ?)
        """, (conversation_id, user_id, opening, current_time()))

    session["conversation_id"] = conversation_id
    return render_template("chat.html")


# DISPLAY THE ADAPTIVE CHAT REPORT
@app.route("/chat/result")
def chat_result():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    conversation_id = session.get("conversation_id")
    user_id = session["user_id"]

    if not conversation_id:
        return redirect(url_for("chat"))

    with get_db() as db:
        report = db.execute("""
            SELECT * FROM reports
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id)).fetchone()

    if not report:
        return redirect(url_for("chat"))

    try:
        guidance = json.loads(report["guidance"])
        if not isinstance(guidance, list):
            raise ValueError("Invalid guidance format")
    except (json.JSONDecodeError, TypeError, ValueError):
        guidance = [
            "Take short breaks and make time for activities you enjoy.",
            "Try to maintain a regular sleep and daily routine.",
            "Talk with someone you trust if you need support."
        ]

    return render_template(
        "result.html",
        summary=report["summary"],
        percentage=report["stress_percentage"],
        guidance=guidance,
        report_type="chat"
    )

# CHAT AND SAVE EVERY MESSAGE
@app.route("/chat/message", methods=["POST"])
def chat_message():
    if not session.get("user_id"):
        return jsonify({"error": "Please log in first."}), 401

    user_id = session["user_id"]
    conversation_id = session.get("conversation_id")

    if not conversation_id:
        return jsonify({
            "error": "Please start a new conversation."
        }), 400

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    finish = data.get("finish") is True

    if not finish and (not message or len(message) > 1000):
        return jsonify({
            "error": "Enter a message of up to 1000 characters."
        }), 400

    user_message_id = None

    with get_db() as db:
        conversation = db.execute("""
            SELECT id FROM conversations
            WHERE id = ? AND user_id = ? AND status = 'active'
        """, (conversation_id, user_id)).fetchone()

        if not conversation:
            return jsonify({
                "error": "This conversation has ended. Start a new one."
            }), 400

        if not finish:
            cursor = db.execute("""
                INSERT INTO messages
                (conversation_id, user_id, role, content, created_at)
                VALUES (?, ?, 'user', ?, ?)
            """, (conversation_id, user_id, message, current_time()))

            user_message_id = cursor.lastrowid

        messages = db.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY id
        """, (conversation_id, user_id)).fetchall()

        user_count = sum(
            1 for item in messages if item["role"] == "user"
        )

    if user_count == 0:
        return jsonify({
            "reply": "Please share a little about how you have been feeling first. 💜",
            "finished": False
        })

    if user_count >= 6:
        finish = True

    transcript = "\n".join(
        f'{item["role"].upper()}: {item["content"]}'
        for item in messages
    )

    # CREATE THE FINAL REPORT
    if finish:
        prompt = f"""
You are MindCare AI, a supportive general wellness companion.

Return ONLY a valid JSON object containing:
- stress_percentage: an integer from 0 to 100
- summary: a short, compassionate summary
- guidance: an array of exactly three practical wellness suggestions

Conversation:
{transcript}

Important:
The percentage is an experimental AI-generated project estimate,
not a validated clinical scale or medical diagnosis.
Do not diagnose any condition or overstate certainty.
Use respectful, non-judgmental language.
The suggestions must be safe and practical.
"""

        raw_report = ask_gemini(prompt)

        percentage = None
        summary = (
            "Thank you for taking time to reflect on your well-being. "
            "Your conversation is complete."
        )
        guidance = [
            "Take short breaks and make time for activities you enjoy.",
            "Try to maintain a regular sleep and daily routine.",
            "Consider talking with someone you trust if you need support."
        ]

        if raw_report:
            try:
                cleaned = re.sub(
                    r"^```(?:json)?\s*|\s*```$",
                    "",
                    raw_report.strip(),
                    flags=re.IGNORECASE
                )

                report_data = json.loads(cleaned)

                value = int(report_data.get("stress_percentage"))

                if 0 <= value <= 100:
                    percentage = value

                if isinstance(report_data.get("summary"), str):
                    summary = report_data["summary"][:2000]

                if isinstance(report_data.get("guidance"), list):
                    suggestions = [
                        str(item)[:500]
                        for item in report_data["guidance"][:3]
                        if str(item).strip()
                    ]

                    if suggestions:
                        guidance = suggestions

            except (ValueError, TypeError, json.JSONDecodeError) as error:
                print("REPORT PARSE ERROR:", error)

        with get_db() as db:
            db.execute("""
                INSERT INTO reports
                (conversation_id, user_id, stress_percentage,
                 summary, guidance, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO NOTHING
            """, (
                conversation_id,
                user_id,
                percentage,
                summary,
                json.dumps(guidance),
                current_time()
            ))

            db.execute("""
                UPDATE conversations
                SET status = 'completed', ended_at = ?
                WHERE id = ? AND user_id = ?
            """, (current_time(), conversation_id, user_id))

        return jsonify({
            "reply": "🌿 Your report is ready! Opening your results...",
            "finished": True,
            "redirect_url": url_for("chat_result")
        })

    # GENERATE THE NEXT QUESTION
    prompt = f"""
You are MindCare AI, a kind wellness companion.

Conversation:
{transcript}

Ask exactly ONE short follow-up question based mainly on
the user's latest answer.

Rules:
- Be specific and empathetic.
- Never repeat an earlier question.
- Use previous answers for context.
- Use at most one suitable emoji.
- Do not diagnose or assign a percentage.
- Return only the question.
"""

    reply = ask_gemini(prompt)

    if not reply:
        reply = (
            "💜 You mentioned that this has been difficult for you. "
            "What feels most challenging about it right now?"
        )

    with get_db() as db:
        db.execute("""
            INSERT INTO messages
            (conversation_id, user_id, role, content, created_at)
            VALUES (?, ?, 'assistant', ?, ?)
        """, (conversation_id, user_id, reply, current_time()))

    return jsonify({
        "reply": reply,
        "finished": False,
        "user_message_id": user_message_id
    })


# EDIT AN ANSWER AND REGENERATE THE NEXT QUESTION
@app.route("/chat/edit-message", methods=["POST"])
def edit_chat_message():
    if not session.get("user_id"):
        return jsonify({"error": "Please log in first."}), 401

    user_id = session["user_id"]
    conversation_id = session.get("conversation_id")
    data = request.get_json(silent=True) or {}

    message_id = data.get("message_id")
    content = str(data.get("content", "")).strip()

    if not isinstance(message_id, int) or isinstance(message_id, bool):
        return jsonify({"error": "Invalid message ID."}), 400

    if not content or len(content) > 1000:
        return jsonify({
            "error": "Enter an answer of 1–1000 characters."
        }), 400

    if not conversation_id:
        return jsonify({"error": "No active conversation found."}), 400

    with get_db() as db:
        conversation = db.execute("""
            SELECT id FROM conversations
            WHERE id = ? AND user_id = ? AND status = 'active'
        """, (conversation_id, user_id)).fetchone()

        if not conversation:
            return jsonify({
                "error": "Only active conversations can be edited."
            }), 400

        original = db.execute("""
            SELECT id FROM messages
            WHERE id = ? AND conversation_id = ?
              AND user_id = ? AND role = 'user'
        """, (message_id, conversation_id, user_id)).fetchone()

        if not original:
            return jsonify({"error": "Answer not found."}), 404

        db.execute("""
            UPDATE messages
            SET content = ?
            WHERE id = ? AND conversation_id = ?
              AND user_id = ? AND role = 'user'
        """, (content, message_id, conversation_id, user_id))

        # Remove later messages that depended on the old answer.
        db.execute("""
            DELETE FROM messages
            WHERE conversation_id = ? AND user_id = ? AND id > ?
        """, (conversation_id, user_id, message_id))

        messages = db.execute("""
            SELECT role, content FROM messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY id
        """, (conversation_id, user_id)).fetchall()

    transcript = "\n".join(
        f'{item["role"].upper()}: {item["content"]}'
        for item in messages
    )

    prompt = f"""
You are MindCare AI, a kind and supportive wellness companion.

Here is the conversation after the user corrected one of their answers:
{transcript}

Ask exactly ONE short follow-up question based on the corrected answer
and previous context. Do not repeat an earlier question.
Be warm, respectful, and non-judgmental. Do not diagnose.
Use at most one suitable emoji. Return only the question.
"""

    reply = ask_gemini(prompt)

    if not reply:
        reply = (
            "💜 Thanks for clarifying. What feels most important "
            "for you to talk about next?"
        )

    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO messages
            (conversation_id, user_id, role, content, created_at)
            VALUES (?, ?, 'assistant', ?, ?)
        """, (conversation_id, user_id, reply, current_time()))

        assistant_message_id = cursor.lastrowid

    return jsonify({
        "success": True,
        "message_id": message_id,
        "corrected_content": content,
        "reply": reply,
        "assistant_message_id": assistant_message_id
    })


# CHAT HISTORY
@app.route("/chat/history")
def chat_history():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:
        conversations = db.execute("""
            SELECT
                c.id,
                c.started_at,
                c.ended_at,
                c.status,
                (
                    SELECT m.content
                    FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.id DESC
                    LIMIT 1
                ) AS last_message,
                EXISTS (
                    SELECT 1
                    FROM reports r
                    WHERE r.conversation_id = c.id
                      AND r.user_id = c.user_id
                ) AS has_report
            FROM conversations c
            WHERE c.user_id = ?
            ORDER BY c.id DESC
        """, (user_id,)).fetchall()

    return render_template(
        "chat_history.html",
        conversations=conversations
    )


# CHAT HISTORY DETAIL
@app.route("/chat/history/<int:conversation_id>")
def chat_history_detail(conversation_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:
        conversation = db.execute("""
            SELECT *
            FROM conversations
            WHERE id = ? AND user_id = ?
        """, (conversation_id, user_id)).fetchone()

        if not conversation:
            return redirect(url_for("chat_history"))

        messages = db.execute("""
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY id
        """, (conversation_id, user_id)).fetchall()

    return render_template(
        "chat_history_detail.html",
        conversation=conversation,
        messages=messages
    )


# CHAT HISTORY REPORT
@app.route("/chat/history/<int:conversation_id>/result")
def chat_history_result(conversation_id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]

    with get_db() as db:
        report = db.execute("""
            SELECT *
            FROM reports
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id)).fetchone()

    if not report:
        return redirect(url_for("chat_history"))

    try:
        guidance = json.loads(report["guidance"])
    except (TypeError, json.JSONDecodeError):
        guidance = []

    return render_template(
        "result.html",
        summary=report["summary"],
        percentage=report["stress_percentage"],
        guidance=guidance
    )


if __name__ == "__main__":
    app.run(debug=True)

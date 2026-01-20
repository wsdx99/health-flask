# ---------------- imports ----------------
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import os
import json
from pywebpush import webpush, WebPushException

# ---------------- app init ----------------
app = Flask(__name__)
app.secret_key = "dev"

# ---------------- config ----------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///health.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- PWA / Push config ----------------
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY_PEM = os.getenv("VAPID_PRIVATE_KEY_PEM", "").replace("\\n", "\n")
VAPID_CLAIMS = {"sub": "mailto:example@example.com"}
CRON_SECRET = os.getenv("CRON_SECRET", "")

# ---------------- models ----------------
class MealRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meal = db.Column(db.String(100), nullable=False)
    calorie = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)

class ExerciseRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(100), nullable=False)
    minutes = db.Column(db.Integer, nullable=False)
    burned = db.Column(db.Integer, nullable=False)
    steps = db.Column(db.Integer, default=0)
    date = db.Column(db.DateTime, default=datetime.now)

class ExercisePlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(100), nullable=False)
    plan_datetime = db.Column(db.DateTime, nullable=False)
    target_minutes = db.Column(db.Integer, default=0)
    target_calorie = db.Column(db.Integer, default=0)
    note = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.Text, unique=True, nullable=False)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

# ---------------- constants & helpers ----------------
DAILY_GOAL = 1800
USER_WEIGHT_KG = 60

MET_VALUES = {
    "walk": 3.3,
    "jog": 7.0,
    "run": 9.8,
    "bike": 6.8,
    "gym": 5.0,
}

def guess_activity_key(kind: str) -> str:
    text = kind.lower()
    if "歩" in kind or "walk" in text:
        return "walk"
    if "jog" in text:
        return "jog"
    if "run" in text:
        return "run"
    if "bike" in text:
        return "bike"
    return "walk"

def calc_exercise_calories(activity_key, minutes, steps=0):
    met = MET_VALUES.get(activity_key, 3.0)
    return int(met * USER_WEIGHT_KG * (minutes / 60) + steps * 0.04)

# ---------------- push helper ----------------
def send_push_to_all(payload_dict: dict) -> tuple[int, int]:
    """return (sent, failed)"""
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY_PEM:
        return (0, 0)

    subs = PushSubscription.query.all()
    sent, failed = 0, 0
    payload = json.dumps(payload_dict)

    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY_PEM,
                vapid_claims=VAPID_CLAIMS,
            )
            sent += 1
        except WebPushException:
            failed += 1

    return sent, failed

# ---------------- routes ----------------
@app.route("/")
def cover():
    return render_template("cover.html", title="ウェルカム")

@app.route("/home")
def index():
    return render_template("index.html", title="ホーム")

# ----- Meals -----
@app.route("/meals", methods=["GET", "POST"])
def meals():
    if request.method == "POST":
        meal = (request.form.get("meal") or "").strip()
        calorie = (request.form.get("calorie") or "").strip()
        date_str = (request.form.get("date") or "").strip()

        if not meal or not calorie or not date_str:
            flash("入力が不足しています。")
            return redirect(url_for("meals"))

        try:
            calorie_int = int(calorie)
        except ValueError:
            flash("カロリーは数値で入力してください。")
            return redirect(url_for("meals"))

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            flash("日付の形式が正しくありません。")
            return redirect(url_for("meals"))

        db.session.add(MealRecord(meal=meal, calorie=calorie_int, date=d))
        db.session.commit()
        flash("保存しました。")
        return redirect(url_for("meals"))

    records = MealRecord.query.order_by(MealRecord.date.desc()).all()
    return render_template("meals.html", title="食事記録", records=records, default_date=date.today().isoformat())

# ----- Exercises -----
@app.route("/exercises", methods=["GET", "POST"])
def exercises():
    if request.method == "POST":
        kind = (request.form.get("kind") or "").strip()
        minutes_str = (request.form.get("minutes") or "").strip()
        steps_str = (request.form.get("steps") or "").strip()
        burned_str = (request.form.get("burned") or "").strip()
        date_str = (request.form.get("date") or "").strip()

        if not kind or not date_str:
            flash("運動名と日付は必須です。")
            return redirect(url_for("exercises"))

        try:
            minutes = int(minutes_str) if minutes_str else 0
        except ValueError:
            flash("分は数値で入力してください。")
            return redirect(url_for("exercises"))

        try:
            steps = int(steps_str) if steps_str else 0
        except ValueError:
            flash("歩数は数値で入力してください。")
            return redirect(url_for("exercises"))

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            flash("日付の形式が正しくありません。")
            return redirect(url_for("exercises"))

        if burned_str:
            try:
                burned = int(burned_str)
            except ValueError:
                flash("消費(kcal)は数値で入力してください。")
                return redirect(url_for("exercises"))
        else:
            burned = calc_exercise_calories(guess_activity_key(kind), minutes, steps)

        db.session.add(ExerciseRecord(kind=kind, minutes=minutes, steps=steps, burned=burned, date=d))
        db.session.commit()
        flash("保存しました。")
        return redirect(url_for("exercises"))

    records = ExerciseRecord.query.order_by(ExerciseRecord.date.desc()).all()
    return render_template("exercises.html", title="運動記録", records=records, default_date=date.today().isoformat())

# ----- Plans / Reports -----
@app.route("/plans")
def plans():
    return render_template("plans.html", title="運動計画")

@app.route("/reports")
def reports():
    return render_template("reports.html", title="レポート")

# ----- Food analyze API -----
@app.route("/api/food/analyze", methods=["POST"])
def api_food_analyze():
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "no image"}), 400
    return jsonify({"ok": True, "name": "サラダ"})

# ----- Push APIs -----
@app.route("/api/push/public-key")
def push_public_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})

@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    data = request.get_json(force=True)
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})

    if not endpoint:
        return jsonify({"ok": False}), 400

    if not PushSubscription.query.filter_by(endpoint=endpoint).first():
        db.session.add(
            PushSubscription(
                endpoint=endpoint,
                p256dh=keys.get("p256dh") or "",
                auth=keys.get("auth") or "",
            )
        )
        db.session.commit()

    return jsonify({"ok": True})

@app.route("/api/push/test", methods=["POST"])
def push_test():
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY_PEM:
        return jsonify({"ok": False, "error": "VAPID keys not set"}), 500

    sent, failed = send_push_to_all({
        "title": "テスト通知",
        "body": "Web Push が動作しました ✅",
        "url": "/meals"
    })
    return jsonify({"ok": True, "sent": sent, "failed": failed})

@app.route("/api/push/daily-reminder", methods=["POST"])
def push_daily_reminder():
    if not CRON_SECRET:
        return jsonify({"ok": False, "error": "CRON_SECRET not set"}), 500

    auth = request.headers.get("X-CRON-SECRET", "")
    if auth != CRON_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    sent, failed = send_push_to_all({
        "title": "健康管理リマインド",
        "body": "今日の食事・運動を記録しましたか？",
        "url": "/home"
    })
    return jsonify({"ok": True, "sent": sent, "failed": failed})

# ---------------- main ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)

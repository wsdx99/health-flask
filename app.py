from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, date, time, timedelta
import os
import json
from pywebpush import webpush, WebPushException

# ---------------- app init ----------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev")

# ---------------- config ----------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///health.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---------------- PWA / Push config ----------------
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY_PEM = os.getenv("VAPID_PRIVATE_KEY_PEM", "").replace("\\n", "\n")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_SUB", "mailto:example@example.com")}
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
    text = (kind or "").lower()
    if ("歩" in kind) or ("ウォーク" in kind) or ("walk" in text):
        return "walk"
    if ("ジョギ" in kind) or ("jog" in text):
        return "jog"
    if ("ラン" in kind) or ("run" in text):
        return "run"
    if ("自転車" in kind) or ("バイク" in kind) or ("bike" in text):
        return "bike"
    if ("筋" in kind) or ("ジム" in kind):
        return "gym"
    return "walk"

def calc_exercise_calories(activity_key: str, minutes: int, steps: int = 0) -> int:
    met = MET_VALUES.get(activity_key, 3.0)
    hours = minutes / 60.0
    kcal_met = met * USER_WEIGHT_KG * hours
    kcal_steps = steps * 0.04
    return int(kcal_met + kcal_steps)

# ---------------- push helper ----------------
def send_push_to_all(payload_dict: dict) -> tuple[int, int, list[str]]:
    """return (sent, failed, errors_sample)"""
    subs = PushSubscription.query.all()
    sent, failed = 0, 0
    errors = []
    payload = json.dumps(payload_dict, ensure_ascii=False)

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
        except WebPushException as e:
            failed += 1
            msg = str(e)
            errors.append(msg)
            print("WebPush failed:", repr(e))

    return sent, failed, errors[:3]

# ---------------- routes: PWA assets ----------------
@app.route("/sw.js")
def sw():
    return send_from_directory("static", "sw.js", mimetype="application/javascript")

# ---------------- routes: pages ----------------
@app.route("/")
def cover():
    return render_template("cover.html", title="ウェルカム")

@app.route("/home")
def index():
    return render_template("index.html", title="ホーム")

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
            steps = int(steps_str) if steps_str else 0
        except ValueError:
            flash("分・歩数は数値で入力してください。")
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

@app.route("/plans", methods=["GET", "POST"])
def plans():
    if request.method == "POST":
        kind = (request.form.get("kind") or "").strip()
        date_str = (request.form.get("date") or "").strip()
        time_str = (request.form.get("time") or "").strip()
        minutes_str = (request.form.get("minutes") or "").strip()
        kcal_str = (request.form.get("kcal") or "").strip()
        note = (request.form.get("note") or "").strip()

        if not kind or not date_str or not time_str:
            flash("運動名・日付・時間は必須です。")
            return redirect(url_for("plans"))

        try:
            minutes_val = int(minutes_str) if minutes_str else 0
            kcal_val = int(kcal_str) if kcal_str else 0
        except ValueError:
            flash("時間とカロリーは数値で入力してください。")
            return redirect(url_for("plans"))

        try:
            plan_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        except ValueError:
            flash("日付または時間の形式が不正です。")
            return redirect(url_for("plans"))

        db.session.add(ExercisePlan(
            kind=kind,
            plan_datetime=plan_dt,
            target_minutes=minutes_val,
            target_calorie=kcal_val,
            note=note or None
        ))
        db.session.commit()
        flash("運動計画を登録しました。")
        return redirect(url_for("plans"))

    items = ExercisePlan.query.order_by(ExercisePlan.plan_datetime.asc()).all()
    return render_template("plans.html", title="運動計画", plans=items, default_date=date.today().isoformat(), default_time="18:00")

@app.route("/reports")
def reports():
    total_in = db.session.query(func.coalesce(func.sum(MealRecord.calorie), 0)).scalar() or 0
    total_out = db.session.query(func.coalesce(func.sum(ExerciseRecord.burned), 0)).scalar() or 0
    net = total_in - total_out

    today = date.today()
    start_day = today - timedelta(days=6)
    start_dt = datetime.combine(start_day, time.min)
    end_dt = datetime.combine(today + timedelta(days=1), time.min)

    meal_rows = (
        db.session.query(func.date(MealRecord.date).label("d"), func.coalesce(func.sum(MealRecord.calorie), 0))
        .filter(MealRecord.date >= start_dt, MealRecord.date < end_dt)
        .group_by("d")
        .all()
    )
    ex_rows = (
        db.session.query(func.date(ExerciseRecord.date).label("d"), func.coalesce(func.sum(ExerciseRecord.burned), 0))
        .filter(ExerciseRecord.date >= start_dt, ExerciseRecord.date < end_dt)
        .group_by("d")
        .all()
    )

    meal_by_date = {row[0]: row[1] for row in meal_rows}
    ex_by_date = {row[0]: row[1] for row in ex_rows}

    labels, in_data, out_data, daily_rows = [], [], [], []
    for i in range(7):
        d = start_day + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        v_in = meal_by_date.get(d_str, 0)
        v_out = ex_by_date.get(d_str, 0)
        labels.append(d_str)
        in_data.append(v_in)
        out_data.append(v_out)
        daily_rows.append((d_str, {"in": v_in, "out": v_out}))

    today_in = meal_by_date.get(today.strftime("%Y-%m-%d"), 0)
    progress = int(min(today_in / DAILY_GOAL * 100, 200)) if DAILY_GOAL > 0 else 0

    return render_template(
        "reports.html",
        title="レポート",
        total_in=total_in,
        total_out=total_out,
        net=net,
        daily_goal=DAILY_GOAL,
        today_in=today_in,
        progress=progress,
        daily_rows=daily_rows,
        labels=labels,
        in_data=in_data,
        out_data=out_data,
    )

# ---------------- routes: food analyze API ----------------
@app.route("/api/food/analyze", methods=["POST"])
def api_food_analyze():
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "no image"}), 400
    return jsonify({"ok": True, "name": "サラダ"})

# ---------------- routes: push APIs ----------------
@app.route("/api/push/public-key")
def push_public_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})

@app.route("/api/push/subscribe", methods=["POST"])
def push_subscribe():
    data = request.get_json(force=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys") or {}
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        return jsonify({"ok": False, "error": "invalid subscription"}), 400

    sub = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not sub:
        db.session.add(PushSubscription(endpoint=endpoint, p256dh=p256dh, auth=auth))
        db.session.commit()

    return jsonify({"ok": True})

@app.route("/api/push/test", methods=["POST"])
def push_test():
    if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY_PEM:
        return jsonify({
            "ok": False,
            "error": "VAPID keys not set",
            "has_public": bool(VAPID_PUBLIC_KEY),
            "has_private": bool(VAPID_PRIVATE_KEY_PEM),
        }), 500

    sent, failed, errors = send_push_to_all({
        "title": "テスト通知",
        "body": "Web Push が動作しました ✅",
        "url": "/home",
    })
    return jsonify({"ok": True, "sent": sent, "failed": failed, "errors": errors})

@app.route("/api/push/daily-reminder", methods=["POST"])
def push_daily_reminder():
    if not CRON_SECRET:
        return jsonify({"ok": False, "error": "CRON_SECRET not set"}), 500

    auth = request.headers.get("X-CRON-SECRET", "")
    if auth != CRON_SECRET:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    sent, failed, errors = send_push_to_all({
        "title": "健康管理リマインド",
        "body": "今日の食事・運動を記録しましたか？",
        "url": "/home",
    })
    return jsonify({"ok": True, "sent": sent, "failed": failed, "errors": errors})

@app.route("/api/push/debug/subscribers")
def push_debug_subscribers():
    return jsonify({"count": PushSubscription.query.count()})

# ---------------- main ----------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)

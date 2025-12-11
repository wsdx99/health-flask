from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime, date, time, timedelta

app = Flask(__name__)
app.secret_key = "dev"  # flash 用，正式环境请修改

# --- SQLite + SQLAlchemy 設定 ---
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///health.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# --- モデル定義 ---
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
    steps = db.Column(db.Integer, default=0)  # 新增：歩数
    date = db.Column(db.DateTime, default=datetime.now)

# 1日の目標摂取量（必要に応じて変更）
DAILY_GOAL = 1800

# --- 運動カロリー自動計算 用の定数 ---
# おおよその MET 値（ざっくりでOK、レポート用）
MET_VALUES = {
    "walk": 3.3,   # ウォーキング
    "jog": 7.0,    # ジョギング
    "run": 9.8,    # ランニング
    "bike": 6.8,   # 自転車
    "gym": 5.0,    # 筋トレ・ジム
}

USER_WEIGHT_KG = 60  # 仮の体重。後でユーザー入力にしても良い

def guess_activity_key(kind: str) -> str:
    """運動名の日本語から、ざっくり種別を推測"""
    text = kind.lower()
    if "歩" in kind or "ウォーク" in kind or "walk" in text:
        return "walk"
    if "ジョギ" in kind or "jog" in text:
        return "jog"
    if "ラン" in kind or "run" in text:
        return "run"
    if "自転車" in kind or "バイク" in kind or "bike" in text:
        return "bike"
    if "筋" in kind or "ジム" in kind:
        return "gym"
    return "walk"  # よく分からない時は軽い有酸素扱い

def calc_exercise_calories(activity_key: str, minutes: int, steps: int = 0,
                           weight_kg: float = USER_WEIGHT_KG) -> int:
    """
    MET * 体重 * 時間 + 歩数からざっくり計算
    ・MET 部分：分 → 時間にして計算
    ・歩数部分：1歩あたり 0.04 kcal 程度で加算（目安）
    """
    met = MET_VALUES.get(activity_key, 3.0)
    hours = minutes / 60.0
    kcal_met = met * weight_kg * hours
    kcal_steps = steps * 0.04
    return int(kcal_met + kcal_steps)

# -----------------  ルート定義  -----------------

@app.route("/")
def index():
    return render_template("index.html", title="ホーム")


@app.route("/meals", methods=["GET", "POST"])
def meals():
    if request.method == "POST":
        meal = request.form.get("meal")
        calorie = request.form.get("calorie")
        date_str = request.form.get("date")  # yyyy-mm-dd

        if not meal or not calorie or not date_str:
            flash("入力が不足しています。")
            return redirect(url_for("meals"))

        try:
            calorie_val = int(calorie)
        except ValueError:
            flash("カロリーは数値で入力してください。")
            return redirect(url_for("meals"))

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            dt = datetime.now()

        record = MealRecord(meal=meal, calorie=calorie_val, date=dt)
        db.session.add(record)
        db.session.commit()
        flash("食事記録を保存しました。")
        return redirect(url_for("meals"))

    # GET のとき：一覧表示（新しい順）
    records = MealRecord.query.order_by(MealRecord.date.desc()).all()
    default_date = date.today().strftime("%Y-%m-%d")
    return render_template(
        "meals.html",
        title="食事記録",
        records=records,
        default_date=default_date,
    )


@app.route("/exercises", methods=["GET", "POST"])
def exercises():
    if request.method == "POST":
        kind = request.form.get("kind", "").strip()
        minutes_str = request.form.get("minutes", "").strip()
        burned_str = request.form.get("burned", "").strip()
        steps_str = request.form.get("steps", "").strip()
        date_str = request.form.get("date", "").strip()

        if not kind or not date_str:
            flash("運動名と日付は必須です。")
            return redirect(url_for("exercises"))

        # 分・歩数は未入力なら0扱い
        try:
            minutes_val = int(minutes_str) if minutes_str else 0
            steps_val = int(steps_str) if steps_str else 0
        except ValueError:
            flash("分と歩数は数値で入力してください。")
            return redirect(url_for("exercises"))

        # 消費カロリー：入力されていればそのまま、空なら自動計算
        if burned_str:
            try:
                burned_val = int(burned_str)
            except ValueError:
                flash("消費カロリーは数値で入力してください。")
                return redirect(url_for("exercises"))
        else:
            key = guess_activity_key(kind)
            burned_val = calc_exercise_calories(key, minutes_val, steps_val)

        # 日付 → datetime 変換
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            dt = datetime.now()

        record = ExerciseRecord(
            kind=kind,
            minutes=minutes_val,
            burned=burned_val,
            steps=steps_val,
            date=dt
        )
        db.session.add(record)
        db.session.commit()
        flash(f"運動記録を保存しました。（推定 {burned_val} kcal）")
        return redirect(url_for("exercises"))

    # GET のとき：一覧表示
    records = ExerciseRecord.query.order_by(ExerciseRecord.date.desc()).all()
    default_date = date.today().strftime("%Y-%m-%d")
    return render_template(
        "exercises.html",
        title="運動記録",
        records=records,
        default_date=default_date,
    )


@app.route("/reports")
def reports():
    # --- 全期間合計 ---
    total_in = (
        db.session.query(func.coalesce(func.sum(MealRecord.calorie), 0))
        .scalar()
        or 0
    )
    total_out = (
        db.session.query(func.coalesce(func.sum(ExerciseRecord.burned), 0))
        .scalar()
        or 0
    )
    net = total_in - total_out

    # --- 直近7日（今日を含む） ---
    today = date.today()
    start_day = today - timedelta(days=6)

    # 日付範囲 → datetime 範囲（00:00～翌日00:00）
    start_dt = datetime.combine(start_day, time.min)
    end_dt = datetime.combine(today + timedelta(days=1), time.min)

    # 食事：日別合計
    meal_rows = (
        db.session.query(
            func.date(MealRecord.date).label("d"),
            func.coalesce(func.sum(MealRecord.calorie), 0),
        )
        .filter(MealRecord.date >= start_dt, MealRecord.date < end_dt)
        .group_by("d")
        .all()
    )
    meal_by_date = {row[0]: row[1] for row in meal_rows}  # "YYYY-MM-DD": kcal

    # 運動：日別合計
    ex_rows = (
        db.session.query(
            func.date(ExerciseRecord.date).label("d"),
            func.coalesce(func.sum(ExerciseRecord.burned), 0),
        )
        .filter(ExerciseRecord.date >= start_dt, ExerciseRecord.date < end_dt)
        .group_by("d")
        .all()
    )
    ex_by_date = {row[0]: row[1] for row in ex_rows}

    labels = []
    in_data = []
    out_data = []
    daily_rows = []  # テーブル用 [(日付, {"in": , "out": }), ...]

    for i in range(7):
        d = start_day + timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        v_in = meal_by_date.get(d_str, 0)
        v_out = ex_by_date.get(d_str, 0)

        labels.append(d_str)
        in_data.append(v_in)
        out_data.append(v_out)
        daily_rows.append((d_str, {"in": v_in, "out": v_out}))

    # 今日の進捗
    today_str = today.strftime("%Y-%m-%d")
    today_in = meal_by_date.get(today_str, 0)
    if DAILY_GOAL > 0:
        progress = int(min(today_in / DAILY_GOAL * 100, 200))  # 上限を200%に
    else:
        progress = 0

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


if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # 初回起動時にテーブル作成
    app.run(host="0.0.0.0", port=5000, debug=True)



#aaaaaa
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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
    date = db.Column(db.DateTime, default=datetime.now)

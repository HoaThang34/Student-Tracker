from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import datetime

db = SQLAlchemy()


class ClassRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(50), nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Teacher(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    school_name = db.Column(db.String(150), default="THPT Chuyên Nguyễn Tất Thành")
    main_class = db.Column(db.String(20), default="12 Tin")
    dob = db.Column(db.String(20))


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    student_class = db.Column(db.String(20), nullable=False)
    current_score = db.Column(db.Integer, default=100)


class ViolationType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    points_deducted = db.Column(db.Integer, nullable=False)


class Violation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    violation_type_name = db.Column(db.String(200), nullable=False)
    points_deducted = db.Column(db.Integer, nullable=False)
    date_committed = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    week_number = db.Column(db.Integer, default=1)
    student = db.relationship('Student', backref=db.backref('violations', lazy=True))


class WeeklyArchive(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_number = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=True)
    student_name = db.Column(db.String(100))
    student_code = db.Column(db.String(50))
    student_class = db.Column(db.String(20))
    final_score = db.Column(db.Integer)
    total_deductions = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.String(200))
    num_tx_columns = db.Column(db.Integer, default=3)
    num_gk_columns = db.Column(db.Integer, default=1)
    num_hk_columns = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    grade_type = db.Column(db.String(10), nullable=False)
    column_index = db.Column(db.Integer, default=1)
    score = db.Column(db.Float, nullable=False)
    semester = db.Column(db.Integer, nullable=False)
    school_year = db.Column(db.String(20))
    date_recorded = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    student = db.relationship('Student', backref=db.backref('grades', lazy=True, cascade='all, delete-orphan'))
    subject = db.relationship('Subject', backref=db.backref('grades', lazy=True, cascade='all, delete-orphan'))


class ChatConversation(db.Model):
    """Model lưu trữ lịch sử hội thoại chatbot với context awareness"""
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'user' hoặc 'assistant'
    message = db.Column(db.Text, nullable=False)
    context_data = db.Column(db.Text, nullable=True)  # JSON metadata (student_id, etc.)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, index=True)
    
    teacher = db.relationship('Teacher', backref=db.backref('chat_history', lazy=True))
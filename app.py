
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import os
import json
import datetime
import base64
import requests
import re
import unicodedata
from io import BytesIO
from flask import send_file
import pandas as pd

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, desc, or_
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)

from models import db, Student, Violation, ViolationType, Teacher, SystemConfig, ClassRoom, WeeklyArchive, Subject, Grade


basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, "templates")

app = Flask(__name__, template_folder=template_dir)

app.config["SECRET_KEY"] = "chia-khoa-bi-mat-cua-ban-ne-123456"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() 
GEMINI_MODEL = "gemini-2.5-flash-lite"  
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Vui lòng đăng nhập hệ thống."
login_manager.login_message_category = "error"

UPLOAD_FOLDER = os.path.join(basedir, "uploads")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Teacher, int(user_id))

@app.context_processor
def inject_global_data():
    try:
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(week_cfg.value) if week_cfg else 1
        classes = [c.name for c in ClassRoom.query.order_by(ClassRoom.name).all()]
    except:
        current_week = 1
        classes = []
    return dict(current_week_number=current_week, all_classes=classes)


def get_current_iso_week():
    today = datetime.datetime.now()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week}"

def format_date_vn(date_obj):
    return date_obj.strftime('%d/%m')

def save_weekly_archive(week_num):
    try:
        WeeklyArchive.query.filter_by(week_number=week_num).delete()
        students = Student.query.all()
        for s in students:
            deductions = db.session.query(func.sum(Violation.points_deducted))\
                .filter(Violation.student_id == s.id, Violation.week_number == week_num)\
                .scalar() or 0
            archive = WeeklyArchive(
                week_number=week_num, student_id=s.id, student_name=s.name,
                student_code=s.student_code, student_class=s.student_class,
                final_score=s.current_score, total_deductions=deductions
            )
            db.session.add(archive)
        db.session.commit()
        return True
    except Exception as e:
        print(f"Archive Error: {e}")
        db.session.rollback()
        return False

def check_and_run_auto_reset():
    try:
        current_real_week_id = get_current_iso_week()
        last_reset_cfg = SystemConfig.query.filter_by(key="last_reset_week_id").first()
        if not last_reset_cfg:
            db.session.add(SystemConfig(key="last_reset_week_id", value=current_real_week_id))
            db.session.commit()
            return False
        if current_real_week_id != last_reset_cfg.value:
            week_cfg = SystemConfig.query.filter_by(key="current_week").first()
            if week_cfg:
                current_w = int(week_cfg.value)
                save_weekly_archive(current_w)
                week_cfg.value = str(current_w + 1)
            for s in Student.query.all(): s.current_score = 100
            last_reset_cfg.value = current_real_week_id
            db.session.commit()
            return True
    except: pass
    return False

def _call_gemini(prompt, image_path=None, is_json=False):
    if not GEMINI_API_KEY:
        return None, "Chưa cấu hình GEMINI_API_KEY."

    headers = {"Content-Type": "application/json"}
    parts = [{"text": prompt}]

    if image_path:
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": encoded_string}})
        except Exception as e:
            return None, f"Lỗi đọc file ảnh: {str(e)}"

    payload = {"contents": [{"parts": parts}]}
    if is_json:
        payload["generationConfig"] = {"response_mime_type": "application/json"}

    try:
        response = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            result = response.json()
            try:
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                if is_json: return json.loads(text), None
                return text, None
            except: return None, "Lỗi parse dữ liệu từ AI."
        return None, f"Lỗi API ({response.status_code})"
    except Exception as e:
        return None, f"Lỗi kết nối: {str(e)}"


@app.route('/')
def welcome(): return render_template('welcome.html')

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = Teacher.query.filter_by(username=request.form["username"]).first()
        if user and user.password == request.form["password"]:
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Sai thông tin đăng nhập!", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.route('/scoreboard')
@login_required
def index():
    search = request.args.get('search', '').strip()
    selected_class = request.args.get('class_select', '').strip()
    q = Student.query
    if selected_class: q = q.filter_by(student_class=selected_class)
    if search: q = q.filter(or_(Student.name.ilike(f"%{search}%"), Student.student_code.ilike(f"%{search}%")))
    students = q.order_by(Student.student_code.asc()).all()
    return render_template('index.html', students=students, search_query=search, selected_class=selected_class)

@app.route("/dashboard")
@login_required
def dashboard():
    check_and_run_auto_reset()
    s_class = request.args.get("class_select")
    q = Student.query.filter_by(student_class=s_class) if s_class else Student.query
    c_tot = q.filter(Student.current_score >= 90).count()
    c_kha = q.filter(Student.current_score >= 70, Student.current_score < 90).count()
    c_tb = q.filter(Student.current_score < 70).count()
    vios_q = db.session.query(Violation.violation_type_name, func.count(Violation.violation_type_name).label("c"))
    if s_class: vios_q = vios_q.join(Student).filter(Student.student_class == s_class)
    top = vios_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
    return render_template("dashboard.html", selected_class=s_class, 
                           pie_labels=json.dumps(["Tốt", "Khá", "Cần cố gắng"]), 
                           pie_data=json.dumps([c_tot, c_kha, c_tb]), 
                           bar_labels=json.dumps([n for n, _ in top]), 
                           bar_data=json.dumps([c for _, c in top]))


@app.route("/add_violation", methods=["GET", "POST"])
@login_required
def add_violation():
    if request.method == "POST":
        students_json = request.form.get("students_list")
        rule_id = request.form.get("rule_id")
        
        try:
            rule = db.session.get(ViolationType, int(rule_id)) if rule_id else None
        except: rule = None

        if not rule:
            flash("Vui lòng chọn lỗi vi phạm!", "error")
            return redirect(url_for("add_violation"))

        w_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(w_cfg.value) if w_cfg else 1
        count = 0

        if students_json:
            try:
                student_codes = json.loads(students_json)
                for code in student_codes:
                    if not code: continue
                    s = Student.query.filter_by(student_code=str(code).strip()).first()
                    if s:
                        s.current_score = (s.current_score or 100) - rule.points_deducted
                        db.session.add(Violation(student_id=s.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                        count += 1
                db.session.commit()
                flash(f"Đã trừ điểm {count} học sinh.", "success")
            except Exception as e:
                db.session.rollback()
                flash(f"Lỗi: {e}", "error")

        else:
            s_name = request.form.get("student_name")
            s_code = request.form.get("student_code")
            student = None
            if s_code: student = Student.query.filter_by(student_code=s_code).first()
            if not student and s_name: student = Student.query.filter(Student.name.ilike(s_name)).first()

            if student:
                student.current_score = (student.current_score or 100) - rule.points_deducted
                db.session.add(Violation(student_id=student.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                db.session.commit()
                flash(f"Đã trừ điểm em {student.name}.", "success")
            else:
                flash("Không tìm thấy học sinh.", "error")
        
        return redirect(url_for("add_violation"))

    return render_template("add_violation.html", rules=ViolationType.query.all())

@app.route("/upload_ocr", methods=["POST"])
@login_required
def upload_ocr():
    """AI đọc tên + lớp từ thẻ, sau đó fuzzy matching trong CSDL."""
    uploaded_files = request.files.getlist("files[]")
    if not uploaded_files: return jsonify({"error": "Chưa chọn file."})

    results = []
    
    prompt = """
    Hãy đọc THÔNG TIN HỌC SINH từ thẻ trong ảnh này.
    
    Trích xuất các thông tin sau (nếu có):
    - Tên học sinh (họ và tên đầy đủ)
    - Lớp (ví dụ: 12 Tin, 11A1, 10B, 12TOAN)
    - Mã số học sinh (nếu có, ví dụ: 12TIN-001, HS123)
    
    Trả về JSON với format:
    {
        "name": "tên đầy đủ của học sinh",
        "class": "tên lớp",
        "student_code": "mã số nếu có, nếu không có để rỗng"
    }
    
    Lưu ý: 
    - Tên có thể có hoặc không có dấu
    - Lớp có thể viết liền hoặc có dấu cách (12Tin, 12 Tin)
    - Nếu không đọc được thông tin nào, trả về chuỗi rỗng ""
    """

    def normalize_text(text):
        """Chuẩn hóa text: loại bỏ dấu cách thừa, chuyển thành chữ thường"""
        import unicodedata
        if not text:
            return ""
        # Loại bỏ dấu cách thừa
        text = " ".join(text.split())
        # Chuyển thành chữ thường
        return text.lower().strip()
    
    def remove_accents(text):
        """Loại bỏ dấu tiếng Việt"""
        if not text:
            return ""
        # Chuẩn hóa Unicode về dạng NFD (tách dấu)
        nfd = unicodedata.normalize('NFD', text)
        # Loại bỏ các ký tự dấu
        return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    
    def fuzzy_match_students(ocr_name, ocr_class, ocr_code):
        """Tìm học sinh phù hợp nhất với thông tin OCR"""
        candidates = []
        
        # Chuẩn hóa input
        ocr_name_norm = normalize_text(ocr_name)
        ocr_name_no_accent = remove_accents(ocr_name_norm)
        ocr_class_norm = normalize_text(ocr_class)
        
        # Lấy tất cả học sinh
        all_students = Student.query.all()
        
        for student in all_students:
            score = 0
            reasons = []
            
            # So sánh mã số nếu có
            if ocr_code and student.student_code:
                if ocr_code.upper() == student.student_code.upper():
                    score += 100  # Match chính xác mã số = điểm cao nhất
                    reasons.append("Mã số khớp chính xác")
                elif ocr_code.upper() in student.student_code.upper() or student.student_code.upper() in ocr_code.upper():
                    score += 50
                    reasons.append("Mã số khớp một phần")
            
            # So sánh lớp
            student_class_norm = normalize_text(student.student_class)
            if ocr_class_norm and student_class_norm:
                # Loại bỏ khoảng cách để so sánh (12Tin == 12 Tin)
                ocr_class_no_space = ocr_class_norm.replace(" ", "")
                student_class_no_space = student_class_norm.replace(" ", "")
                
                if ocr_class_no_space == student_class_no_space:
                    score += 40
                    reasons.append("Lớp khớp chính xác")
                elif ocr_class_no_space in student_class_no_space or student_class_no_space in ocr_class_no_space:
                    score += 20
                    reasons.append("Lớp khớp một phần")
            
            # So sánh tên
            student_name_norm = normalize_text(student.name)
            student_name_no_accent = remove_accents(student_name_norm)
            
            if ocr_name_norm and student_name_norm:
                # So sánh có dấu
                if ocr_name_norm == student_name_norm:
                    score += 60
                    reasons.append("Tên khớp chính xác (có dấu)")
                # So sánh không dấu
                elif ocr_name_no_accent == student_name_no_accent:
                    score += 50
                    reasons.append("Tên khớp chính xác (không dấu)")
                # So sánh chứa
                elif ocr_name_norm in student_name_norm or student_name_norm in ocr_name_norm:
                    score += 30
                    reasons.append("Tên khớp một phần (có dấu)")
                elif ocr_name_no_accent in student_name_no_accent or student_name_no_accent in ocr_name_no_accent:
                    score += 25
                    reasons.append("Tên khớp một phần (không dấu)")
                # Sử dụng difflib để tính similarity
                else:
                    from difflib import SequenceMatcher
                    ratio = SequenceMatcher(None, ocr_name_no_accent, student_name_no_accent).ratio()
                    if ratio > 0.7:  # 70% giống nhau
                        score += int(ratio * 30)
                        reasons.append(f"Tên tương tự {int(ratio*100)}%")
            
            if score > 0:
                candidates.append({
                    "student": student,
                    "score": score,
                    "reasons": reasons
                })
        
        # Sắp xếp theo điểm giảm dần
        candidates.sort(key=lambda x: x["score"], reverse=True)
        
        # Trả về top 3
        return candidates[:3]

    for f in uploaded_files:
        if f.filename == '': continue
        p = os.path.join(UPLOAD_FOLDER, f.filename)
        f.save(p)
        
        data, error = _call_gemini(prompt, image_path=p, is_json=True)
        if os.path.exists(p): os.remove(p)

        if data:
            ocr_name = str(data.get("name", "")).strip()
            ocr_class = str(data.get("class", "")).strip()
            ocr_code = str(data.get("student_code", "")).strip().upper()
            
            # Fuzzy matching
            matches = fuzzy_match_students(ocr_name, ocr_class, ocr_code)
            
            if matches:
                # Lấy kết quả tốt nhất
                best_match = matches[0]
                student = best_match["student"]
                
                item = {
                    "file_name": f.filename,
                    "ocr_data": {
                        "name": ocr_name,
                        "class": ocr_class,
                        "code": ocr_code
                    },
                    "found": True,
                    "confidence": best_match["score"],
                    "match_reasons": best_match["reasons"],
                    "db_info": {
                        "name": student.name,
                        "code": student.student_code,
                        "class": student.student_class
                    },
                    "alternatives": [
                        {
                            "name": m["student"].name,
                            "code": m["student"].student_code,
                            "class": m["student"].student_class,
                            "confidence": m["score"],
                            "reasons": m["reasons"]
                        }
                        for m in matches[1:3]  # Top 2-3
                    ] if len(matches) > 1 else []
                }
            else:
                item = {
                    "file_name": f.filename,
                    "ocr_data": {
                        "name": ocr_name,
                        "class": ocr_class,
                        "code": ocr_code
                    },
                    "found": False,
                    "db_info": None
                }
            
            results.append(item)
        else:
            results.append({"file_name": f.filename, "error": error or "Không đọc được thông tin từ thẻ"})

    return jsonify({"results": results})

@app.route("/batch_violation", methods=["POST"])
def batch_violation(): return redirect(url_for('add_violation'))


@app.route("/manage_students")
@login_required
def manage_students():
    students = Student.query.order_by(Student.student_code.asc()).all()
    return render_template("manage_students.html", students=students)

@app.route("/add_student", methods=["POST"])
@login_required
def add_student():
    db.session.add(Student(name=request.form["student_name"], student_code=request.form["student_code"], student_class=request.form["student_class"]))
    db.session.commit()
    flash("Thêm học sinh thành công", "success")
    return redirect(url_for("manage_students"))

@app.route("/delete_student/<int:student_id>", methods=["POST"])
@login_required
def delete_student(student_id):
    s = db.session.get(Student, student_id)
    if s:
        Violation.query.filter_by(student_id=student_id).delete()
        db.session.delete(s)
        db.session.commit()
        flash("Đã xóa học sinh", "success")
    return redirect(url_for("manage_students"))

@app.route("/edit_student/<int:student_id>", methods=["GET", "POST"])
@login_required
def edit_student(student_id):
    s = db.session.get(Student, student_id)
    if not s:
        flash("Không tìm thấy học sinh", "error")
        return redirect(url_for("manage_students"))
        
    if request.method == "POST":
        s.name = request.form["student_name"]
        s.student_code = request.form["student_code"]
        s.student_class = request.form["student_class"]
        db.session.commit()
        flash("Cập nhật thành công", "success")
        return redirect(url_for("manage_students"))
        
    return render_template("edit_student.html", student=s)

@app.route("/add_class", methods=["POST"])
@login_required
def add_class():
    if not ClassRoom.query.filter_by(name=request.form["class_name"]).first():
        db.session.add(ClassRoom(name=request.form["class_name"]))
        db.session.commit()
    return redirect(url_for("manage_students"))

@app.route("/manage_rules", methods=["GET", "POST"])
@login_required
def manage_rules():
    if request.method == "POST":
        db.session.add(ViolationType(name=request.form["rule_name"], points_deducted=int(request.form["points"])))
        db.session.commit()
        flash("Đã thêm lỗi vi phạm", "success")
        return redirect(url_for("manage_rules"))
    return render_template("manage_rules.html", rules=ViolationType.query.all())

@app.route("/delete_rule/<int:rule_id>", methods=["POST"])
@login_required
def delete_rule(rule_id):
    r = db.session.get(ViolationType, rule_id)
    if r: db.session.delete(r); db.session.commit()
    return redirect(url_for("manage_rules"))

@app.route("/edit_rule/<int:rule_id>", methods=["GET", "POST"])
@login_required
def edit_rule(rule_id):
    r = db.session.get(ViolationType, rule_id)
    if request.method == "POST":
        r.name = request.form["rule_name"]
        r.points_deducted = int(request.form["points"])
        db.session.commit()
        flash("Đã sửa lỗi vi phạm", "success")
        return redirect(url_for("manage_rules"))
    return render_template("edit_rule.html", rule=r)

@app.route("/chatbot")
@login_required
def chatbot():
    return render_template("chatbot.html")

@app.route("/api/chatbot", methods=["POST"])
@login_required
def api_chatbot():
    msg = (request.json.get("message") or "").strip()
    
    # Tìm kiếm học sinh từ CSDL
    s_list = Student.query.filter(
        or_(
            Student.name.ilike(f"%{msg}%"), 
            Student.student_code.ilike(f"%{msg}%")
        )
    ).limit(5).all()
    
    # Nếu tìm thấy học sinh
    if s_list:
        # Nếu có nhiều kết quả - hiển thị danh sách để chọn
        if len(s_list) > 1:
            response = f"**Tìm thấy {len(s_list)} học sinh:**\n\n"
            buttons = []
            
            for s in s_list:
                response += f"• {s.name} ({s.student_code}) - Lớp {s.student_class}\n"
                buttons.append({
                    "label": f"{s.name} - {s.student_class}",
                    "payload": f"{s.name}"
                })
            
            response += "\n*Nhấn vào tên để xem chi tiết*"
            return jsonify({"response": response.strip(), "buttons": buttons})
        
        # Nếu chỉ có 1 kết quả - sử dụng AI để phân tích
        student = s_list[0]
        
        # Thu thập dữ liệu từ CSDL
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(week_cfg.value) if week_cfg else 1
        semester = 1
        school_year = "2023-2024"
        
        # Lấy điểm học tập
        grades = Grade.query.filter_by(
            student_id=student.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        grades_data = {}
        if grades:
            grades_by_subject = {}
            for grade in grades:
                if grade.subject_id not in grades_by_subject:
                    grades_by_subject[grade.subject_id] = {
                        'subject_name': grade.subject.name,
                        'TX': [],
                        'GK': [],
                        'HK': []
                    }
                grades_by_subject[grade.subject_id][grade.grade_type].append(grade.score)
            
            for subject_id, data in grades_by_subject.items():
                subject_name = data['subject_name']
                avg_score = None
                
                if data['TX'] and data['GK'] and data['HK']:
                    avg_tx = sum(data['TX']) / len(data['TX'])
                    avg_gk = sum(data['GK']) / len(data['GK'])
                    avg_hk = sum(data['HK']) / len(data['HK'])
                    avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
                    
                    grades_data[subject_name] = {
                        'TX': round(avg_tx, 1),
                        'GK': round(avg_gk, 1),
                        'HK': round(avg_hk, 1),
                        'TB': avg_score
                    }
        
        # Lấy vi phạm
        violations = Violation.query.filter_by(student_id=student.id).order_by(Violation.date_committed.desc()).all()
        violations_data = []
        if violations:
            for v in violations[:5]:
                violations_data.append({
                    'type': v.violation_type_name,
                    'points': v.points_deducted,
                    'date': v.date_committed.strftime('%d/%m/%Y')
                })
        
        # Tạo context cho AI
        context = f"""THÔNG TIN HỌC SINH:
- Họ tên: {student.name}
- Mã số: {student.student_code}
- Lớp: {student.student_class}
- Điểm hành vi hiện tại: {student.current_score}/100

ĐIỂM HỌC TẬP (Học kỳ 1):
"""
        if grades_data:
            for subject, scores in grades_data.items():
                context += f"- {subject}: TX={scores['TX']}, GK={scores['GK']}, HK={scores['HK']}, TB={scores['TB']}\n"
        else:
            context += "- Chưa có dữ liệu điểm\n"
        
        context += f"\nVI PHẠM:\n"
        if violations_data:
            context += f"- Tổng số: {len(violations)} lần\n"
            context += "- Chi tiết gần nhất:\n"
            for v in violations_data:
                context += f"  + {v['type']} (-{v['points']}đ) - {v['date']}\n"
        else:
            context += "- Không có vi phạm\n"
        
        # Gọi AI để phân tích
        prompt = f"""{context}

Câu hỏi của người dùng: "{msg}"

Bạn là trợ lý ảo của giáo viên chủ nhiệm. Hãy phân tích thông tin trên và:
1. Đưa ra nhận xét tổng quan về học sinh này (điểm mạnh, điểm yếu)
2. Phân tích kết quả học tập (môn nào tốt, môn nào cần cải thiện)
3. Nhận xét về hành vi và kỷ luật
4. Đưa ra đề xuất cụ thể để giúp học sinh phát triển tốt hơn

Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp. Sử dụng emoji phù hợp và định dạng markdown (** cho chữ đậm, xuống dòng rõ ràng).
Bắt đầu với tiêu đề "📋 Phân tích về em {student.name}"
"""
        
        ai_response, err = _call_gemini(prompt)
        
        if ai_response:
            # Tạo các nút hành động
            buttons = [
                {"label": "📊 Xem học bạ", "payload": f"/student/{student.id}/transcript"},
                {"label": "📈 Chi tiết điểm", "payload": f"/student/{student.id}"},
                {"label": "📜 Lịch sử vi phạm", "payload": f"/student/{student.id}/violations_timeline"}
            ]
            
            return jsonify({"response": ai_response.strip(), "buttons": buttons})
        else:
            # Fallback nếu AI lỗi - hiển thị dữ liệu raw
            response = f"**📋 Thông tin học sinh**\n\n"
            response += f"**Họ tên:** {student.name}\n"
            response += f"**Mã số:** {student.student_code}\n"
            response += f"**Lớp:** {student.student_class}\n"
            response += f"**Điểm hành vi:** {student.current_score}/100\n\n"
            
            if grades_data:
                response += "**📚 Điểm học tập (HK1):**\n"
                for subject, scores in grades_data.items():
                    response += f"• {subject}: TX={scores['TX']}, GK={scores['GK']}, HK={scores['HK']}, TB={scores['TB']}\n"
                response += "\n"
            
            if violations_data:
                response += f"**⚠️ Vi phạm:** {len(violations)} lần\n"
                response += "**Gần nhất:**\n"
                for v in violations_data[:3]:
                    response += f"• {v['type']} (-{v['points']}đ) - {v['date']}\n"
            else:
                response += "**✅ Không có vi phạm**\n"
            
            buttons = [
                {"label": "📊 Xem học bạ", "payload": f"/student/{student.id}/transcript"},
                {"label": "📈 Chi tiết điểm", "payload": f"/student/{student.id}"},
                {"label": "📜 Lịch sử vi phạm", "payload": f"/student/{student.id}/violations_timeline"}
            ]
            
            return jsonify({"response": response.strip(), "buttons": buttons})
    
    # Nếu không tìm thấy học sinh, sử dụng AI để trả lời
    prompt = f"""Bạn là trợ lý ảo của hệ thống quản lý học sinh. 
    Người dùng hỏi: "{msg}"
    
    Trả lời ngắn gọn, thân thiện bằng tiếng Việt. Nếu họ hỏi về tra cứu học sinh, hướng dẫn nhập tên hoặc mã số học sinh.
    Nếu họ hỏi về chức năng hệ thống, giải thích rõ ràng.
    Sử dụng emoji phù hợp và định dạng markdown."""
    
    ans, err = _call_gemini(prompt)
    return jsonify({"response": ans or "Xin lỗi, tôi chưa hiểu câu hỏi của bạn. Bạn có thể nhập tên hoặc mã số học sinh để tra cứu thông tin."})

@app.route("/profile")
@login_required
def profile(): return render_template("profile.html", user=current_user)

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        return redirect(url_for("profile"))
    return render_template("edit_profile.html", user=current_user)

@app.route("/history")
@login_required
def history():
    weeks = [w[0] for w in db.session.query(WeeklyArchive.week_number).distinct().order_by(WeeklyArchive.week_number.desc()).all()]
    sel = request.args.get('week', type=int) or (weeks[0] if weeks else None)
    archives = WeeklyArchive.query.filter_by(week_number=sel).all() if sel else []
    return render_template("history.html", weeks=weeks, selected_week=sel, archives=archives, class_rankings=[])

@app.route("/weekly_report")
@login_required
def weekly_report():
    w = int(SystemConfig.query.filter_by(key="current_week").first().value)
    sel = request.args.get('week', w, type=int)
    vios = db.session.query(Violation, Student).join(Student).filter(Violation.week_number == sel).all()
    
    total_errors = len(vios)
    total_points = sum(v.Violation.points_deducted for v in vios)
    
    all_classes = ClassRoom.query.all()
    class_data = []
    
    for cls in all_classes:
        students_in_class = Student.query.filter_by(student_class=cls.name).all()
        
        if not students_in_class:
            continue
        
        weekly_deduct = db.session.query(func.sum(Violation.points_deducted))\
            .join(Student)\
            .filter(Student.student_class == cls.name, Violation.week_number == sel)\
            .scalar() or 0
        
        avg_score = 100 - weekly_deduct
        
        class_data.append({
            'name': cls.name,
            'avg_score': round(avg_score, 1),
            'weekly_deduct': round(weekly_deduct, 1)
        })
    
    class_rankings = sorted(class_data, key=lambda x: x['avg_score'], reverse=True)
    
    return render_template("weekly_report.html", violations=vios, selected_week=sel, system_week=w, total_points=total_points, total_errors=total_errors, class_rankings=class_rankings)


@app.route("/export_report")
@login_required
def export_report():
    week = request.args.get('week', type=int)
    if not week: return "Vui lòng chọn tuần", 400
    violations = db.session.query(Violation, Student).join(Student).filter(Violation.week_number == week).all()
    data = [{"Tên": r.Student.name, "Lớp": r.Student.student_class, "Lỗi": r.Violation.violation_type_name} for r in violations]
    df = pd.read_json(json.dumps(data)) if data else pd.DataFrame([{"Thông báo": "Trống"}])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"Report_{week}.xlsx", as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/student/<int:student_id>")
@login_required
def student_detail(student_id):
    s = db.session.get(Student, student_id)
    if not s: return redirect(url_for('index'))
    pts, lbls, curr = [100], ["Start"], 100
    for v in sorted(s.violations, key=lambda x: x.date_committed):
        curr -= v.points_deducted
        pts.append(curr); lbls.append(format_date_vn(v.date_committed))
    return render_template("student_detail.html", student=s, chart_labels=json.dumps(lbls), chart_scores=json.dumps(pts))

@app.route("/api/generate_report/<int:student_id>", methods=["POST"])
@login_required
def generate_report(student_id):
    s = db.session.get(Student, student_id)
    ans, _ = _call_gemini(f"Nhận xét HS {s.name}. Điểm: {s.current_score}")
    return jsonify({"report": ans})


@app.route("/manage_subjects", methods=["GET", "POST"])
@login_required
def manage_subjects():
    """Quản lý danh sách môn học"""
    if request.method == "POST":
        name = request.form.get("subject_name", "").strip()
        code = request.form.get("subject_code", "").strip().upper()
        description = request.form.get("description", "").strip()
        num_tx = int(request.form.get("num_tx_columns", 3))
        num_gk = int(request.form.get("num_gk_columns", 1))
        num_hk = int(request.form.get("num_hk_columns", 1))
        
        if not name or not code:
            flash("Vui lòng nhập tên và mã môn học!", "error")
            return redirect(url_for("manage_subjects"))
        
        if Subject.query.filter_by(code=code).first():
            flash("Mã môn học đã tồn tại!", "error")
            return redirect(url_for("manage_subjects"))
        
        subject = Subject(
            name=name, 
            code=code, 
            description=description,
            num_tx_columns=num_tx,
            num_gk_columns=num_gk,
            num_hk_columns=num_hk
        )
        db.session.add(subject)
        db.session.commit()
        flash(f"Đã thêm môn {name}", "success")
        return redirect(url_for("manage_subjects"))
    
    subjects = Subject.query.order_by(Subject.name).all()
    return render_template("manage_subjects.html", subjects=subjects)

@app.route("/edit_subject/<int:subject_id>", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id):
    """Sửa thông tin môn học"""
    subject = db.session.get(Subject, subject_id)
    if not subject:
        flash("Không tìm thấy môn học!", "error")
        return redirect(url_for("manage_subjects"))
    
    if request.method == "POST":
        subject.name = request.form.get("subject_name", "").strip()
        subject.code = request.form.get("subject_code", "").strip().upper()
        subject.description = request.form.get("description", "").strip()
        subject.num_tx_columns = int(request.form.get("num_tx_columns", 3))
        subject.num_gk_columns = int(request.form.get("num_gk_columns", 1))
        subject.num_hk_columns = int(request.form.get("num_hk_columns", 1))
        
        db.session.commit()
        flash("Đã cập nhật môn học!", "success")
        return redirect(url_for("manage_subjects"))
    
    return render_template("edit_subject.html", subject=subject)

@app.route("/delete_subject/<int:subject_id>", methods=["POST"])
@login_required
def delete_subject(subject_id):
    """Xóa môn học"""
    subject = db.session.get(Subject, subject_id)
    if subject:
        db.session.delete(subject)
        db.session.commit()
        flash("Đã xóa môn học!", "success")
    return redirect(url_for("manage_subjects"))

@app.route("/manage_grades")
@login_required
def manage_grades():
    """Danh sách học sinh để chọn nhập điểm"""
    search = request.args.get('search', '').strip()
    selected_class = request.args.get('class_select', '').strip()
    
    q = Student.query
    if selected_class:
        q = q.filter_by(student_class=selected_class)
    if search:
        q = q.filter(or_(
            Student.name.ilike(f"%{search}%"),
            Student.student_code.ilike(f"%{search}%")
        ))
    
    students = q.order_by(Student.student_code.asc()).all()
    return render_template("manage_grades.html", students=students, search_query=search, selected_class=selected_class)

@app.route("/student_grades/<int:student_id>", methods=["GET", "POST"])
@login_required
def student_grades(student_id):
    """Xem và nhập điểm cho học sinh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_grades"))
    
    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        grade_type = request.form.get("grade_type")
        column_index = int(request.form.get("column_index", 1))
        score = request.form.get("score")
        semester = int(request.form.get("semester", 1))
        school_year = request.form.get("school_year", "2023-2024")
        
        if not all([subject_id, grade_type, score]):
            flash("Vui lòng điền đầy đủ thông tin!", "error")
            return redirect(url_for("student_grades", student_id=student_id))
        
        try:
            score_float = float(score)
            if score_float < 0 or score_float > 10:
                flash("Điểm phải từ 0 đến 10!", "error")
                return redirect(url_for("student_grades", student_id=student_id))
        except ValueError:
            flash("Điểm không hợp lệ!", "error")
            return redirect(url_for("student_grades", student_id=student_id))
        
        existing = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject_id,
            grade_type=grade_type,
            column_index=column_index,
            semester=semester,
            school_year=school_year
        ).first()
        
        if existing:
            existing.score = score_float
            flash("Đã cập nhật điểm!", "success")
        else:
            grade = Grade(
                student_id=student_id,
                subject_id=subject_id,
                grade_type=grade_type,
                column_index=column_index,
                score=score_float,
                semester=semester,
                school_year=school_year
            )
            db.session.add(grade)
            flash("Đã thêm điểm!", "success")
        
        db.session.commit()
        return redirect(url_for("student_grades", student_id=student_id))
    
    subjects = Subject.query.order_by(Subject.name).all()
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    grades = Grade.query.filter_by(
        student_id=student_id,
        semester=semester,
        school_year=school_year
    ).all()
    
    grades_by_subject = {}
    for subject in subjects:
        subject_grades = {
            'TX': {},
            'GK': {},
            'HK': {}
        }
        for grade in grades:
            if grade.subject_id == subject.id:
                subject_grades[grade.grade_type][grade.column_index] = grade
        grades_by_subject[subject.id] = subject_grades
    
    return render_template(
        "student_grades.html",
        student=student,
        subjects=subjects,
        grades_by_subject=grades_by_subject,
        semester=semester,
        school_year=school_year
    )

@app.route("/delete_grade/<int:grade_id>", methods=["POST"])
@login_required
def delete_grade(grade_id):
    """Xóa một điểm"""
    grade = db.session.get(Grade, grade_id)
    if grade:
        student_id = grade.student_id
        db.session.delete(grade)
        db.session.commit()
        flash("Đã xóa điểm!", "success")
        return redirect(url_for("student_grades", student_id=student_id))
    return redirect(url_for("manage_grades"))

@app.route("/api/update_grade/<int:grade_id>", methods=["POST"])
@login_required
def update_grade_api(grade_id):
    """API endpoint để cập nhật điểm inline"""
    try:
        data = request.get_json()
        new_score = float(data.get("score", 0))
        
        if new_score < 0 or new_score > 10:
            return jsonify({"success": False, "error": "Điểm phải từ 0 đến 10"}), 400
        
        grade = db.session.get(Grade, grade_id)
        if not grade:
            return jsonify({"success": False, "error": "Không tìm thấy điểm"}), 404
        
        grade.score = new_score
        db.session.commit()
        
        return jsonify({"success": True, "score": new_score})
    except ValueError:
        return jsonify({"success": False, "error": "Điểm không hợp lệ"}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/student/<int:student_id>/transcript")
@login_required
def student_transcript(student_id):
    """Xem bảng điểm tổng hợp (học bạ) của học sinh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_grades"))
    
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    subjects = Subject.query.order_by(Subject.name).all()
    
    transcript_data = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        avg_score = None
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
        
        transcript_data.append({
            'subject': subject,
            'tx_scores': tx_scores,
            'gk_scores': gk_scores,
            'hk_scores': hk_scores,
            'avg_score': avg_score
        })
    
    valid_averages = [item['avg_score'] for item in transcript_data if item['avg_score'] is not None]
    gpa = round(sum(valid_averages) / len(valid_averages), 2) if valid_averages else None
    
    return render_template(
        "student_transcript.html",
        student=student,
        transcript_data=transcript_data,
        semester=semester,
        school_year=school_year,
        gpa=gpa
    )


@app.route("/student/<int:student_id>/violations_timeline")
@login_required
def violations_timeline(student_id):
    """Timeline lịch sử vi phạm của học sinh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_students"))
    
    violations = Violation.query.filter_by(student_id=student_id)\
        .order_by(Violation.date_committed.desc()).all()
    
    violations_by_week = db.session.query(
        Violation.week_number,
        func.count(Violation.id).label('count'),
        func.sum(Violation.points_deducted).label('total_deducted')
    ).filter(Violation.student_id == student_id)\
    .group_by(Violation.week_number)\
    .order_by(Violation.week_number).all()
    
    violations_by_type = db.session.query(
        Violation.violation_type_name,
        func.count(Violation.id).label('count')
    ).filter(Violation.student_id == student_id)\
    .group_by(Violation.violation_type_name)\
    .order_by(desc('count')).all()
    
    week_labels = [w[0] for w in violations_by_week]
    week_counts = [w[1] for w in violations_by_week]
    type_labels = [t[0] for t in violations_by_type]
    type_counts = [t[1] for t in violations_by_type]
    
    return render_template(
        "violations_timeline.html",
        student=student,
        violations=violations,
        violations_by_week=violations_by_week,
        violations_by_type=violations_by_type,
        week_labels=week_labels,
        week_counts=week_counts,
        type_labels=type_labels,
        type_counts=type_counts
    )

@app.route("/student/<int:student_id>/parent_report")
@login_required
def parent_report(student_id):
    """Báo cáo tổng hợp cho phụ huynh"""
    student = db.session.get(Student, student_id)
    if not student:
        flash("Không tìm thấy học sinh!", "error")
        return redirect(url_for("manage_students"))
    
    semester = int(request.args.get('semester', 1))
    school_year = request.args.get('school_year', '2023-2024')
    
    subjects = Subject.query.order_by(Subject.name).all()
    transcript_data = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        avg_score = None
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
        
        transcript_data.append({
            'subject': subject,
            'tx_scores': tx_scores,
            'gk_scores': gk_scores,
            'hk_scores': hk_scores,
            'avg_score': avg_score
        })
    
    valid_averages = [item['avg_score'] for item in transcript_data if item['avg_score'] is not None]
    gpa = round(sum(valid_averages) / len(valid_averages), 2) if valid_averages else None
    
    current_week_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(current_week_cfg.value) if current_week_cfg else 1
    
    recent_violations = Violation.query.filter_by(student_id=student_id)\
        .filter(Violation.week_number >= max(1, current_week - 4))\
        .order_by(Violation.date_committed.desc())\
        .limit(10).all()
    
    total_violations = Violation.query.filter_by(student_id=student_id).count()
    
    return render_template(
        "parent_report.html",
        student=student,
        transcript_data=transcript_data,
        gpa=gpa,
        semester=semester,
        school_year=school_year,
        recent_violations=recent_violations,
        total_violations=total_violations,
        current_week=current_week,
        now=datetime.datetime.now()
    )

@app.route("/api/generate_parent_report/<int:student_id>", methods=["POST"])
@login_required
def generate_parent_report(student_id):
    """Gọi AI tạo nhận xét tổng hợp cho phụ huynh"""
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({"error": "Không tìm thấy học sinh"}), 404
    
    semester = int(request.json.get('semester', 1))
    school_year = request.json.get('school_year', '2023-2024')
    
    subjects = Subject.query.all()
    grades_info = []
    for subject in subjects:
        grades = Grade.query.filter_by(
            student_id=student_id,
            subject_id=subject.id,
            semester=semester,
            school_year=school_year
        ).all()
        
        tx_scores = [g.score for g in grades if g.grade_type == 'TX']
        gk_scores = [g.score for g in grades if g.grade_type == 'GK']
        hk_scores = [g.score for g in grades if g.grade_type == 'HK']
        
        if tx_scores and gk_scores and hk_scores:
            avg_tx = sum(tx_scores) / len(tx_scores)
            avg_gk = sum(gk_scores) / len(gk_scores)
            avg_hk = sum(hk_scores) / len(hk_scores)
            avg_score = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
            grades_info.append(f"{subject.name}: {avg_score}")
    
    valid_avg = [float(g.split(': ')[1]) for g in grades_info if g]
    gpa = round(sum(valid_avg) / len(valid_avg), 2) if valid_avg else 0
    
    violations = Violation.query.filter_by(student_id=student_id)\
        .order_by(Violation.date_committed.desc())\
        .limit(10).all()
    
    violation_summary = f"{len(violations)} vi phạm gần đây" if violations else "Không có vi phạm"
    
    prompt = f"""Bạn là giáo viên chủ nhiệm. Hãy viết nhận xét NGẮN GỌN (3-4 câu) gửi phụ huynh về học sinh {student.name} (Lớp {student.student_class}):

THÔNG TIN HỌC TẬP:
- GPA học kỳ {semester}: {gpa}/10
- Điểm các môn: {', '.join(grades_info) if grades_info else 'Chưa có điểm'}

THÔNG TIN RÈN LUYỆN:
- Điểm rèn luyện hiện tại: {student.current_score}/100
- {violation_summary}

Hãy viết nhận xét xúc tích, chân thành, khích lệ học sinh và đưa ra lời khuyên cụ thể. Không cần xưng hô, viết trực tiếp nội dung."""
    
    response, error = _call_gemini(prompt)
    
    if error:
        return jsonify({"error": error}), 500
    
    return jsonify({"report": response})


@app.route("/admin/reset_week", methods=["POST"])
def reset_week(): check_and_run_auto_reset(); return redirect(url_for("dashboard"))
@app.route("/admin/update_week", methods=["POST"])
def update_week():
    c = SystemConfig.query.filter_by(key="current_week").first()
    if c: c.value = str(request.form["new_week"]); db.session.commit()
    return redirect(url_for("dashboard"))
@app.route("/api/check_duplicate_student", methods=["POST"])
def check_duplicate_student(): return jsonify([])

def create_database():
    db.create_all()
    if not Teacher.query.first(): db.session.add(Teacher(username="admin", password="admin", full_name="Admin"))
    if not SystemConfig.query.first(): db.session.add(SystemConfig(key="current_week", value="1"))
    if not ViolationType.query.first(): db.session.add(ViolationType(name="Đi muộn", points_deducted=2))
    db.session.commit()

if __name__ == "__main__":
    with app.app_context(): create_database()

    app.run(debug=True)

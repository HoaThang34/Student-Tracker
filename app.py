
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import os
import json
import datetime
import base64
import requests
import re
import unicodedata
import uuid
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

from models import db, Student, Violation, ViolationType, Teacher, SystemConfig, ClassRoom, WeeklyArchive, Subject, Grade, ChatConversation


basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, "templates")

app = Flask(__name__, template_folder=template_dir)

app.config["SECRET_KEY"] = "chia-khoa-bi-mat-cua-ban-ne-123456"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip() 
GEMINI_MODEL = "gemini-3-flash"  
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

def is_reset_needed():
    """Kiểm tra xem đã sang tuần thực tế mới chưa để hiện cảnh báo"""
    try:
        current_iso_week = get_current_iso_week()
        last_reset_cfg = SystemConfig.query.filter_by(key="last_reset_week_id").first()
        
        # Nếu chưa từng reset lần nào -> Cần báo
        if not last_reset_cfg:
            return True
            
        # Nếu tuần thực tế khác tuần đã lưu -> Cần báo
        if current_iso_week != last_reset_cfg.value:
            return True
    except:
        pass
    return False

# === CHATBOT MEMORY HELPER FUNCTIONS ===

def get_or_create_chat_session():
    """
    Lấy session_id hiện tại từ Flask session hoặc tạo mới
    
    Returns:
        str: Session ID duy nhất cho cuộc hội thoại hiện tại
    """
    if 'chat_session_id' not in session:
        session['chat_session_id'] = str(uuid.uuid4())
    return session['chat_session_id']

def get_conversation_history(session_id, limit=10):
    """
    Lấy lịch sử hội thoại từ database
    
    Args:
        session_id (str): ID của chat session
        limit (int): Số lượng messages gần nhất (default 10)
    
    Returns:
        list[dict]: Danh sách messages theo format {"role": str, "content": str}
    """
    messages = ChatConversation.query.filter_by(
        session_id=session_id
    ).order_by(
        ChatConversation.created_at.asc()
    ).limit(limit).all()
    
    return [{"role": msg.role, "content": msg.message} for msg in messages]

def save_message(session_id, teacher_id, role, message, context_data=None):
    """
    Lưu message vào database
    
    Args:
        session_id (str): ID của session
        teacher_id (int): ID của teacher
        role (str): 'user' hoặc 'assistant'
        message (str): Nội dung message
        context_data (dict, optional): Metadata bổ sung (student_id, etc.)
    """
    chat_msg = ChatConversation(
        session_id=session_id,
        teacher_id=teacher_id,
        role=role,
        message=message,
        context_data=json.dumps(context_data) if context_data else None
    )
    db.session.add(chat_msg)
    db.session.commit()

# Context-aware AI System Prompt
CHATBOT_SYSTEM_PROMPT = """Vai trò: Bạn là một Trợ lý AI có Nhận thức Ngữ cảnh Cao (Context-Aware AI Assistant) cho giáo viên chủ nhiệm.

Mục tiêu: Duy trì sự liền mạch của cuộc hội thoại bằng cách ghi nhớ và sử dụng tích cực thông tin từ lịch sử trò chuyện.

Quy tắc Hoạt động:
1. Ghi nhớ Chủ động: Rà soát toàn bộ thông tin người dùng đã cung cấp trước đó (tên học sinh, yêu cầu, bối cảnh).
2. Tham chiếu Chéo: Lồng ghép chi tiết từ quá khứ để chứng minh bạn đang nhớ (VD: "Như bạn đã hỏi về em [tên] lúc nãy...").
3. Tránh Lặp lại: Không hỏi lại thông tin đã được cung cấp.
4. Cập nhật Trạng thái: Nếu người dùng thay đổi ý định, cập nhật ngay và xác nhận.

Định dạng Đầu ra: Phản hồi tự nhiên, ngắn gọn, thấu hiểu và luôn kết nối logic với các dữ kiện trước đó. Sử dụng emoji và markdown để dễ đọc.
"""

# === BULK VIOLATION IMPORT HELPER FUNCTIONS ===

def calculate_week_from_date(date_obj):
    """
    Calculate week_number from date
    Simple implementation: week of year
    
    Args:
        date_obj: datetime object
    
    Returns:
        int: week number
    """
    _, week_num, _ = date_obj.isocalendar()
    return week_num

def parse_excel_file(file):
    """
    Parse Excel file using pandas
    
    Expected columns:
    - Mã học sinh (student_code)
    - Loại vi phạm (violation_type_name)
    - Điểm trừ (points_deducted)
    - Ngày vi phạm (date_committed) - format: YYYY-MM-DD HH:MM or DD/MM/YYYY HH:MM
    - Tuần (week_number) - optional, auto-calculate if empty
    
    Returns:
        List[dict]: Violations data
    """
    try:
        df = pd.read_excel(file)
        
        # Validate required columns
        required_cols = ['Mã học sinh', 'Loại vi phạm', 'Điểm trừ', 'Ngày vi phạm']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Thiếu cột bắt buộc: {col}")
        
        violations = []
        for idx, row in df.iterrows():
            # Parse datetime
            date_str = str(row['Ngày vi phạm'])
            try:
                # Try YYYY-MM-DD HH:MM format
                date_committed = datetime.datetime.strptime(date_str, '%Y-%m-%d %H:%M')
            except:
                try:
                    # Try DD/MM/YYYY HH:MM format
                    date_committed = datetime.datetime.strptime(date_str, '%d/%m/%Y %H:%M')
                except:
                    try:
                        # Try date only YYYY-MM-DD
                        date_committed = datetime.datetime.strptime(date_str.split()[0], '%Y-%m-%d')
                    except:
                        raise ValueError(f"Dòng {idx+2}: Định dạng ngày không hợp lệ: {date_str}")
            
            # Calculate week_number if not provided
            week_number = row.get('Tuần', None)
            if pd.isna(week_number):
                week_number = calculate_week_from_date(date_committed)
            
            violations.append({
                'student_code': str(row['Mã học sinh']).strip(),
                'violation_type_name': str(row['Loại vi phạm']).strip(),
                'points_deducted': int(row['Điểm trừ']),
                'date_committed': date_committed,
                'week_number': int(week_number)
            })
        
        return violations
    except Exception as e:
        raise ValueError(f"Lỗi đọc file Excel: {str(e)}")

def import_violations_to_db(violations_data):
    """
    Import violations to database
    
    Args:
        violations_data: List[dict] with keys:
            - student_code
            - violation_type_name
            - points_deducted
            - date_committed
            - week_number
    
    Returns:
        Tuple[List[str], int]: (errors, success_count)
    """
    errors = []
    success_count = 0
    
    for idx, v_data in enumerate(violations_data):
        try:
            # Find student
            student = Student.query.filter_by(student_code=v_data['student_code']).first()
            if not student:
                errors.append(f"Dòng {idx+1}: Không tìm thấy học sinh '{v_data['student_code']}'")
                continue
            
            # Create violation record
            violation = Violation(
                student_id=student.id,
                violation_type_name=v_data['violation_type_name'],
                points_deducted=v_data['points_deducted'],
                date_committed=v_data['date_committed'],
                week_number=v_data['week_number']
            )
            
            db.session.add(violation)
            
            # QUAN TRỌNG: KHÔNG cập nhật current_score
            # Chỉ lưu lịch sử, không ảnh hưởng điểm hiện tại
            
            success_count += 1
            
        except Exception as e:
            errors.append(f"Dòng {idx+1}: {str(e)}")
            db.session.rollback()
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        errors.append(f"Lỗi lưu database: {str(e)}")
    
    return errors, success_count

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
    
    # Calculate GPA for each student
    week_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(week_cfg.value) if week_cfg else 1
    
    # Determine current semester and school year
    # Simple logic: weeks 1-20 = semester 1, weeks 21-40 = semester 2
    semester = 1 if current_week <= 20 else 2
    school_year = "2023-2024"  # Could be made dynamic later
    
    student_gpas = {}
    for student in students:
        gpa = calculate_student_gpa(student.id, semester, school_year)
        student_gpas[student.id] = gpa
    
    return render_template('index.html', students=students, student_gpas=student_gpas, search_query=search, selected_class=selected_class)

def calculate_student_gpa(student_id, semester, school_year):
    """
    Calculate GPA for a student
    Formula: (TX + GK*2 + HK*3) / 6 for each subject, then average all subjects
    
    Returns:
        float: GPA value (0.0 - 10.0) or None if no grades
    """
    grades = Grade.query.filter_by(
        student_id=student_id,
        semester=semester,
        school_year=school_year
    ).all()
    
    if not grades:
        return None
    
    # Group by subject
    grades_by_subject = {}
    for grade in grades:
        if grade.subject_id not in grades_by_subject:
            grades_by_subject[grade.subject_id] = {'TX': [], 'GK': [], 'HK': []}
        grades_by_subject[grade.subject_id][grade.grade_type].append(grade.score)
    
    # Calculate average for each subject
    subject_averages = []
    for subject_id, data in grades_by_subject.items():
        if data['TX'] and data['GK'] and data['HK']:
            avg_tx = sum(data['TX']) / len(data['TX'])
            avg_gk = sum(data['GK']) / len(data['GK'])
            avg_hk = sum(data['HK']) / len(data['HK'])
            subject_avg = round((avg_tx + avg_gk * 2 + avg_hk * 3) / 6, 2)
            subject_averages.append(subject_avg)
    
    if not subject_averages:
        return None
    
    # Calculate overall GPA
    gpa = round(sum(subject_averages) / len(subject_averages), 2)
    return gpa


@app.route("/dashboard")
@login_required
def dashboard():
    show_reset_warning = is_reset_needed()
    
    # 1. Lấy số thứ tự tuần hiện tại
    w_cfg = SystemConfig.query.filter_by(key="current_week").first()
    current_week = int(w_cfg.value) if w_cfg else 1
    
    s_class = request.args.get("class_select")
    
    # 2. Thống kê điểm số (Của hiện tại)
    q = Student.query.filter_by(student_class=s_class) if s_class else Student.query
    c_tot = q.filter(Student.current_score >= 90).count()
    c_kha = q.filter(Student.current_score >= 70, Student.current_score < 90).count()
    c_tb = q.filter(Student.current_score < 70).count()
    
    # 3. Thống kê lỗi (CHỈ LẤY CỦA TUẦN HIỆN TẠI) -> Đây là mấu chốt để "reset" visual
    vios_q = db.session.query(Violation.violation_type_name, func.count(Violation.violation_type_name).label("c"))
    
    # Lọc theo tuần hiện tại
    vios_q = vios_q.filter(Violation.week_number == current_week)
    
    if s_class: 
        vios_q = vios_q.join(Student).filter(Student.student_class == s_class)
        
    top = vios_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
    
    return render_template("dashboard.html", 
                           show_reset_warning=show_reset_warning,
                           selected_class=s_class, 
                           pie_labels=json.dumps(["Tốt", "Khá", "Cần cố gắng"]), 
                           pie_data=json.dumps([c_tot, c_kha, c_tb]), 
                           bar_labels=json.dumps([n for n, _ in top]), 
                           bar_data=json.dumps([c for _, c in top]))

# --- Thêm vào app.py ---

@app.route("/api/analyze_class_stats", methods=["POST"])
@login_required
def analyze_class_stats():
    try:
        data = request.get_json()
        s_class = data.get("class_name", "")
        # Nhận tham số tuần từ request (nếu có)
        week_req = data.get("week", None)
        
        # Xác định tuần cần phân tích
        sys_week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        sys_week = int(sys_week_cfg.value) if sys_week_cfg else 1
        target_week = int(week_req) if week_req else sys_week
        
        # Kiểm tra xem có phải là xem lại lịch sử không
        is_history = (target_week < sys_week)
        
        # 1. Lấy thống kê Phân loại (Tốt/Khá/TB)
        if is_history:
            # Nếu là lịch sử: Lấy từ bảng lưu trữ WeeklyArchive
            q = WeeklyArchive.query.filter_by(week_number=target_week)
            if s_class: q = q.filter_by(student_class=s_class)
            
            c_tot = q.filter(WeeklyArchive.final_score >= 90).count()
            c_kha = q.filter(WeeklyArchive.final_score >= 70, WeeklyArchive.final_score < 90).count()
            c_tb = q.filter(WeeklyArchive.final_score < 70).count()
        else:
            # Nếu là hiện tại: Lấy từ bảng Student
            q = Student.query
            if s_class: q = q.filter_by(student_class=s_class)
            
            c_tot = q.filter(Student.current_score >= 90).count()
            c_kha = q.filter(Student.current_score >= 70, Student.current_score < 90).count()
            c_tb = q.filter(Student.current_score < 70).count()
            
        total_students = c_tot + c_kha + c_tb
        
        # 2. Lấy Top vi phạm (Lọc đúng theo tuần target_week)
        vios_q = db.session.query(Violation.violation_type_name, func.count(Violation.violation_type_name).label("c"))
        vios_q = vios_q.filter(Violation.week_number == target_week)
        
        if s_class:
            vios_q = vios_q.join(Student).filter(Student.student_class == s_class)
        
        top_violations = vios_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
        violations_text = ", ".join([f"{name} ({count} lần)" for name, count in top_violations])
        if not violations_text: violations_text = "Không có vi phạm đáng kể."

        # 3. Tạo Prompt gửi AI
        context_name = f"Lớp {s_class}" if s_class else "Toàn Trường"
        time_context = f"TUẦN {target_week}"
        
        prompt = f"""
        Đóng vai Trợ lý Giáo dục. Phân tích nề nếp {time_context} của {context_name}:
        - Tổng sĩ số: {total_students}
        - Kết quả rèn luyện: Tốt {c_tot}, Khá {c_kha}, Trung bình/Yếu {c_tb}.
        - Các lỗi vi phạm chính trong tuần: {violations_text}

        Yêu cầu trả lời:
        - Viết một đoạn nhận xét ngắn gọn (khoảng 3-4 câu).
        - Giọng văn khách quan, sư phạm nhưng thẳng thắn.
        - Chỉ ra điểm tích cực (nếu tỉ lệ Tốt cao) hoặc vấn đề báo động (nếu vi phạm nhiều).
        - Đưa ra 1 lời khuyên cụ thể cho giáo viên chủ nhiệm để chấn chỉnh lớp trong tuần tới.
        - Không dùng các định dạng markdown như * đậm * hay dấu hoa thị đầu dòng, viết thành đoạn văn xuôi.
        """
        
        analysis_text, error = _call_gemini(prompt)
        if error: return jsonify({"error": error}), 500
            
        return jsonify({"analysis": analysis_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
#Thêm vi phạm(remake)
# --- Thay thế hàm add_violation cũ bằng hàm này ---

@app.route("/add_violation", methods=["GET", "POST"])
@login_required
def add_violation():
    if request.method == "POST":
        # Get list of rule IDs (can be multiple)
        selected_rule_ids = request.form.getlist("rule_ids[]")
        
        # 1. Lấy danh sách ID học sinh từ Form (Dạng Select nhiều)
        selected_student_ids = request.form.getlist("student_ids[]")
        
        # 2. Lấy danh sách từ OCR (Dạng JSON nếu có)
        ocr_json = request.form.get("students_list")
        
        if not selected_rule_ids:
            flash("Vui lòng chọn ít nhất một lỗi vi phạm!", "error")
            return redirect(url_for("add_violation"))

        w_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week = int(w_cfg.value) if w_cfg else 1
        count = 0

        # Process each violation type
        for rule_id in selected_rule_ids:
            try:
                rule = db.session.get(ViolationType, int(rule_id))
            except:
                continue
            
            if not rule:
                continue

            # A. Xử lý danh sách từ Dropdown chọn tay
            if selected_student_ids:
                for s_id in selected_student_ids:
                    student = db.session.get(Student, int(s_id))
                    if student:
                        student.current_score = (student.current_score or 100) - rule.points_deducted
                        db.session.add(Violation(student_id=student.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                        count += 1
            
            # B. Xử lý danh sách từ OCR (Giữ nguyên logic cũ)
            elif ocr_json:
                try:
                    student_codes = json.loads(ocr_json)
                    for code in student_codes:
                        if not code: continue
                        s = Student.query.filter_by(student_code=str(code).strip()).first()
                        if s:
                            s.current_score = (s.current_score or 100) - rule.points_deducted
                            db.session.add(Violation(student_id=s.id, violation_type_name=rule.name, points_deducted=rule.points_deducted, week_number=current_week))
                            count += 1
                except Exception as e:
                    print(f"OCR Error: {e}")

        if count > 0:
            db.session.commit()
            flash(f"Đã ghi nhận {count} vi phạm (cho {len(selected_student_ids) if selected_student_ids else 'nhiều'} học sinh x {len(selected_rule_ids)} lỗi).", "success")
        else:
            flash("Chưa chọn học sinh nào hoặc xảy ra lỗi.", "error")
        
        return redirect(url_for("add_violation"))

    # GET: Truyền thêm danh sách học sinh để hiển thị trong Dropdown
    students = Student.query.order_by(Student.student_class, Student.name).all()
    return render_template("add_violation.html", rules=ViolationType.query.all(), students=students)



@app.route("/bulk_import_violations")
@login_required
def bulk_import_violations():
    """Display bulk import page"""
    students = Student.query.order_by(Student.student_class, Student.name).all()
    violation_types = ViolationType.query.all()
    return render_template("bulk_import_violations.html", 
                          students=students, 
                          violation_types=violation_types)

@app.route("/process_bulk_violations", methods=["POST"])
@login_required
def process_bulk_violations():
    """
    Process bulk violation import from either:
    - Manual form entry (JSON array from frontend)
    - Excel file upload
    """
    try:
        # Check source type
        excel_file = request.files.get('excel_file')
        manual_data = request.form.get('manual_violations_json')
        
        violations_to_import = []
        
        if excel_file and excel_file.filename:
            # Process Excel file
            violations_to_import = parse_excel_file(excel_file)
        elif manual_data:
            # Process manual JSON data
            violations_to_import = json.loads(manual_data)
            
            # Convert date strings to datetime objects
            for v in violations_to_import:
                if isinstance(v['date_committed'], str):
                    v['date_committed'] = datetime.datetime.strptime(v['date_committed'], '%Y-%m-%dT%H:%M')
                if 'week_number' not in v or v['week_number'] is None:
                    v['week_number'] = calculate_week_from_date(v['date_committed'])
        else:
            return jsonify({"status": "error", "message": "Không có dữ liệu để import"}), 400
        
        # Validate & Import
        errors, success_count = import_violations_to_db(violations_to_import)
        
        if errors:
            return jsonify({
                "status": "partial" if success_count > 0 else "error",
                "errors": errors,
                "success": success_count,
                "message": f"Đã import {success_count} vi phạm. Có {len(errors)} lỗi."
            })
        
        return jsonify({
            "status": "success",
            "count": success_count,
            "message": f"✅ Đã import thành công {success_count} vi phạm!"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_violation_template")
@login_required
def download_violation_template():
    """Generate and download Excel template"""
    # Create sample template
    df = pd.DataFrame({
        'Mã học sinh': ['12TIN-001', '12TIN-002', '11A1-005'],
        'Loại vi phạm': ['Đi trễ', 'Không mặc đồng phục', 'Thiếu học liệu'],
        'Điểm trừ': [5, 10, 3],
        'Ngày vi phạm': ['2024-01-15 08:30', '2024-01-16 07:45', '2024-01-20 14:00'],
        'Tuần': [3, 3, 4]
    })
    
    # Save to BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Violations')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='template_import_violations.xlsx'
    )


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
    # Lấy danh sách học sinh
    students = Student.query.order_by(Student.student_code.asc()).all()
    class_list = ClassRoom.query.order_by(ClassRoom.name).all()
    return render_template("manage_students.html", students=students, class_list=class_list)

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
#chỉnh sửa lớp học

@app.route("/edit_class/<int:class_id>", methods=["POST"])
@login_required
def edit_class(class_id):
    """Đổi tên lớp và cập nhật lại lớp cho toàn bộ học sinh"""
    try:
        new_name = request.form.get("new_name", "").strip()
        if not new_name:
            flash("Tên lớp không được để trống!", "error")
            return redirect(url_for("manage_students"))

        # Tìm lớp cần sửa
        cls = db.session.get(ClassRoom, class_id)
        if cls:
            old_name = cls.name
            
            # 1. Cập nhật tên trong bảng ClassRoom
            cls.name = new_name
            
            # 2. Cập nhật lại tên lớp cho TẤT CẢ học sinh đang ở lớp cũ
            # (Logic quan trọng để đồng bộ dữ liệu)
            students_in_class = Student.query.filter_by(student_class=old_name).all()
            for s in students_in_class:
                s.student_class = new_name
                
            db.session.commit()
            flash(f"Đã đổi tên lớp '{old_name}' thành '{new_name}' và cập nhật {len(students_in_class)} học sinh.", "success")
        else:
            flash("Không tìm thấy lớp học!", "error")
            
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi: {str(e)}", "error")
        
    return redirect(url_for("manage_students"))

@app.route("/delete_class/<int:class_id>", methods=["POST"])
@login_required
def delete_class(class_id):
    """Xóa lớp học"""
    try:
        cls = db.session.get(ClassRoom, class_id)
        if cls:
            # Kiểm tra an toàn: Chỉ cho xóa nếu lớp RỖNG (không có học sinh)
            student_count = Student.query.filter_by(student_class=cls.name).count()
            if student_count > 0:
                flash(f"Không thể xóa lớp '{cls.name}' vì đang có {student_count} học sinh. Hãy chuyển hoặc xóa học sinh trước.", "error")
            else:
                db.session.delete(cls)
                db.session.commit()
                flash(f"Đã xóa lớp {cls.name}", "success")
    except Exception as e:
        flash(f"Lỗi: {str(e)}", "error")
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
    """Context-aware chatbot với conversation memory"""
    msg = (request.json.get("message") or "").strip()
    if not msg:
        return jsonify({"response": "Vui lòng nhập câu hỏi."})
    
    # 1. Get/Create chat session
    session_id = get_or_create_chat_session()
    teacher_id = current_user.id
    
    # 2. Load conversation history
    history = get_conversation_history(session_id, limit=10)
    
    # 3. Save user message to database
    save_message(session_id, teacher_id, "user", msg)
    
    # 4. Tìm kiếm học sinh từ CSDL (hỗ trợ cả context từ history)
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
            
            # Save bot response
            save_message(session_id, teacher_id, "assistant", response)
            
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
        
        # Tạo context cho AI với conversation history
        student_context = f"""THÔNG TIN HỌC SINH:
- Họ tên: {student.name}
- Mã số: {student.student_code}
- Lớp: {student.student_class}
- Điểm hành vi hiện tại: {student.current_score}/100

ĐIỂM HỌC TẬP (Học kỳ 1):
"""
        if grades_data:
            for subject, scores in grades_data.items():
                student_context += f"- {subject}: TX={scores['TX']}, GK={scores['GK']}, HK={scores['HK']}, TB={scores['TB']}\n"
        else:
            student_context += "- Chưa có dữ liệu điểm\n"
        
        student_context += f"\nVI PHẠM:\n"
        if violations_data:
            student_context += f"- Tổng số: {len(violations)} lần\n"
            student_context += "- Chi tiết gần nhất:\n"
            for v in violations_data:
                student_context += f"  + {v['type']} (-{v['points']}đ) - {v['date']}\n"
        else:
            student_context += "- Không có vi phạm\n"
        
        # Build context-aware prompt với conversation history
        prompt = f"""{CHATBOT_SYSTEM_PROMPT}

===== LỊCH SỬ HỘI THOẠI =====
"""
        if history:
            for h in history:
                role_vn = "Giáo viên" if h['role'] == 'user' else "Trợ lý"
                prompt += f"{role_vn}: {h['content']}\n"
        
        prompt += f"""
===== THÔNG TIN HỌC SINH ĐƯỢC TRA CỨU =====
{student_context}

===== CÂU HỎI HIỆN TẠI =====
Giáo viên: {msg}

===== YÊU CẦU =====
Dựa trên lịch sử hội thoại và thông tin học sinh, hãy:
1. Tham chiếu lại các thông tin đã thảo luận trước đó (nếu có)
2. Phân tích học sinh một cách toàn diện
3. Trả lời câu hỏi của giáo viên một cách tự nhiên, có ngữ cảnh

Trả lời bằng tiếng Việt, thân thiện, chuyên nghiệp. Sử dụng emoji phù hợp và định dạng markdown.
"""
        
        ai_response, err = _call_gemini(prompt)
        
        if ai_response:
            # Save AI response
            save_message(session_id, teacher_id, "assistant", ai_response, 
                        context_data={"student_id": student.id, "student_name": student.name})
            
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
            
            save_message(session_id, teacher_id, "assistant", response)
            
            buttons = [
                {"label": "📊 Xem học bạ", "payload": f"/student/{student.id}/transcript"},
                {"label": "📈 Chi tiết điểm", "payload": f"/student/{student.id}"},
                {"label": "📜 Lịch sử vi phạm", "payload": f"/student/{student.id}/violations_timeline"}
            ]
            
            return jsonify({"response": response.strip(), "buttons": buttons})
    
    # Nếu không tìm thấy học sinh, sử dụng AI với context awareness
    prompt = f"""{CHATBOT_SYSTEM_PROMPT}

===== LỊCH SỬ HỘI THOẠI =====
"""
    if history:
        for h in history:
            role_vn = "Giáo viên" if h['role'] == 'user' else "Trợ lý"
            prompt += f"{role_vn}: {h['content']}\n"
    
    prompt += f"""
===== CÂU HỎI HIỆN TẠI =====
Giáo viên: {msg}

===== YÊU CẦU =====
Bạn là trợ lý ảo của hệ thống quản lý học sinh. 
- Dựa vào lịch sử hội thoại, hiểu ngữ cảnh và trả lời phù hợp
- Nếu giáo viên hỏi về học sinh nhưng không tìm thấy, đề nghị nhập tên chính xác hơn
- Nếu hỏi về chức năng hệ thống, giải thích rõ ràng
- Trả lời ngắn gọn, thân thiện, sử dụng emoji và markdown
"""
    
    ans, err = _call_gemini(prompt)
    response_text = ans or "Xin lỗi, tôi chưa hiểu câu hỏi của bạn. Bạn có thể nhập tên hoặc mã số học sinh để tra cứu thông tin."
    
    # Save AI response
    save_message(session_id, teacher_id, "assistant", response_text)
    
    return jsonify({"response": response_text})

@app.route("/api/chatbot/clear", methods=["POST"])
@login_required
def clear_chat_session():
    """Tạo session mới và xóa session cũ khỏi Flask session"""
    session.pop('chat_session_id', None)
    return jsonify({"status": "success", "message": "Chat đã được làm mới"})


@app.route("/profile")
@login_required
def profile(): return render_template("profile.html", user=current_user)

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    if request.method == "POST":
        return redirect(url_for("profile"))
    return render_template("edit_profile.html", user=current_user)

#route kho lưu trữ (remake)

@app.route("/history")
@login_required
def history():
    # Lấy danh sách tuần
    weeks = [w[0] for w in db.session.query(Violation.week_number).distinct().order_by(Violation.week_number.desc()).all()]
    
    selected_week = request.args.get('week', type=int)
    selected_class = request.args.get('class_select', '').strip()

    # Mặc định chọn tuần mới nhất có dữ liệu
    if not selected_week and weeks: selected_week = weeks[0]
        
    violations = []     # Danh sách chi tiết lỗi
    class_rankings = [] # Bảng xếp hạng
    pie_data = [0, 0, 0] # Dữ liệu biểu đồ tròn
    bar_labels = []      # Nhãn biểu đồ cột
    bar_data = []        # Dữ liệu biểu đồ cột

    if selected_week:
        # A. LẤY CHI TIẾT VI PHẠM (để hiện bảng)
        query = db.session.query(Violation).join(Student).filter(Violation.week_number == selected_week)
        if selected_class:
            query = query.filter(Student.student_class == selected_class)
        violations = query.order_by(Violation.date_committed.desc()).all()

        # B. TÍNH TOÁN BIỂU ĐỒ TRÒN (Từ bảng lưu trữ WeeklyArchive)
        # Nếu có chọn lớp thì lọc theo lớp, không thì lấy toàn trường
        arch_query = WeeklyArchive.query.filter_by(week_number=selected_week)
        if selected_class:
            arch_query = arch_query.filter_by(student_class=selected_class)
        archives = arch_query.all()

        if archives:
            c_tot = sum(1 for a in archives if a.final_score >= 90)
            c_kha = sum(1 for a in archives if 70 <= a.final_score < 90)
            c_tb = sum(1 for a in archives if a.final_score < 70)
            pie_data = [c_tot, c_kha, c_tb]

        # C. TÍNH TOÁN BIỂU ĐỒ CỘT (Top vi phạm tuần đó)
        vios_chart_q = db.session.query(Violation.violation_type_name, func.count(Violation.id).label("c"))\
            .filter(Violation.week_number == selected_week)
        
        if selected_class:
            vios_chart_q = vios_chart_q.join(Student).filter(Student.student_class == selected_class)

        top = vios_chart_q.group_by(Violation.violation_type_name).order_by(desc("c")).limit(5).all()
        
        bar_labels = [t[0] for t in top]
        bar_data = [t[1] for t in top]

        # D. TÍNH BẢNG XẾP HẠNG (Chỉ tính khi không lọc lớp cụ thể)
        if not selected_class:
            all_classes_obj = ClassRoom.query.all()
            for cls in all_classes_obj:
                # Lấy điểm trung bình từ Archive cho nhanh
                cls_avgs = [a.final_score for a in WeeklyArchive.query.filter_by(week_number=selected_week, student_class=cls.name).all()]
                
                # Tính tổng lỗi (để hiển thị)
                deduct = db.session.query(func.sum(Violation.points_deducted))\
                    .join(Student).filter(Student.student_class == cls.name, Violation.week_number == selected_week).scalar() or 0
                
                avg_score = sum(cls_avgs)/len(cls_avgs) if cls_avgs else 100
                
                class_rankings.append({
                    "name": cls.name,
                    "weekly_deduct": deduct,
                    "avg_score": round(avg_score, 2)
                })
            class_rankings.sort(key=lambda x: x['avg_score'], reverse=True)

    all_classes = [c.name for c in ClassRoom.query.order_by(ClassRoom.name).all()]

    return render_template("history.html", 
                           weeks=weeks, 
                           selected_week=selected_week, 
                           selected_class=selected_class,
                           violations=violations, 
                           class_rankings=class_rankings,
                           all_classes=all_classes,
                           # Truyền dữ liệu biểu đồ sang HTML
                           pie_data=json.dumps(pie_data),
                           bar_labels=json.dumps(bar_labels),
                           bar_data=json.dumps(bar_data))

# --- THÊM ROUTE MỚI ĐỂ XUẤT EXCEL ---

@app.route("/export_history")
@login_required
def export_history():
    selected_week = request.args.get('week', type=int)
    selected_class = request.args.get('class_select', '').strip()
    
    if not selected_week:
        flash("Vui lòng chọn tuần để xuất báo cáo", "error")
        return redirect(url_for('history'))

    # Truy vấn giống hệt bên trên
    query = db.session.query(Violation).join(Student).filter(Violation.week_number == selected_week)
    if selected_class:
        query = query.filter(Student.student_class == selected_class)
    
    violations = query.order_by(Violation.date_committed.desc()).all()
    
    # Tạo dữ liệu cho Excel
    data = []
    for v in violations:
        data.append({
            "Ngày": v.date_committed.strftime('%d/%m/%Y'),
            "Mã HS": v.student.student_code,
            "Họ Tên": v.student.name,
            "Lớp": v.student.student_class,
            "Lỗi Vi Phạm": v.violation_type_name,
            "Điểm Trừ": v.points_deducted,
            "Tuần": v.week_number
        })
    
    # Xuất file
    if data:
        df = pd.read_json(json.dumps(data))
    else:
        df = pd.DataFrame([{"Thông báo": "Không có dữ liệu vi phạm"}])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=f"Tuan_{selected_week}")
        # Tự động điều chỉnh độ rộng cột (cơ bản)
        worksheet = writer.sheets[f"Tuan_{selected_week}"]
        for idx, col in enumerate(df.columns):
            worksheet.column_dimensions[chr(65 + idx)].width = 20

    output.seek(0)
    filename = f"BaoCao_ViPham_Tuan{selected_week}"
    if selected_class:
        filename += f"_{selected_class}"
    filename += ".xlsx"
    
    return send_file(output, download_name=filename, as_attachment=True, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

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
@login_required
def reset_week():
    try:
        # 1. Lấy tuần hiển thị hiện tại
        week_cfg = SystemConfig.query.filter_by(key="current_week").first()
        current_week_num = int(week_cfg.value) if week_cfg else 1
        
        # 2. Lưu trữ dữ liệu tuần cũ
        save_weekly_archive(current_week_num)
        
        # 3. Reset điểm toàn bộ học sinh về 100
        db.session.query(Student).update({Student.current_score: 100})
        
        # 4. Tăng số tuần hiển thị lên 1
        if week_cfg:
            week_cfg.value = str(current_week_num + 1)
            
        # 5. Cập nhật "Dấu vết" tuần ISO để tắt cảnh báo
        current_iso = get_current_iso_week()
        last_reset_cfg = SystemConfig.query.filter_by(key="last_reset_week_id").first()
        if not last_reset_cfg:
            db.session.add(SystemConfig(key="last_reset_week_id", value=current_iso))
        else:
            last_reset_cfg.value = current_iso
            
        db.session.commit()
        flash(f"Đã kết thúc Tuần {current_week_num}. Hệ thống chuyển sang Tuần {current_week_num + 1}.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi: {str(e)}", "error")
        
    return redirect(url_for("dashboard"))
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

@app.route("/delete_violation/<int:violation_id>", methods=["POST"])
@login_required
def delete_violation(violation_id):
    try:
        # 1. Tìm bản ghi vi phạm
        violation = Violation.query.get_or_404(violation_id)
        student = Student.query.get(violation.student_id)
        
        # 2. KHÔI PHỤC ĐIỂM SỐ
        # Cộng trả lại điểm đã trừ
        if student:
            student.current_score += violation.points_deducted
            # Đảm bảo điểm không vượt quá 100 (nếu quy chế là max 100)
            if student.current_score > 100:
                student.current_score = 100
        
        # 3. Xóa vi phạm
        db.session.delete(violation)
        db.session.commit()
        
        flash(f"Đã xóa vi phạm và khôi phục {violation.points_deducted} điểm cho học sinh.", "success")
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi khi xóa: {str(e)}", "error")
        
    # Quay lại trang Timeline của học sinh đó
    return redirect(url_for('violations_timeline', student_id=student.id if student else 0))

import unidecode # Thư viện xử lý tiếng Việt không dấu
import re

@app.route("/import_students", methods=["GET", "POST"])
@login_required
def import_students():
    """Bước 1: Upload file và Sinh mã tự động"""
    if request.method == "POST":
        file = request.files.get("file")
        # Lấy số khóa từ ô nhập (mặc định là 34 nếu không nhập)
        course_code = request.form.get("course_code", "34").strip()
        
        if not file:
            flash("Vui lòng chọn file Excel!", "error")
            return redirect(request.url)

        try:
            # Đọc file Excel
            df = pd.read_excel(file)
            # Chuẩn hóa tên cột về chữ thường để dễ tìm
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            preview_data = []
            
            # Tìm cột Họ tên và Lớp (chấp nhận: "họ tên", "tên", "họ và tên"...)
            name_col = next((c for c in df.columns if "tên" in c or "name" in c), None)
            class_col = next((c for c in df.columns if "lớp" in c or "class" in c), None)
            
            if not name_col or not class_col:
                flash("File Excel cần có cột 'Họ tên' và 'Lớp'", "error")
                return redirect(request.url)

            # Lặp qua từng dòng trong Excel
            for index, row in df.iterrows():
                name = str(row[name_col]).strip()
                s_class = str(row[class_col]).strip()
                
                # Bỏ qua dòng trống
                if not name or name.lower() == 'nan': continue

                # --- LOGIC SINH MÃ: [KHÓA] [CHUYÊN] - 001[STT] ---
                
                # 1. Lấy phần Chuyên (VD: "12 Tin" -> "TIN")
                class_unsign = unidecode.unidecode(s_class).upper() # 12 TIN
                # Chỉ giữ lại chữ cái A-Z, bỏ số và dấu cách
                specialization = re.sub(r'[^A-Z]', '', class_unsign) 
                
                # 2. Tính số thứ tự (STT)
                # Đếm xem trong DB lớp này đã có bao nhiêu bạn rồi để nối tiếp
                count_in_db = Student.query.filter_by(student_class=s_class).count()
                # STT = Số lượng trong DB + Số thứ tự trong file Excel (index bắt đầu từ 0 nên +1)
                sequence = count_in_db + index + 1
                
                # 3. Ghép mã
                # {sequence:03d} nghĩa là số 6 sẽ thành 006
                auto_code = f"{course_code} {specialization} - 001{sequence:03d}"
                
                preview_data.append({
                    "name": name,
                    "class": s_class,
                    "generated_code": auto_code
                })
            
            # Chuyển sang trang xác nhận
            return render_template("confirm_import.html", students=preview_data)

        except Exception as e:
            flash(f"Lỗi đọc file: {str(e)}", "error")
            return redirect(request.url)

    return render_template("import_students.html")


@app.route("/save_imported_students", methods=["POST"])
@login_required
def save_imported_students():
    """Bước 2: Lưu vào CSDL sau khi xác nhận"""
    try:
        # Lấy danh sách dạng mảng từ form
        names = request.form.getlist("names[]")
        classes = request.form.getlist("classes[]")
        codes = request.form.getlist("codes[]")
        
        count = 0
        for name, s_class, code in zip(names, classes, codes):
            # 1. Kiểm tra trùng mã trong DB
            if Student.query.filter_by(student_code=code).first():
                continue # Nếu trùng thì bỏ qua
            
            # 2. Tự động tạo Lớp mới nếu chưa có
            if not ClassRoom.query.filter_by(name=s_class).first():
                db.session.add(ClassRoom(name=s_class))
            
            # 3. Thêm học sinh
            new_student = Student(name=name, student_class=s_class, student_code=code)
            db.session.add(new_student)
            count += 1
            
        db.session.commit()
        flash(f"Đã nhập thành công {count} học sinh!", "success")
        return redirect(url_for('manage_students'))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Lỗi khi lưu: {str(e)}", "error")
        return redirect(url_for('import_students'))
    
app.run(debug=True)
 

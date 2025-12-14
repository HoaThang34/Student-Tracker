# 🎓 Hệ Thống Quản Lý Học Sinh

Ứng dụng web quản lý toàn diện cho nhà trường, bao gồm quản lý điểm số, vi phạm nội quy, và báo cáo học sinh.

## 📋 Tính Năng

### 1. **Quản Lý Học Sinh**
- ✅ Thêm, sửa, xóa thông tin học sinh
- ✅ Tìm kiếm theo tên hoặc mã số học sinh
- ✅ Lọc theo lớp học
- ✅ Quản lý danh sách lớp học

### 2. **Quản Lý Điểm Số**
- ✅ Nhập điểm theo môn học (TX, GK, HK)
- ✅ Xem bảng điểm tổng hợp (Học bạ)
- ✅ Tính điểm trung bình tự động
- ✅ Quản lý môn học và cấu hình cột điểm

### 3. **Quản Lý Vi Phạm Nội Quy**
- ✅ Ghi nhận vi phạm của học sinh
- ✅ OCR tự động đọc mã số từ thẻ học sinh
- ✅ Trừ điểm rèn luyện theo quy định
- ✅ Quản lý loại vi phạm và mức trừ điểm
- ✅ Theo dõi lịch sử vi phạm theo tuần

### 4. **Báo Cáo & Thống Kê**
- ✅ Dashboard tổng quan với biểu đồ
- ✅ Báo cáo tuần, tháng
- ✅ Xuất file Excel
- ✅ Báo cáo tổng hợp cho phụ huynh
- ✅ Timeline vi phạm của học sinh
- ✅ Lưu trữ điểm theo tuần

### 5. **AI & Chatbot**
- ✅ OCR thông minh với Google Gemini AI
- ✅ Chatbot hỗ trợ tra cứu thông tin
- ✅ Tự động nhận xét học sinh

### 6. **Bảo Mật**
- ✅ Đăng nhập với Flask-Login
- ✅ Phân quyền giáo viên
- ✅ Bảo mật session

## 🛠️ Công Nghệ Sử Dụng

### Backend
- **Flask** - Web framework Python
- **SQLAlchemy** - ORM cho database
- **SQLite** - Cơ sở dữ liệu
- **Flask-Login** - Quản lý đăng nhập

### AI & Machine Learning
- **Google Gemini API** - AI chatbot và OCR
- **Gemini Flash 2.5 Lite** - Model AI

### Frontend
- **HTML/CSS/JavaScript** - Giao diện web
- **Chart.js** - Biểu đồ thống kê
- **Bootstrap** - Framework CSS (tuỳ chọn)

### Thư Viện Khác
- **Pandas** - Xử lý dữ liệu
- **OpenPyXL** - Xuất file Excel
- **Requests** - Gọi API

## 📦 Cài Đặt

### 1. Yêu Cầu Hệ Thống
- Python 3.8 trở lên
- pip (Python package manager)

### 2. Clone/Download Project
```bash
# Nếu dùng Git
git clone <repository-url>
cd Source

# Hoặc giải nén file ZIP đã tải
```

### 3. Cài Đặt Dependencies
```bash
pip install -r requirements.txt
```

### 4. Cấu Hình API Key
Mở file `app.py` và cấu hình Gemini API Key:

```python
GEMINI_API_KEY = "your-api-key-here"
```

Hoặc thiết lập biến môi trường:
```bash
# Windows
set GEMINI_API_KEY=your-api-key-here

# Linux/Mac
export GEMINI_API_KEY=your-api-key-here
```

**Lấy API Key miễn phí tại:** https://aistudio.google.com/app/apikey

### 5. Khởi Tạo Database
```bash
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
>>> exit()
```

### 6. Tạo Tài Khoản Admin (Tuỳ chọn)
```python
from models import Teacher
from app import app, db

with app.app_context():
    admin = Teacher(
        username='admin',
        password='admin123',
        full_name='Giáo Viên Admin',
        school_name='THPT Chuyên Nguyễn Tất Thành',
        main_class='12 Tin'
    )
    db.session.add(admin)
    db.session.commit()
```

## 🚀 Chạy Ứng Dụng

### Development Mode
```bash
python app.py
```

Hoặc với Flask CLI:
```bash
flask run
```

Sau đó truy cập: **http://localhost:5000**

### Production Mode
```bash
# Sử dụng Gunicorn (Linux/Mac)
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Hoặc Waitress (Windows)
pip install waitress
waitress-serve --listen=*:5000 app:app
```

## 📂 Cấu Trúc Project

```
Source/
│
├── app.py                    # Ứng dụng chính Flask
├── models.py                 # Database models
├── requirements.txt          # Dependencies
├── database.db              # SQLite database
│
├── templates/               # HTML templates
│   ├── base.html           # Template cơ bản
│   ├── login.html          # Trang đăng nhập
│   ├── dashboard.html      # Dashboard
│   ├── manage_students.html    # Quản lý học sinh
│   ├── manage_grades.html      # Quản lý điểm
│   ├── student_grades.html     # Nhập điểm học sinh
│   ├── student_transcript.html # Học bạ
│   ├── add_violation.html      # Ghi vi phạm
│   ├── violations_timeline.html # Timeline vi phạm
│   ├── parent_report.html      # Báo cáo phụ huynh
│   ├── weekly_report.html      # Báo cáo tuần
│   ├── history.html            # Lịch sử
│   ├── chatbot.html            # AI Chatbot
│   └── ...
│
└── uploads/                 # Thư mục lưu ảnh upload
```

## 💾 Database Models

### Student (Học Sinh)
- `id` - ID
- `student_code` - Mã học sinh (unique)
- `name` - Họ tên
- `student_class` - Lớp
- `current_score` - Điểm rèn luyện hiện tại (mặc định 100)

### Teacher (Giáo Viên)
- `id` - ID
- `username` - Tên đăng nhập (unique)
- `password` - Mật khẩu
- `full_name` - Họ tên
- `school_name` - Tên trường
- `main_class` - Lớp chủ nhiệm

### Subject (Môn Học)
- `id` - ID
- `name` - Tên môn học
- `code` - Mã môn (unique)
- `description` - Mô tả
- `num_tx_columns` - Số cột điểm TX
- `num_gk_columns` - Số cột điểm GK
- `num_hk_columns` - Số cột điểm HK

### Grade (Điểm Số)
- `id` - ID
- `student_id` - ID học sinh
- `subject_id` - ID môn học
- `grade_type` - Loại điểm (TX/GK/HK)
- `column_index` - Thứ tự cột
- `score` - Điểm số (0-10)
- `semester` - Học kỳ
- `school_year` - Năm học

### ViolationType (Loại Vi Phạm)
- `id` - ID
- `name` - Tên loại vi phạm
- `points_deducted` - Điểm bị trừ

### Violation (Vi Phạm)
- `id` - ID
- `student_id` - ID học sinh
- `violation_type_name` - Tên vi phạm
- `points_deducted` - Điểm bị trừ
- `date_committed` - Ngày vi phạm
- `week_number` - Tuần

### ClassRoom (Lớp Học)
- `id` - ID
- `name` - Tên lớp

### WeeklyArchive (Lưu Trữ Tuần)
- `id` - ID
- `week_number` - Số tuần
- `student_id` - ID học sinh
- `final_score` - Điểm cuối tuần
- `total_deductions` - Tổng điểm trừ

## 📱 Sử Dụng

### 1. Đăng Nhập
Truy cập `/login` và sử dụng tài khoản giáo viên

### 2. Dashboard
Xem thống kê tổng quan về học sinh, vi phạm

### 3. Quản Lý Học Sinh
- Truy cập `/manage_students`
- Thêm/Sửa/Xóa học sinh
- Thêm lớp học mới

### 4. Nhập Điểm
- Truy cập `/manage_grades`
- Chọn học sinh → Nhập điểm theo môn học
- Xem học bạ tại `/student/<id>/transcript`

### 5. Ghi Vi Phạm
- Truy cập `/add_violation`
- Nhập thủ công hoặc dùng OCR upload ảnh thẻ học sinh
- Chọn loại vi phạm và xác nhận

### 6. Xem Báo Cáo
- **Báo cáo tuần**: `/weekly_report`
- **Lịch sử**: `/history`
- **Báo cáo phụ huynh**: `/student/<id>/parent_report`
- **Timeline vi phạm**: `/student/<id>/violations_timeline`

### 7. AI Chatbot
- Truy cập `/chatbot`
- Hỏi thông tin học sinh hoặc câu hỏi chung

## 🔧 Cấu Hình Nâng Cao

### Thay Đổi Secret Key
```python
app.config["SECRET_KEY"] = "your-secret-key-here"
```

### Thay Đổi AI Model
```python
GEMINI_MODEL = "gemini-2.5-flash-lite"  # Hoặc model khác
```

### Tự Động Reset Điểm Tuần
Hệ thống tự động reset điểm rèn luyện mỗi tuần (theo ISO week)

Để tắt tính năng này, comment dòng trong route `/dashboard`:
```python
# check_and_run_auto_reset()
```

## 🔒 Bảo Mật

### Khuyến Nghị
1. **Đổi SECRET_KEY** thành chuỗi ngẫu nhiên mạnh
2. **Mã hoá mật khẩu** bằng bcrypt hoặc werkzeug.security
3. **Sử dụng HTTPS** khi deploy production
4. **Giới hạn upload file** để tránh tấn công
5. **Bảo mật API Key** - không commit lên Git

### Example: Hash Password
```python
from werkzeug.security import generate_password_hash, check_password_hash

# Khi tạo user
hashed_password = generate_password_hash('password123')

# Khi đăng nhập
if check_password_hash(user.password, entered_password):
    # Login success
```

## 📊 API Endpoints

### Authentication
- `GET /login` - Trang đăng nhập
- `POST /login` - Xác thực
- `GET /logout` - Đăng xuất

### Students
- `GET /manage_students` - Danh sách học sinh
- `POST /add_student` - Thêm học sinh
- `POST /delete_student/<id>` - Xóa học sinh
- `GET/POST /edit_student/<id>` - Sửa học sinh

### Grades
- `GET /manage_grades` - Danh sách điểm
- `GET/POST /student_grades/<id>` - Nhập điểm
- `POST /delete_grade/<id>` - Xóa điểm
- `GET /student/<id>/transcript` - Xem học bạ

### Violations
- `GET/POST /add_violation` - Ghi vi phạm
- `POST /upload_ocr` - OCR ảnh thẻ
- `GET /student/<id>/violations_timeline` - Timeline

### Reports
- `GET /dashboard` - Dashboard
- `GET /weekly_report` - Báo cáo tuần
- `GET /history` - Lịch sử
- `GET /export_report` - Xuất Excel
- `GET /student/<id>/parent_report` - Báo cáo phụ huynh

### AI
- `GET /chatbot` - Trang chatbot
- `POST /api/chatbot` - API chatbot
- `POST /api/generate_report/<id>` - Tạo nhận xét AI

## 🐛 Troubleshooting

### Database Error
```bash
# Xóa database cũ và tạo mới
rm database.db
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
```

### Gemini API Error
- Kiểm tra API Key có đúng không
- Kiểm tra kết nối internet
- Xem log lỗi chi tiết trong console

### Import Error
```bash
# Cài lại dependencies
pip install -r requirements.txt --upgrade
```

## 📝 License

Dự án giáo dục - Sử dụng tự do cho mục đích học tập.

## 👥 Tác Giả

Học sinh TrườngTHPT Chuyên Nguyễn Tất Thành

## 🔄 Cập Nhật

### Version 1.0.0 (Current)
- ✅ Quản lý học sinh, điểm số, vi phạm
- ✅ OCR với Gemini AI
- ✅ Dashboard thống kê
- ✅ Báo cáo tổng hợp
- ✅ Chatbot AI

### Kế Hoạch Phát Triển
- [ ] Mobile app
- [ ] Gửi email/SMS thông báo
- [ ] Tích hợp Google Classroom
- [ ] Nhận diện khuôn mặt
- [ ] Multi-language support
- [ ] Role-based access control

---

**Lưu Ý:** Đây là phiên bản demo/giáo dục. Nên kiểm tra kỹ và tăng cường bảo mật trước khi sử dụng trong môi trường thực tế.

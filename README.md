# 🎓 Hệ Thống Quản Lý Học Sinh

Ứng dụng web quản lý toàn diện cho nhà trường, bao gồm quản lý điểm số, vi phạm nội quy, và báo cáo học sinh với AI hỗ trợ.

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
- ✅ OCR tự động đọc mã số từ thẻ học sinh (AI Vision)
- ✅ Import hàng loạt vi phạm từ Excel
- ✅ Trừ điểm rèn luyện theo quy định
- ✅ Quản lý loại vi phạm và mức trừ điểm
- ✅ Theo dõi lịch sử vi phạm theo tuần

### 4. **Báo Cáo & Thống Kê**
- ✅ Dashboard tổng quan với biểu đồ
- ✅ AI phân tích và nhận xét tự động
- ✅ Báo cáo tuần, tháng
- ✅ Xuất file Excel
- ✅ Báo cáo tổng hợp cho phụ huynh
- ✅ Timeline vi phạm của học sinh
- ✅ Lưu trữ điểm theo tuần

### 5. **AI & Chatbot** 🤖
- ✅ **Ollama Local AI**: Xử lý AI hoàn toàn offline
- ✅ **OCR Vision**: Đọc thẻ học sinh từ ảnh
- ✅ **Chatbot thông minh**: Tra cứu thông tin học sinh với conversation memory
- ✅ **AI Analytics**: Tự động phân tích và nhận xét lớp học
- ✅ **Privacy-first**: Dữ liệu không rời khỏi local machine

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
- **Ollama** - Local AI runtime
- **Gemini 3 Flash Preview** - Multimodal AI model (cloud variant)
- **Vision AI** - OCR và xử lý ảnh

### Frontend
- **HTML/CSS/JavaScript** - Giao diện web
- **Chart.js** - Biểu đồ thống kê
- **Tailwind CSS** - Framework CSS hiện đại

### Thư Viện Khác
- **Pandas** - Xử lý dữ liệu
- **OpenPyXL** - Xuất file Excel
- **Requests** - HTTP client

## 📦 Cài Đặt

### 1. Yêu Cầu Hệ Thống
- Python 3.8 trở lên
- pip (Python package manager)
- **Ollama** - Cài đặt từ https://ollama.com

### 2. Clone/Download Project
```bash
# Nếu dùng Git
git clone <repository-url>
cd Student_Tracker

# Hoặc giải nén file ZIP đã tải
```

### 3. Cài Đặt Ollama và Model

#### Bước 3.1: Cài đặt Ollama
```bash
# Windows/Mac/Linux: Tải từ https://ollama.com/download
# Sau khi cài đặt, verify:
ollama --version
```

#### Bước 3.2: Pull AI Model
```bash
ollama pull gemini-3-flash-preview:cloud
```

#### Bước 3.3: Verify Model
```bash
ollama list
# Kết quả phải hiển thị: gemini-3-flash-preview:cloud
```

### 4. Cài Đặt Python Dependencies
```bash
pip install -r requirements.txt
```

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

### Bước 1: Khởi động Ollama Service
Ollama thường tự động chạy sau khi cài đặt. Nếu không:
```bash
# Linux/Mac
ollama serve

# Windows: Ollama chạy dưới dạng service tự động
```

### Bước 2: Chạy Flask App

#### Development Mode
```bash
python app.py
```

Hoặc với Flask CLI:
```bash
flask run
```

Sau đó truy cập: **http://localhost:5000**

#### Production Mode
```bash
# Sử dụng Gunicorn (Linux/Mac)
gunicorn -w 4 -b 0.0.0.0:5000 app:app

# Hoặc Waitress (Windows)
pip install waitress
waitress-serve --listen=*:5000 app:app
```

## 📂 Cấu Trúc Project

```
Student_Tracker/
│
├── app.py                    # Ứng dụng chính Flask
├── models.py                 # Database models
├── requirements.txt          # Dependencies
├── database.db              # SQLite database
├── migrate_chatbot.py       # Migration script cho chatbot memory
│
├── templates/               # HTML templates
│   ├── base.html           # Template cơ bản
│   ├── login.html          # Trang đăng nhập
│   ├── welcome.html        # Trang chào mừng
│   ├── dashboard.html      # Dashboard
│   ├── manage_students.html    # Quản lý học sinh
│   ├── manage_grades.html      # Quản lý điểm
│   ├── student_grades.html     # Nhập điểm học sinh
│   ├── student_transcript.html # Học bạ
│   ├── add_violation.html      # Ghi vi phạm
│   ├── bulk_import_violations.html # Import vi phạm hàng loạt
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

### ChatConversation (Hội Thoại Chatbot)
- `id` - ID
- `session_id` - Session ID
- `teacher_id` - ID giáo viên
- `role` - Vai trò (user/assistant)
- `message` - Nội dung tin nhắn
- `context_data` - Metadata (JSON)
- `created_at` - Thời gian tạo

## 📱 Sử Dụng

### 1. Đăng Nhập
Truy cập `/login` và sử dụng tài khoản giáo viên

### 2. Dashboard
Xem thống kê tổng quan về học sinh, vi phạm với AI analytics

### 3. Quản Lý Học Sinh
- Truy cập `/manage_students`
- Thêm/Sửa/Xóa học sinh
- Thêm lớp học mới

### 4. Nhập Điểm
- Truy cập `/manage_grades`
- Chọn học sinh → Nhập điểm theo môn học
- Xem học bạ tại `/student/<id>/transcript`

### 5. Ghi Vi Phạm
- **Cách 1 - Thủ công**: Truy cập `/add_violation`, chọn học sinh và loại vi phạm
- **Cách 2 - OCR**: Upload ảnh thẻ học sinh, AI tự động nhận diện
- **Cách 3 - Bulk Import**: Truy cập `/bulk_import_violations`, upload file Excel

### 6. Xem Báo Cáo
- **Báo cáo tuần**: `/weekly_report`
- **Lịch sử**: `/history`
- **Báo cáo phụ huynh**: `/student/<id>/parent_report`
- **Timeline vi phạm**: `/student/<id>/violations_timeline`

### 7. AI Chatbot 🤖
- Truy cập `/chatbot`
- Hỏi về học sinh: "Cho tôi biết về em Nguyễn Văn A"
- Chatbot có **conversation memory**, nhớ được ngữ cảnh cuộc trò chuyện
- Nhấn "Làm mới chat" để bắt đầu cuộc hội thoại mới

## 🔧 Cấu Hình Nâng Cao

### Thay Đổi Secret Key
```python
app.config["SECRET_KEY"] = "your-secret-key-here"
```

### Cấu Hình Ollama
```python
# app.py
OLLAMA_MODEL = "gemini-3-flash-preview:cloud"  # Thay đổi model
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")  # Thay đổi host
```

Hoặc dùng biến môi trường:
```bash
# Windows
set OLLAMA_HOST=http://localhost:11434

# Linux/Mac
export OLLAMA_HOST=http://localhost:11434
```

### Sử Dụng Model Khác
```bash
# List các model có sẵn
ollama list

# Pull model khác
ollama pull llama2
ollama pull mistral
ollama pull llava  # Cho vision tasks

# Cập nhật trong app.py
OLLAMA_MODEL = "llava"  # Model khác
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
5. **Local AI**: Ollama chạy local → Dữ liệu không rời khỏi máy bạn

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
- `GET /` - Trang chào mừng
- `GET /login` - Trang đăng nhập
- `POST /login` - Xác thực
- `GET /logout` - Đăng xuất

### Students
- `GET /scoreboard` - Bảng điểm tổng quan
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
- `GET /bulk_import_violations` - Trang import hàng loạt
- `POST /process_bulk_violations` - Xử lý import
- `GET /download_violation_template` - Tải template Excel
- `POST /upload_ocr` - OCR ảnh thẻ
- `GET /student/<id>/violations_timeline` - Timeline

### Reports
- `GET /dashboard` - Dashboard
- `POST /api/analyze_class_stats` - AI phân tích lớp
- `GET /weekly_report` - Báo cáo tuần
- `GET /history` - Lịch sử
- `GET /export_report` - Xuất Excel
- `GET /student/<id>/parent_report` - Báo cáo phụ huynh

### AI Chatbot
- `GET /chatbot` - Trang chatbot
- `POST /api/chatbot` - API chatbot (với conversation memory)
- `POST /api/chatbot/clear` - Xóa lịch sử chat
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

### Ollama Connection Error
```bash
# Kiểm tra Ollama đang chạy
ollama list

# Khởi động lại Ollama service
# Linux/Mac:
ollama serve

# Windows: Mở Ollama app hoặc restart service
```

### Model Not Found Error
```bash
# Pull model lại
ollama pull gemini-3-flash-preview:cloud

# Verify
ollama list
```

### Import Error
```bash
# Cài lại dependencies
pip install -r requirements.txt --upgrade
```

### Chatbot Memory Issues
```bash
# Chạy migration script để upgrade database
python migrate_chatbot.py
```

## 🎯 So Sánh: Gemini API vs Ollama

| Tiêu chí | Gemini API (Cũ) | Ollama (Hiện tại) |
|----------|-----------------|-------------------|
| **Kết nối** | External HTTPS | Local HTTP |
| **Speed** | 2-5s (network) | 1-3s (local) |
| **Privacy** | ❌ Data gửi Google | ✅ 100% local |
| **Cost** | Có thể tính phí | ✅ Miễn phí |
| **Setup** | Cần API Key | Cần install Ollama |
| **Offline** | ❌ Cần internet | ✅ Hoàn toàn offline |
| **Rate Limit** | Có giới hạn | ✅ Không giới hạn |

## 📝 License

Dự án giáo dục - Sử dụng tự do cho mục đích học tập.

## 👥 Tác Giả

Học sinh Trường THPT Chuyên Nguyễn Tất Thành

## 🔄 Lịch Sử Cập Nhật

### Version 2.0.0 (Current - 26/12/2024)
- ✅ **Migration sang Ollama**: Không còn phụ thuộc Gemini API
- ✅ **Privacy-first AI**: 100% xử lý local
- ✅ **Chatbot Memory**: Ghi nhớ ngữ cảnh hội thoại
- ✅ **Bulk Import**: Import hàng loạt vi phạm từ Excel
- ✅ **Enhanced OCR**: Vision AI với Ollama

### Version 1.0.0
- ✅ Quản lý học sinh, điểm số, vi phạm
- ✅ OCR với Gemini AI
- ✅ Dashboard thống kê
- ✅ Báo cáo tổng hợp
- ✅ Chatbot AI cơ bản

### Kế Hoạch Phát Triển
- [ ] Mobile app (React Native/Flutter)
- [ ] Gửi email/SMS thông báo tự động
- [ ] Tích hợp Google Classroom
- [ ] Nhận diện khuôn mặt với AI
- [ ] Multi-language support (English, Vietnamese)
- [ ] Role-based access control (Admin, Giáo viên, Phụ huynh)
- [ ] Real-time notifications với WebSocket
- [ ] Advanced analytics với machine learning

---

## 🚀 Quick Start Guide

```bash
# 1. Cài Ollama (https://ollama.com)

# 2. Pull model
ollama pull gemini-3-flash-preview:cloud

# 3. Clone project
cd Student_Tracker

# 4. Install dependencies
pip install -r requirements.txt

# 5. Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 6. Run app
python app.py

# 7. Open browser
# http://localhost:5000
```

---

**Lưu Ý:** 
- ✅ Version 2.0.0 sử dụng **Ollama local AI**, đảm bảo privacy và không tốn phí
- ✅ Tất cả dữ liệu được xử lý **hoàn toàn offline**
- ⚠️ Đây là phiên bản demo/giáo dục. Nên kiểm tra kỹ và tăng cường bảo mật trước khi sử dụng trong môi trường thực tế.

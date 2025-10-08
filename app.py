from flask import Flask, render_template, request, jsonify, make_response
import cv2
import face_recognition
import numpy as np
from datetime import datetime, timedelta
import sqlite3
import os

DB_PATH = os.getenv('DB_PATH', 'attendance.db')
import base64
import pandas as pd
import threading
import time
import socket
from decimal import Decimal
import logging
from logging.handlers import RotatingFileHandler

# إعداد التسجيل إلى ملف مع تدوير
logger = logging.getLogger('radmeter')
logger.setLevel(logging.INFO)
_log_handler = RotatingFileHandler('app.log', maxBytes=5_000_000, backupCount=3, encoding='utf-8')
_log_formatter = logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s')
_log_handler.setFormatter(_log_formatter)
if not logger.handlers:
    logger.addHandler(_log_handler)

# استيراد مُجدول البيانات التراكمية
try:
    from scheduler import CumulativeDataScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    print("⚠️ تحذير: لم يتم العثور على مُجدول البيانات التراكمية")
    SCHEDULER_AVAILABLE = False

# استيراد نظام الحسابات الزمنية المحسن
from time_utils import (
    time_calculator,
    get_current_time_precise,
    calculate_duration_precise,
    calculate_exposure_precise
)

# استيراد نظام التخزين المؤقت
from cache_manager import get_radiation_cache

# إعدادات النظام
DEFAULT_SENSOR_ID = "ESP32_001"
print("✅ النظام يستخدم قاعدة البيانات المحلية SQLite فقط")

# إنشاء كائن التخزين المؤقت العام
radiation_cache = get_radiation_cache()

def update_cache_from_local_db():
    """تحديث التخزين المؤقت من قاعدة البيانات المحلية"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # جلب آخر 10 قراءات من قاعدة البيانات المحلية
        c.execute('''SELECT cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp
                     FROM radiation_readings_local
                     ORDER BY timestamp DESC LIMIT 10''')

        readings = c.fetchall()

        if readings:
            print(f"🔄 تحديث التخزين المؤقت من قاعدة البيانات المحلية: {len(readings)} قراءة")
            logger.info(f"Updating cache from local DB with {len(readings)} readings")

            for reading in reversed(readings):  # إضافة بالترتيب الزمني
                cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp = reading

                # إضافة القراءة إلى التخزين المؤقت باستخدام الواجهة الصحيحة
                reading_obj = radiation_cache.add_reading(
                    cpm=int(cpm) if cpm is not None else 0,
                    source_power=float(source_power) if source_power is not None else 0.0,
                    absorbed_dose_rate=float(absorbed_dose_rate) if absorbed_dose_rate is not None else 0.0,
                    total_absorbed_dose=float(total_absorbed_dose) if total_absorbed_dose is not None else 0.0,
                    sensor_id=DEFAULT_SENSOR_ID
                )

                # ضبط الطابع الزمني للقراءة لتطابق قاعدة البيانات
                try:
                    ts_str = str(timestamp)
                    reading_obj.timestamp = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                except Exception as ts_err:
                    logger.warning(f"Failed to parse timestamp from DB row: {ts_err}")
                    pass

            print(f"✅ تم تحديث التخزين المؤقت بنجاح")
            logger.info("Cache updated successfully from local DB")
        else:
            print("⚠️ لا توجد قراءات في قاعدة البيانات المحلية")
            logger.warning("No readings found in local DB while trying to update cache")

        conn.close()

    except Exception as e:
        print(f"❌ خطأ في تحديث التخزين المؤقت: {e}")
        logger.exception(f"Cache update from local DB failed: {e}")

def get_local_ip():
    """الحصول على عنوان IP المحلي"""
    try:
        # إنشاء socket للحصول على عنوان IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # اتصال بـ Google DNS
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        try:
            # بديل في حالة فشل الطريقة الأولى
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            return local_ip
        except Exception:
            return "127.0.0.1"  # localhost كبديل أخير

app = Flask(__name__)

# إعداد مُجدول البيانات التراكمية
global_scheduler = None

def initialize_scheduler():
    """""تهيئة مُجدول البيانات التراكمية"""
    global global_scheduler
    if SCHEDULER_AVAILABLE and global_scheduler is None:
        try:
            local_ip = get_local_ip()
            api_url = f"http://{local_ip}:5000"
            global_scheduler = CumulativeDataScheduler(api_base_url=api_url)
            print(f"✅ تم تهيئة مُجدول البيانات التراكمية - {api_url}")
            return True
        except Exception as e:
            print(f"❌ خطأ في تهيئة المُجدول: {e}")
            return False
    return False

# إنشاء المجلدات المطلوبة إذا لم تكن موجودة
if not os.path.exists('static/attendance'):
    os.makedirs('static/attendance')
if not os.path.exists('static/employees'):
    os.makedirs('static/employees')

# إنشاء قاعدة البيانات
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # تفعيل إعدادات SQLite لتحسين الاعتمادية والأداء
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.execute("PRAGMA busy_timeout=5000")
    except Exception as _pragma_err:
        # في حال فشل أي PRAGMA لا نمنع التهيئة
        logger.warning(f"Failed to set PRAGMAs: {_pragma_err}")

    # جدول الموظفين
    c.execute('''CREATE TABLE IF NOT EXISTS employees
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  employee_id TEXT UNIQUE,
                  name TEXT,
                  image_path TEXT,
                  department TEXT,
                  position TEXT,
                  max_daily_dose REAL DEFAULT 20.0,
                  max_annual_dose REAL DEFAULT 20000.0,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # جدول الحضور والانصراف
    c.execute('''CREATE TABLE IF NOT EXISTS attendance
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  employee_id TEXT,
                  check_type TEXT,
                  timestamp DATETIME,
                  image_path TEXT)''')

    # إضافة الأعمدة المفقودة إذا لم تكن موجودة
    try:
        c.execute("ALTER TABLE attendance ADD COLUMN name TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE attendance ADD COLUMN date TEXT")
    except Exception:
        pass
    try:
        c.execute("ALTER TABLE attendance ADD COLUMN time TEXT")
    except Exception:
        pass
    # جدول قراءات الإشعاع المحلية
    c.execute('''CREATE TABLE IF NOT EXISTS radiation_readings_local
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      cpm INTEGER,
                      source_power REAL,
                      absorbed_dose_rate REAL,
                      total_absorbed_dose REAL,
                      session_id INTEGER,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
    # ضمان توفر العمود عند قواعد بيانات سابقة
    try:
        c.execute("ALTER TABLE radiation_readings_local ADD COLUMN session_id INTEGER")
    except Exception:
        pass
    # فهرس للأداء على session_id
    c.execute('''CREATE INDEX IF NOT EXISTS idx_radiation_readings_session_id
                 ON radiation_readings_local (session_id)''')

    # جدول فترات التعرض للموظفين
    c.execute('''CREATE TABLE IF NOT EXISTS employee_exposure_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  employee_id TEXT,
                  check_in_time DATETIME,
                  check_out_time DATETIME,
                  initial_total_dose REAL,
                  final_total_dose REAL,
                  exposure_duration_minutes INTEGER,
                  average_dose_rate REAL,
                  total_exposure REAL,
                  max_dose_rate REAL,
                  min_dose_rate REAL,
                  safety_alerts INTEGER DEFAULT 0,
                  notes TEXT,
                  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                  FOREIGN KEY (employee_id) REFERENCES employees (employee_id))''')

    # إضافة الأعمدة الجديدة لنظام الجلسة الواحدة اليومية
    try:
        c.execute("ALTER TABLE employee_exposure_sessions ADD COLUMN session_date DATE")
    except Exception:
        pass  # العمود موجود بالفعل

    try:
        c.execute("ALTER TABLE employee_exposure_sessions ADD COLUMN is_active BOOLEAN DEFAULT 1")
    except Exception:
        pass  # العمود موجود بالفعل

    try:
        c.execute("ALTER TABLE employee_exposure_sessions ADD COLUMN daily_total_exposure REAL DEFAULT 0.0")
    except Exception:
        pass  # العمود موجود بالفعل

    # جدول تنبيهات الأمان
    c.execute('''CREATE TABLE IF NOT EXISTS safety_alerts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  employee_id TEXT,
                  alert_type TEXT,
                  alert_level TEXT,
                  message TEXT,
                  dose_value REAL,
                  threshold_value REAL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                  acknowledged BOOLEAN DEFAULT FALSE,
                  FOREIGN KEY (employee_id) REFERENCES employees (employee_id))''')

    # جدول إعدادات النظام
    c.execute('''CREATE TABLE IF NOT EXISTS system_settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  setting_key TEXT UNIQUE,
                  setting_value TEXT,
                  description TEXT,
                  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # إدراج الإعدادات الافتراضية (محدثة وفقاً للمعايير الدولية)
    default_settings = [
        ('daily_dose_limit', '54.8', 'الحد الأقصى للجرعة اليومية للعاملين (μSv) - ICRP'),
        ('annual_dose_limit', '20000.0', 'الحد الأقصى للجرعة السنوية للعاملين (μSv) - ICRP'),
        ('warning_threshold', '15.0', 'عتبة التحذير لمعدل الجرعة (μSv/h)'),
        ('danger_threshold', '25.0', 'عتبة الخطر لمعدل الجرعة (μSv/h)'),
        ('natural_background_limit', '0.3', 'الحد الأقصى للخلفية الطبيعية (μSv/h) - UNSCEAR'),
        ('worker_hourly_limit', '6.8', 'الحد الساعي للعاملين (μSv/h)'),
        ('auto_checkout_hours', '12', 'الخروج التلقائي بعد ساعات'),
        ('alert_email_enabled', 'false', 'تفعيل تنبيهات البريد الإلكتروني'),
        ('sensor_timeout_minutes', '5', 'انتهاء مهلة الحساس بالدقائق'),
        ('tube_type', 'J305', 'نوع أنبوب Geiger المستخدم (SBM20 أو J305)')
    ]

    for setting in default_settings:
        c.execute('''INSERT OR IGNORE INTO system_settings
                     (setting_key, setting_value, description)
                     VALUES (?, ?, ?)''', setting)

    # إنشاء جدول البيانات التراكمية إذا لم يكن موجوداً (لمطابقة واجهة /api/cumulative_doses_fast)
    c.execute('''
        CREATE TABLE IF NOT EXISTS employee_cumulative_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id TEXT NOT NULL,
            total_sessions INTEGER DEFAULT 0,
            completed_sessions INTEGER DEFAULT 0,
            active_sessions INTEGER DEFAULT 0,
            total_duration_minutes INTEGER DEFAULT 0,
            total_duration_hours REAL DEFAULT 0.0,
            average_session_duration_minutes REAL DEFAULT 0.0,
            total_cumulative_exposure REAL DEFAULT 0.0,
            average_exposure_per_session REAL DEFAULT 0.0,
            average_dose_rate_per_hour REAL DEFAULT 0.0,
            max_single_session_exposure REAL DEFAULT 0.0,
            min_single_session_exposure REAL DEFAULT 0.0,
            daily_exposure REAL DEFAULT 0.0,
            weekly_exposure REAL DEFAULT 0.0,
            monthly_exposure REAL DEFAULT 0.0,
            annual_exposure REAL DEFAULT 0.0,
            daily_exposure_percentage REAL DEFAULT 0.0,
            weekly_exposure_percentage REAL DEFAULT 0.0,
            monthly_exposure_percentage REAL DEFAULT 0.0,
            annual_exposure_percentage REAL DEFAULT 0.0,
            total_readings INTEGER DEFAULT 0,
            average_readings_per_session REAL DEFAULT 0.0,
            first_session_date DATE,
            last_session_date DATE,
            last_completed_session_date DATE,
            safety_status TEXT DEFAULT 'آمن',
            safety_class TEXT DEFAULT 'success',
            risk_level TEXT DEFAULT 'منخفض',
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(employee_id)
        )
    ''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_employee_cumulative_employee_id 
                 ON employee_cumulative_data(employee_id)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_employee_cumulative_last_updated 
                 ON employee_cumulative_data(last_updated)''')

    conn.commit()
    conn.close()
    print("✅ تم تهيئة قاعدة البيانات بنجاح")

# تهيئة قاعدة البيانات عند بدء التطبيق
init_db()

# ===================================
# نظام حفظ البيانات في الخلفية
# ===================================

def background_database_sync():
    """مهمة خلفية لحفظ البيانات في قاعدة البيانات"""
    print("🔄 بدء مهمة حفظ البيانات في الخلفية...")

    while True:
        try:
            # الحصول على القراءات غير المحفوظة
            unsaved_readings = radiation_cache.get_unsaved_readings()

            if unsaved_readings:
                print(f"💾 حفظ {len(unsaved_readings)} قراءة في قاعدة البيانات...")

                for reading in unsaved_readings:
                    try:
                        success = save_reading_to_database(reading)
                        if success:
                            radiation_cache.mark_as_saved(reading)
                        else:
                            radiation_cache.mark_save_failed(reading)
                    except Exception as e:
                        print(f"❌ خطأ في حفظ القراءة: {e}")
                        radiation_cache.mark_save_failed(reading)

            # انتظار 30 ثانية قبل المحاولة التالية
            time.sleep(30)

        except Exception as e:
            print(f"❌ خطأ في مهمة الخلفية: {e}")
            time.sleep(60)  # انتظار دقيقة في حالة الخطأ

def save_reading_to_database(reading):
    """حفظ قراءة واحدة في قاعدة البيانات المحلية - محدث لربط القراءات بالجلسات"""
    try:
        # حفظ في SQLite المحلية
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # إنشاء جدول قراءات الإشعاع إذا لم يكن موجوداً
        c.execute('''CREATE TABLE IF NOT EXISTS radiation_readings_local
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      cpm INTEGER,
                      source_power REAL,
                      absorbed_dose_rate REAL,
                      total_absorbed_dose REAL,
                      session_id INTEGER,
                      timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE INDEX IF NOT EXISTS idx_radiation_readings_session_id
                     ON radiation_readings_local (session_id)''')

        # الحصول على جميع الجلسات النشطة
        c.execute('''SELECT id, employee_id FROM employee_exposure_sessions 
                     WHERE is_active = 1''')
        active_sessions = c.fetchall()

        if active_sessions:
            # حفظ قراءة منفصلة لكل جلسة نشطة
            for session_id, employee_id in active_sessions:
                c.execute('''INSERT INTO radiation_readings_local
                             (cpm, source_power, absorbed_dose_rate, total_absorbed_dose, session_id)
                             VALUES (?, ?, ?, ?, ?)''',
                          (reading.cpm, reading.source_power, reading.absorbed_dose_rate, 
                           reading.total_absorbed_dose, session_id))
            print(f"✅ تم حفظ القراءة لـ {len(active_sessions)} جلسة نشطة")
        else:
            # حفظ قراءة عامة بدون session_id (للحفاظ على السجل العام)
            c.execute('''INSERT INTO radiation_readings_local
                         (cpm, source_power, absorbed_dose_rate, total_absorbed_dose, session_id)
                         VALUES (?, ?, ?, ?, NULL)''',
                      (reading.cpm, reading.source_power, reading.absorbed_dose_rate, reading.total_absorbed_dose))
            print(f"ℹ️ تم حفظ القراءة كقراءة عامة (لا توجد جلسات نشطة)")

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"❌ خطأ في حفظ القراءة في قاعدة البيانات: {e}")
        import traceback
        traceback.print_exc()
        return False

# بدء مهمة الخلفية
background_thread = threading.Thread(target=background_database_sync, daemon=True)
background_thread.start()
print("✅ تم بدء مهمة حفظ البيانات في الخلفية")

def load_known_faces():
    """تحميل الوجوه المعروفة من مجلد dataset"""
    known_face_encodings = []
    known_face_names = []

    if not os.path.exists('dataset'):
        return known_face_encodings, known_face_names

    try:
        for person_name in os.listdir('dataset'):
            person_dir = os.path.join('dataset', person_name)
            if os.path.isdir(person_dir):
                for image_file in os.listdir(person_dir):
                    if image_file.lower().endswith(('.png', '.jpg', '.jpeg')):
                        image_path = os.path.join(person_dir, image_file)
                        try:
                            image = face_recognition.load_image_file(image_path)
                            encodings = face_recognition.face_encodings(image)
                            if encodings:
                                known_face_encodings.append(encodings[0])
                                known_face_names.append(person_name)
                                break  # استخدام صورة واحدة فقط لكل شخص لتحسين الأداء
                        except Exception as e:
                            print(f"Error loading {image_path}: {e}")
                            continue
    except Exception as e:
        print(f"Error loading faces: {e}")

    return known_face_encodings, known_face_names

def get_employee_name_by_id(employee_id):
    """الحصول على اسم الموظف من قاعدة البيانات المحلية أو ملفات CSV"""
    try:
        # أولاً: البحث في قاعدة البيانات المحلية
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute('SELECT name FROM employees WHERE employee_id = ?', (employee_id,))
        result = c.fetchone()
        conn.close()

        if result:
            return result[0]

        # ثانياً: البحث في ملفات CSV (للتوافق مع البيانات القديمة)
        department_files = [
            "هندسة تقنيات الذكاء الاصطناعي.csv",
            "هندسة تقنيات الحاسوب.csv",
            "هندسة تقنيات الأمن السيبراني.csv"
        ]

        # تطبيع رقم الموظف
        normalized_employee_id = str(employee_id).lstrip('0')
        if not normalized_employee_id:
            normalized_employee_id = '0'

        # البحث في ملفات الأقسام
        for file_name in department_files:
            if os.path.exists(file_name):
                try:
                    df = pd.read_csv(file_name, encoding='utf-8-sig')

                    # البحث بـ employee_id أو student_id للتوافق
                    id_column = 'employee_id' if 'employee_id' in df.columns else 'student_id'

                    if id_column in df.columns:
                        # مطابقة دقيقة أولاً
                        employee_row = df[df[id_column].astype(str) == str(employee_id)]
                        if not employee_row.empty:
                            return employee_row.iloc[0]['name']

                        # مطابقة بدون الأصفار البادئة
                        df_normalized = df.copy()
                        df_normalized['id_normalized'] = df_normalized[id_column].astype(str).str.lstrip('0')
                        df_normalized['id_normalized'] = df_normalized['id_normalized'].replace('', '0')

                        employee_row = df_normalized[df_normalized['id_normalized'] == normalized_employee_id]
                        if not employee_row.empty:
                            return employee_row.iloc[0]['name']
                except Exception:
                    continue

        return f"موظف غير معروف (رقم: {employee_id})"
    except Exception as e:
        print(f"Error getting employee name: {e}")
        return f"موظف غير معروف (رقم: {employee_id})"

# تحميل الوجوه المعروفة عند بدء التطبيق
known_face_encodings, known_face_names = load_known_faces()
print(f"Loaded {len(known_face_encodings)} known faces")

@app.route('/')
def index():
    response = make_response(render_template('index.html'))
    # منع التخزين المؤقت للصفحة الرئيسية
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/debug_frontend.html')
def debug_frontend():
    """صفحة اختبار الواجهة الأمامية"""
    from flask import send_from_directory
    return send_from_directory('.', 'debug_frontend.html')

@app.route('/add_employee')
def add_employee():
    """نموذج إضافة موظف جديد"""
    return render_template('add_employee.html')

@app.route('/employees')
def employees():
    """توافق مع روابط قديمة - يعرض نموذج إضافة الموظف"""
    return render_template('add_employee.html')

@app.route('/comprehensive_reports')
def comprehensive_reports():
    """صفحة التقارير الإجمالية الشاملة"""
    return render_template('comprehensive_reports.html')



@app.route('/attendance')
def attendance_page():
    """صفحة تسجيل الحضور والانصراف"""
    return render_template('attendance.html')



@app.route('/unified_reports')
def unified_reports():
    """صفحة التقارير الموحدة (الحضور والتعرض)"""
    return render_template('unified_reports.html')

@app.route('/tube_selector')
def tube_selector():
    """صفحة اختيار نوع أنبوب Geiger"""
    return render_template('tube_selector.html')

# ===================================
# API Endpoints لبيانات الإشعاع
# ===================================

@app.route('/api/radiation_data', methods=['GET'])
def get_radiation_data():
    """إرسال أحدث بيانات الإشعاع للواجهة - جلب من الذاكرة أولاً"""
    try:
        # محاولة جلب البيانات من التخزين المؤقت أولاً
        latest_reading = radiation_cache.get_latest_reading()

        # إذا لم توجد بيانات في التخزين المؤقت، جلب من قاعدة البيانات المحلية
        if not latest_reading:
            update_cache_from_local_db()
            latest_reading = radiation_cache.get_latest_reading()

        if latest_reading:
            print("📊 تم جلب البيانات من التخزين المؤقت")
            response = jsonify({
                "success": True,
                "data": {
                    "cpm": latest_reading.cpm,
                    "sourcePower": latest_reading.source_power,
                    "absorbedDose": latest_reading.absorbed_dose_rate,
                    "totalDose": latest_reading.total_absorbed_dose,
                    "timestamp": latest_reading.timestamp.isoformat(),
                    "source": "cache"
                }
            })
            # منع التخزين المؤقت في المتصفح
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        # إذا لم توجد بيانات في الذاكرة، جرب قاعدة البيانات المحلية
        print("⚠️ لا توجد بيانات في التخزين المؤقت، جاري البحث في قاعدة البيانات المحلية...")

        # جلب البيانات من SQLite المحلية
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # إنشاء الجدول إذا لم يكن موجوداً
            c.execute('''CREATE TABLE IF NOT EXISTS radiation_readings_local
                         (id INTEGER PRIMARY KEY AUTOINCREMENT,
                          cpm INTEGER,
                          source_power REAL,
                          absorbed_dose_rate REAL,
                          total_absorbed_dose REAL,
                          session_id INTEGER,
                          timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            c.execute('''CREATE INDEX IF NOT EXISTS idx_radiation_readings_session_id
                         ON radiation_readings_local (session_id)''')

            # جلب أحدث قراءة
            c.execute('''SELECT cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp
                         FROM radiation_readings_local
                         ORDER BY timestamp DESC
                         LIMIT 1''')

            row = c.fetchone()
            conn.close()

            if row:
                response = jsonify({
                    "success": True,
                    "data": {
                        "cpm": row[0],
                        "sourcePower": row[1],
                        "absorbedDose": row[2],
                        "totalDose": row[3],
                        "timestamp": row[4],
                        "source": "database"
                    }
                })
                # منع التخزين المؤقت في المتصفح
                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                response.headers['Pragma'] = 'no-cache'
                response.headers['Expires'] = '0'
                return response
        except Exception as db_error:
            print(f"❌ خطأ في الاتصال بقاعدة البيانات: {db_error}")

        # إذا لم توجد بيانات في أي مكان، إرجاع بيانات افتراضية
        print("⚠️ لا توجد بيانات متاحة")
        response = jsonify({
            "success": True,
            "data": {
                "cpm": 0,
                "sourcePower": 0.0,
                "absorbedDose": 0.0,
                "totalDose": 0.0,
                "timestamp": datetime.now().isoformat(),
                "source": "default"
            }
        })
        # منع التخزين المؤقت في المتصفح
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except Exception as e:
        print(f"❌ خطأ في جلب بيانات الإشعاع: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/system_status', methods=['GET'])
def get_system_status():
    """فحص حالة النظام مع معلومات التخزين المؤقت"""
    try:
        # الحصول على إحصائيات التخزين المؤقت
        cache_stats = radiation_cache.get_cache_stats()

        # فحص حالة قاعدة البيانات المحلية
        db_status = "unknown"
        try:
            # فحص اتصال SQLite
            conn = sqlite3.connect(DB_PATH)
            conn.close()
            db_status = "connected"
        except Exception:
            db_status = "disconnected"

        return jsonify({
            "success": True,
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "database": {
                "enabled": True,
                "status": db_status,
                "type": "sqlite"
            },
            "cache": {
                "total_readings": cache_stats["total_readings"],
                "saved_readings": cache_stats["saved_readings"],
                "unsaved_readings": cache_stats["unsaved_readings"],
                "oldest_timestamp": cache_stats["oldest_timestamp"].isoformat() if cache_stats["oldest_timestamp"] else None,
                "newest_timestamp": cache_stats["newest_timestamp"].isoformat() if cache_stats["newest_timestamp"] else None
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/cache_stats', methods=['GET'])
def get_cache_stats():
    """الحصول على إحصائيات التخزين المؤقت"""
    try:
        stats = radiation_cache.get_cache_stats()
        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ===================================
# دوال إدارة فترات التعرض
# ===================================

def start_exposure_session(employee_id):
    """بدء أو استئناف فترة تعرض للموظف - نظام الجلسة الواحدة اليومية"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # الحصول على التاريخ الحالي (بدون الوقت)
        current_time = get_current_time_precise()
        current_date = current_time.date()

        # الحصول على التاريخ الحالي (بدون الوقت)
        current_time = get_current_time_precise()
        current_date = current_time.date()
        current_total_dose = get_current_total_dose()

        # التحقق من وجود جلسة نشطة حالياً لهذا الموظف (بغض النظر عن التاريخ)
        c.execute('''SELECT id, check_in_time, initial_total_dose, session_date, is_active
                     FROM employee_exposure_sessions
                     WHERE employee_id = ? AND is_active = 1
                     ORDER BY check_in_time DESC
                     LIMIT 1''',
                  (employee_id,))

        existing_session = c.fetchone()

        if existing_session:
            session_id, old_check_in_time, old_initial_dose, session_date, was_active = existing_session
            
            print(f"🔍 جلسة نشطة موجودة بالفعل:")
            print(f"   Session ID: {session_id}")
            print(f"   تاريخ الجلسة: {session_date}")
            print(f"   وقت البدء الأصلي: {old_check_in_time}")
            print(f"   الجرعة الأولية: {old_initial_dose:.6f} μSv")
            print(f"   الجرعة الحالية: {current_total_dose:.6f} μSv")
            
            conn.close()
            
            return {
                "success": True,
                "session_id": session_id,
                "initial_dose": old_initial_dose,
                "current_total_dose": current_total_dose,
                "accumulated_exposure": current_total_dose - old_initial_dose,
                "resumed": True,
                "check_in_time": str(old_check_in_time),
                "session_date": str(session_date),
                "original_start_time": old_check_in_time,
                "message": "جلسة نشطة قيد التشغيل بالفعل"
            }
        else:
            # التحقق من وجود جلسات قديمة نشطة (من أيام سابقة) وإغلاقها تلقائياً
            c.execute('''SELECT id FROM employee_exposure_sessions
                         WHERE employee_id = ?
                         AND is_active = 1
                         AND DATE(session_date) < DATE(?)''',
                      (employee_id, current_date))

            old_sessions = c.fetchall()
            if old_sessions:
                print(f"⚠️ تم العثور على {len(old_sessions)} جلسة قديمة نشطة - سيتم إغلاقها تلقائياً")
                for old_session in old_sessions:
                    c.execute('''UPDATE employee_exposure_sessions
                                SET is_active = 0,
                                    notes = COALESCE(notes, '') || ' [تم الإغلاق التلقائي]'
                                WHERE id = ?''', (old_session[0],))
                conn.commit() # Commit these changes before creating a new session

            # إنشاء جلسة جديدة ليوم جديد
            c.execute('''INSERT INTO employee_exposure_sessions
                         (employee_id, check_in_time, initial_total_dose, session_date, is_active, daily_total_exposure)
                         VALUES (?, ?, ?, ?, 1, 0.0)''',
                      (employee_id, current_time, current_total_dose, current_date))

            session_id = c.lastrowid
            conn.commit()
            conn.close()

            print(f"✅ بدء جلسة تعرض جديدة للموظف {employee_id}")
            print(f"   Session ID: {session_id}")
            print(f"   التاريخ: {current_date}")
            print(f"   الوقت: {current_time}")
            print(f"   الجرعة الإجمالية الحالية: {current_total_dose:.6f} μSv")

            return {
                "success": True,
                "session_id": session_id,
                "initial_dose": current_total_dose,
                "resumed": False,
                "check_in_time": current_time.isoformat(),
                "session_date": str(current_date),
                "message": "تم إنشاء جلسة يومية جديدة"
            }

    except Exception as e:
        print(f"❌ خطأ في بدء/استئناف فترة التعرض: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

def end_exposure_session(employee_id):
    """إنهاء فترة التعرض للموظف - تصفير الوقت والاحتفاظ بالجرعة التراكمية"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # البحث عن فترة التعرض النشطة
        c.execute('''SELECT id, check_in_time, initial_total_dose, session_date
                     FROM employee_exposure_sessions
                     WHERE employee_id = ? AND is_active = 1''', (employee_id,))

        session = c.fetchone()
        if not session:
            conn.close()
            print(f"⚠️ لا توجد جلسة نشطة للموظف {employee_id}")
            return {"success": False, "error": "No active exposure session found"}

        session_id, check_in_time, initial_dose, session_date = session

        # الحصول على الجرعة الإجمالية الحالية
        final_dose = get_current_total_dose()

        # حساب مدة التعرض بدقة عالية باستخدام النظام المحسن
        check_out_dt = get_current_time_precise()

        # تطبيع وقت الدخول أولاً
        check_in_dt = time_calculator.normalize_datetime(check_in_time)
        duration_data = calculate_duration_precise(check_in_dt, check_out_dt)

        # استخراج القيم بدقة عالية
        duration_seconds_precise = Decimal(str(duration_data['seconds']))
        duration_minutes = int(duration_data['minutes'])
        duration_hours = Decimal(str(duration_data['hours']))

        # حساب التعرض الفعلي للموظف خلال فترة العمل - محدث
        # بدلاً من الاعتماد على الجرعة الإجمالية العامة، نحسب التعرض من القراءات الفعلية
        actual_exposure = calculate_employee_exposure(employee_id, check_in_dt, check_out_dt, session_id)

        # إذا لم نتمكن من حساب التعرض الفعلي، نستخدم طريقة بديلة
        if actual_exposure is None:
            # حساب التعرض بناءً على الفرق في الجرعة الإجمالية
            dose_difference = final_dose - initial_dose

            # إذا كان الفرق صفر أو سالب، نحسب بناءً على معدل الجرعة والوقت
            if dose_difference <= 0:
                # الحصول على متوسط معدل الجرعة من القراءات الحديثة
                avg_dose_rate = get_average_dose_rate_from_cache()
                if avg_dose_rate > 0 and duration_hours > 0:
                    total_exposure = float(avg_dose_rate * duration_hours)
                    print(f"📊 حساب التعرض من معدل الجرعة: {avg_dose_rate:.3f} μSv/h × {float(duration_hours):.3f} h = {total_exposure:.3f} μSv")
                else:
                    total_exposure = 0.0
            else:
                total_exposure = dose_difference
        else:
            total_exposure = actual_exposure

        # حساب متوسط معدل الجرعة بدقة عالية
        if duration_hours > 0:
            average_dose_rate = float(Decimal(str(total_exposure)) / Decimal(str(duration_hours)))
        else:
            average_dose_rate = 0.0

        # الحصول على إحصائيات معدل الجرعة خلال الفترة
        max_dose_rate, min_dose_rate, avg_dose_rate_from_readings = get_dose_rate_stats(check_in_dt, check_out_dt)

        # استخدام متوسط معدل الجرعة من القراءات إذا كان متاحاً
        if avg_dose_rate_from_readings > 0:
            average_dose_rate = avg_dose_rate_from_readings

        # حساب الجرعة اليومية (الفرق بين الجرعة النهائية والأولية)
        daily_exposure = total_exposure  # الجرعة المحسوبة من القراءات الفعلية

        # تحديث فترة التعرض مع إضافة الحقول الجديدة
        c.execute('''UPDATE employee_exposure_sessions
                     SET check_out_time = ?,
                         final_total_dose = ?,
                         exposure_duration_minutes = ?,
                         average_dose_rate = ?,
                         total_exposure = ?,
                         max_dose_rate = ?,
                         min_dose_rate = ?,
                         daily_total_exposure = ?,
                         is_active = 0
                     WHERE id = ?''',
                  (check_out_dt, final_dose, duration_minutes, average_dose_rate,
                   total_exposure, max_dose_rate, min_dose_rate, daily_exposure, session_id))

        conn.commit()
        conn.close()

        print(f"📊 تفاصيل الجلسة:")
        print(f"   الجرعة اليومية (تم تصفيرها): {daily_exposure:.6f} μSv")
        print(f"   الجرعة الإجمالية التراكمية (محفوظة): {final_dose:.6f} μSv")
        print(f"   الوقت (تم تصفيره): {duration_minutes} دقيقة")
        print(f"   ✅ تم إغلاق الجلسة - is_active = 0")

        # تصنيف مستوى الأمان
        safety_status, safety_percentage, risk_level, is_pregnant = classify_radiation_safety(
            average_dose_rate, total_exposure, duration_minutes, employee_id
        )

        # طباعة النتائج بدقة محسنة
        formatted_duration = duration_data['formatted']
        print(f"✅ انتهاء فترة التعرض للموظف {employee_id}")
        print(f"   المدة: {formatted_duration}")
        print(f"   المدة بالدقائق: {duration_minutes}")
        print(f"   المدة بالساعات: {float(duration_hours):.6f}")
        print(f"   التعرض الإجمالي: {total_exposure:.6f} μSv")
        print(f"   متوسط معدل الجرعة: {average_dose_rate:.6f} μSv/h")
        print(f"   أقصى معدل جرعة: {max_dose_rate:.6f} μSv/h")
        print(f"   أقل معدل جرعة: {min_dose_rate:.6f} μSv/h")
        print(f"   تصنيف الأمان: {safety_status}")
        print(f"   مستوى الخطر: {risk_level}")
        print(f"   نسبة الأمان: {safety_percentage:.1f}%")

        # حساب النسبة المئوية للحد اليومي بناءً على حالة الحمل
        if is_pregnant:
            daily_limit = 3.7  # الحد اليومي للحامل
        else:
            daily_limit = 54.8  # الحد اليومي للعاملين العاديين

        return {
            "success": True,
            "session_id": session_id,
            "duration_minutes": duration_minutes,
            "duration_hours": round(float(duration_hours), 6),
            "duration_seconds": round(float(duration_seconds_precise), 3),
            "duration_formatted": formatted_duration,
            "total_exposure": round(total_exposure, 6),
            "average_dose_rate": round(average_dose_rate, 6),
            "max_dose_rate": round(max_dose_rate, 6),
            "min_dose_rate": round(min_dose_rate, 6),
            "safety_status": safety_status,
            "safety_percentage": safety_percentage,
            "risk_level": risk_level,
            "is_pregnant": is_pregnant,
            "daily_limit": daily_limit,
            "daily_limit_percentage": round((total_exposure / daily_limit) * 100, 3),
            "annual_projection": round(total_exposure * 365, 3),
            "precision_level": "high",
            "calculation_method": "enhanced_time_system"
        }

    except Exception as e:
        print(f"❌ خطأ في إنهاء فترة التعرض: {e}")
        return {"success": False, "error": str(e)}

def get_current_total_dose():
    """الحصول على الجرعة الإجمالية الحالية من التخزين المؤقت أو قاعدة البيانات"""
    try:
        # أولاً: محاولة الحصول على البيانات من التخزين المؤقت
        if radiation_cache and hasattr(radiation_cache, 'get_latest_reading'):
            latest_reading = radiation_cache.get_latest_reading()
            if latest_reading and hasattr(latest_reading, 'total_absorbed_dose'):
                print(f"📊 جرعة إجمالية من التخزين المؤقت: {latest_reading.total_absorbed_dose} μSv")
                return latest_reading.total_absorbed_dose

        # ثانياً: الحصول من قاعدة البيانات كبديل
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT total_absorbed_dose FROM radiation_readings_local
                     ORDER BY timestamp DESC LIMIT 1''')
        row = c.fetchone()
        conn.close()
        if row:
            print(f"📊 جرعة إجمالية من قاعدة البيانات: {row[0]} μSv")
            return row[0]

        print("⚠️ لا توجد قراءات جرعة متاحة")
        return 0.0

    except Exception as e:
        print(f"❌ خطأ في الحصول على الجرعة الإجمالية: {e}")
        return 0.0

def get_average_dose_rate_from_cache():
    """الحصول على متوسط معدل الجرعة من التخزين المؤقت"""
    try:
        if radiation_cache and hasattr(radiation_cache, 'get_recent_readings'):
            # الحصول على آخر 10 قراءات
            recent_readings = radiation_cache.get_recent_readings(10)
            if recent_readings:
                total_rate = sum(reading.absorbed_dose_rate for reading in recent_readings)
                avg_rate = total_rate / len(recent_readings)
                print(f"📊 متوسط معدل الجرعة من {len(recent_readings)} قراءة: {avg_rate:.3f} μSv/h")
                return avg_rate

        # بديل: الحصول من قاعدة البيانات
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT AVG(absorbed_dose_rate) FROM radiation_readings_local
                     WHERE timestamp > datetime('now', '-1 hour')''')
        row = c.fetchone()
        conn.close()

        if row and row[0]:
            print(f"📊 متوسط معدل الجرعة من قاعدة البيانات: {row[0]:.3f} μSv/h")
            return row[0]

        return 0.0

    except Exception as e:
        print(f"❌ خطأ في الحصول على متوسط معدل الجرعة: {e}")
        return 0.0

def calculate_employee_exposure(employee_id, start_time, end_time, session_id=None):
    """حساب التعرض الفعلي للموظف خلال فترة العمل بدقة عالية - محدث"""
    try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # تطبيع الأوقات باستخدام النظام المحسن
            start_dt = time_calculator.normalize_datetime(start_time)
            end_dt = time_calculator.normalize_datetime(end_time)

            # الحصول علم جميع القراءات خلال فترة العمل - محدث لاستخدام session_id
            if session_id:
                # استخدام session_id للحصول على قراءات محددة للجلسة
                c.execute('''SELECT absorbed_dose_rate, timestamp
                             FROM radiation_readings_local
                             WHERE session_id = ?
                             ORDER BY timestamp''',
                          (session_id,))
                print(f"📊 استخدام قراءات الجلسة (session_id={session_id})")
            else:
                # طريقة قديمة: البحث بناءً على الفترة الزمنية
                c.execute('''SELECT absorbed_dose_rate, timestamp
                             FROM radiation_readings_local
                             WHERE timestamp BETWEEN ? AND ?
                             AND (session_id IS NULL OR session_id IN 
                                  (SELECT id FROM employee_exposure_sessions WHERE employee_id = ?))
                             ORDER BY timestamp''',
                          (start_dt, end_dt, employee_id))
                print(f"⚠️ استخدام الطريقة القديمة (بناءً على الفترة الزمنية)")

            readings = c.fetchall()
            conn.close()

            if not readings:
                print(f"⚠️ لا توجد قراءات إشعاعية للموظف {employee_id} خلال الفترة")
                return None

            total_exposure = Decimal('0')
            previous_time = start_dt

            print(f"📊 حساب التعرض للموظف {employee_id}:")
            print(f"   عدد القراءات: {len(readings)}")

            for i, (dose_rate, timestamp) in enumerate(readings):
                # تطبيع وقت القراءة
                current_time = time_calculator.normalize_datetime(timestamp)

                # حساب الفترة الزمنية بدقة عالية
                _, _, time_diff_hours, _ = time_calculator.calculate_duration(previous_time, current_time)

                # حساب التعرض للفترة بدقة عالية
                exposure_increment = time_calculator.calculate_precise_exposure(dose_rate, time_diff_hours)
                total_exposure += exposure_increment

                print(f"   القراءة {i+1}: {dose_rate:.6f} μSv/h × {float(time_diff_hours):.6f} h = {float(exposure_increment):.6f} μSv")

                previous_time = current_time

            # إضافة التعرض للفترة الأخيرة حتى نهاية العمل
            if readings:
                last_reading_time = time_calculator.normalize_datetime(readings[-1][1])
                _, _, final_time_diff, _ = time_calculator.calculate_duration(last_reading_time, end_dt)

                if final_time_diff > 0:
                    last_dose_rate = readings[-1][0]
                    final_exposure = time_calculator.calculate_precise_exposure(last_dose_rate, final_time_diff)
                    total_exposure += final_exposure
                    print(f"   الفترة الأخيرة: {last_dose_rate:.6f} μSv/h × {float(final_time_diff):.6f} h = {float(final_exposure):.6f} μSv")

            final_exposure_float = float(total_exposure)
            print(f"   إجمالي التعرض: {final_exposure_float:.6f} μSv")

            return final_exposure_float

    except Exception as e:
        print(f"❌ خطأ في حساب التعرض الفعلي للموظف: {e}")
        return None

def get_dose_rate_stats(start_time, end_time):
    """الحصول على إحصائيات معدل الجرعة خلال فترة معينة من قاعدة البيانات المحلية"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute('''SELECT MAX(absorbed_dose_rate), MIN(absorbed_dose_rate), AVG(absorbed_dose_rate)
                     FROM radiation_readings_local
                     WHERE timestamp BETWEEN ? AND ?''',
                  (start_time, end_time))
        row = c.fetchone()
        conn.close()

        if row and row[0] is not None:
            return row[0], row[1], row[2]  # max, min, avg

        return 0.0, 0.0, 0.0

    except Exception as e:
        print(f"❌ خطأ في الحصول على إحصائيات معدل الجرعة: {e}")
        return 0.0, 0.0, 0.0

# ===================================
# دوال مساعدة لحساب الجرعات اليومية والتراكمية
# ===================================

def get_employee_daily_dose(employee_id, date=None):
    """حساب الجرعة اليومية للموظف في تاريخ محدد"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        if date is None:
            date = datetime.now().date()

        # جلب جميع الجلسات في هذا اليوم
        c.execute('''SELECT SUM(daily_total_exposure)
                     FROM employee_exposure_sessions
                     WHERE employee_id = ?
                     AND DATE(session_date) = DATE(?)''',
                  (employee_id, date))

        result = c.fetchone()
        conn.close()

        daily_dose = result[0] if result and result[0] else 0.0
        print(f"📊 الجرعة اليومية للموظف {employee_id} في {date}: {daily_dose:.6f} μSv")

        return daily_dose

    except Exception as e:
        print(f"❌ خطأ في حساب الجرعة اليومية: {e}")
        return 0.0

def get_employee_cumulative_dose(employee_id):
    """حساب الجرعة التراكمية الإجمالية للموظف منذ بداية العمل"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # جلب مجموع جميع الجرعات اليومية
        c.execute('''SELECT SUM(daily_total_exposure)
                     FROM employee_exposure_sessions
                     WHERE employee_id = ?
                     AND is_active = 0''',  # فقط الجلسات المغلقة
                  (employee_id,))

        result = c.fetchone()
        conn.close()

        cumulative_dose = result[0] if result and result[0] else 0.0
        print(f"📊 الجرعة التراكمية للموظف {employee_id}: {cumulative_dose:.6f} μSv")

        return cumulative_dose

    except Exception as e:
        print(f"❌ خطأ في حساب الجرعة التراكمية: {e}")
        return 0.0

def check_dose_limits(employee_id, daily_dose, cumulative_dose):
    """التحقق من تجاوز الحدود اليومية والسنوية"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # جلب معلومات الموظف (للتحقق من حالة الحمل)
        c.execute('SELECT gender, pregnant FROM employees WHERE employee_id = ?', (employee_id,))
        employee_info = c.fetchone()
        conn.close()

        is_pregnant = False
        if employee_info:
            gender, pregnant = employee_info
            is_pregnant = (gender == 'أنثى' and pregnant == 'نعم')

        # تحديد الحدود بناءً على حالة الحمل
        if is_pregnant:
            daily_limit = 3.7      # μSv/يوم للحامل
            annual_limit = 1000.0  # μSv/سنة للحامل
        else:
            daily_limit = 54.8     # μSv/يوم للعاملين
            annual_limit = 20000.0 # μSv/سنة للعاملين

        # حساب النسب المئوية
        daily_percentage = (daily_dose / daily_limit) * 100 if daily_limit > 0 else 0
        annual_percentage = (cumulative_dose / annual_limit) * 100 if annual_limit > 0 else 0

        # تحديد حالة التحذير
        warnings = []
        if daily_percentage >= 100:
            warnings.append(f"⚠️ تجاوز الحد اليومي: {daily_percentage:.1f}%")
        elif daily_percentage >= 80:
            warnings.append(f"⚠️ اقتراب من الحد اليومي: {daily_percentage:.1f}%")

        if annual_percentage >= 100:
            warnings.append(f"🚨 تجاوز الحد السنوي: {annual_percentage:.1f}%")
        elif annual_percentage >= 80:
            warnings.append(f"⚠️ اقتراب من الحد السنوي: {annual_percentage:.1f}%")

        return {
            "is_pregnant": is_pregnant,
            "daily_limit": daily_limit,
            "annual_limit": annual_limit,
            "daily_dose": daily_dose,
            "cumulative_dose": cumulative_dose,
            "daily_percentage": round(daily_percentage, 2),
            "annual_percentage": round(annual_percentage, 2),
            "warnings": warnings,
            "safe": len(warnings) == 0
        }

    except Exception as e:
        print(f"❌ خطأ في التحقق من الحدود: {e}")
        return None

@app.route('/api/employee_exposure', methods=['POST'])
def manage_employee_exposure():
    """إدارة فترات التعرض للموظفين"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        action = data.get('action')
        employee_id = data.get('employee_id')

        if not action or not employee_id:
            return jsonify({"success": False, "error": "Missing action or employee_id"}), 400

        if action == 'start':
            result = start_exposure_session(employee_id)
        elif action == 'end':
            result = end_exposure_session(employee_id)
        else:
            return jsonify({"success": False, "error": "Invalid action"}), 400

        return jsonify(result)

    except Exception as e:
        print(f"❌ خطأ في إدارة تعرض الموظف: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/employee_dose_summary/<employee_id>', methods=['GET'])
def get_employee_dose_summary(employee_id):
    """الحصول على ملخص الجرعات اليومية والتراكمية للموظف"""
    try:
        # حساب الجرعة اليومية
        daily_dose = get_employee_daily_dose(employee_id)

        # حساب الجرعة التراكمية
        cumulative_dose = get_employee_cumulative_dose(employee_id)

        # التحقق من الحدود
        limits_check = check_dose_limits(employee_id, daily_dose, cumulative_dose)

        return jsonify({
            "success": True,
            "employee_id": employee_id,
            "daily_dose": round(daily_dose, 6),
            "cumulative_dose": round(cumulative_dose, 6),
            "limits": limits_check
        })

    except Exception as e:
        print(f"❌ خطأ في جلب ملخص الجرعات: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/employee_exposure_history/<employee_id>', methods=['GET'])
def get_employee_exposure_history(employee_id):
    """الحصول على تاريخ التعرض للموظف مع الجرعات اليومية"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # الحصول على آخر 30 فترة تعرض مع الحقول الجديدة
        c.execute('''SELECT check_in_time, check_out_time, exposure_duration_minutes,
                            total_exposure, average_dose_rate, max_dose_rate,
                            safety_alerts, notes, session_date, is_active, daily_total_exposure
                     FROM employee_exposure_sessions
                     WHERE employee_id = ?
                     ORDER BY check_in_time DESC
                     LIMIT 30''', (employee_id,))

        sessions = []
        for row in c.fetchall():
            sessions.append({
                "check_in_time": row[0],
                "check_out_time": row[1],
                "duration_minutes": row[2],
                "total_exposure": row[3],
                "average_dose_rate": row[4],
                "max_dose_rate": row[5],
                "safety_alerts": row[6],
                "notes": row[7],
                "session_date": row[8],
                "is_active": row[9],
                "daily_total_exposure": row[10]
            })

        # حساب الإحصائيات المحدثة
        c.execute('''SELECT
                        COUNT(*) as total_sessions,
                        SUM(daily_total_exposure) as total_daily_exposure,
                        AVG(average_dose_rate) as avg_dose_rate,
                        MAX(max_dose_rate) as max_dose_rate_ever,
                        SUM(safety_alerts) as total_alerts
                     FROM employee_exposure_sessions
                     WHERE employee_id = ? AND is_active = 0''', (employee_id,))

        stats_row = c.fetchone()
        stats = {
            "total_sessions": stats_row[0] if stats_row[0] else 0,
            "total_cumulative_dose": stats_row[1] if stats_row[1] else 0.0,
            "average_dose_rate": stats_row[2] if stats_row[2] else 0.0,
            "max_dose_rate_ever": stats_row[3] if stats_row[3] else 0.0,
            "total_alerts": stats_row[4] if stats_row[4] else 0
        }

        conn.close()

        return jsonify({
            "success": True,
            "employee_id": employee_id,
            "sessions": sessions,
            "statistics": stats
        })

    except Exception as e:
        print(f"❌ خطأ في الحصول على تاريخ التعرض: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ===================================
# API Endpoints لاستقبال بيانات ESP32
# ===================================

@app.route('/data', methods=['POST'])
def receive_radiation_data():
    """استقبال بيانات الإشعاع من ESP32 وحفظها فوراً في الذاكرة"""
    try:
        # التحقق من وجود البيانات
        if not request.json:
            return jsonify({
                "success": False,
                "error": "No JSON data received"
            }), 400

        data = request.json

        # التحقق من وجود الحقول المطلوبة
        required_fields = ['cpm', 'source_power', 'absorbed_dose', 'total_dose']
        missing_fields = [field for field in required_fields if field not in data]

        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {missing_fields}"
            }), 400

        # استخراج البيانات
        cpm = int(data['cpm'])
        source_power = float(data['source_power'])
        absorbed_dose_rate = float(data['absorbed_dose'])
        total_absorbed_dose = float(data['total_dose'])

        print(f"📊 بيانات جديدة من ESP32:")
        print(f"   CPM: {cpm}")
        print(f"   Source Power: {source_power} μSv/h")
        print(f"   Absorbed Dose Rate: {absorbed_dose_rate} μSv/h")
        print(f"   Total Dose: {total_absorbed_dose} μSv")

        # حفظ البيانات فوراً في التخزين المؤقت
        reading = radiation_cache.add_reading(
            cpm=cpm,
            source_power=source_power,
            absorbed_dose_rate=absorbed_dose_rate,
            total_absorbed_dose=total_absorbed_dose,
            sensor_id=DEFAULT_SENSOR_ID
        )

        print("✅ تم حفظ البيانات في الذاكرة المؤقتة")
        print("🔄 سيتم حفظ البيانات في قاعدة البيانات في الخلفية")

        # إرجاع استجابة فورية
        return jsonify({
            "success": True,
            "message": "Data received and cached successfully",
            "data": {
                "cpm": cpm,
                "source_power": source_power,
                "absorbed_dose_rate": absorbed_dose_rate,
                "total_absorbed_dose": total_absorbed_dose,
                "timestamp": reading.timestamp.isoformat(),
                "cached": True
            }
        }), 200

    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"Invalid data format: {str(e)}"
        }), 400

    except Exception as e:
        print(f"❌ خطأ غير متوقع: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.route('/api/radiation/latest', methods=['GET'])
def get_latest_radiation():
    """الحصول على أحدث قراءة إشعاع من قاعدة البيانات المحلية"""
    try:
        # قراءة من SQLite المحلية
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''SELECT cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp
                     FROM radiation_readings_local
                     ORDER BY timestamp DESC
                     LIMIT 1''')

        row = c.fetchone()
        conn.close()

        if row:
            return jsonify({
                "success": True,
                "data": {
                    "cpm": row[0],
                    "source_power": row[1],
                    "absorbed_dose_rate": row[2],
                    "total_absorbed_dose": row[3],
                    "timestamp": row[4]
                }
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "No radiation data found"
            }), 404

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500



# ===================================
# API: إعدادات نوع الأنبوب للتكامل مع ESP32
# ===================================

@app.route('/api/get_tube_settings', methods=['GET'])
def get_tube_settings():
    """جلب نوع أنبوب Geiger الحالي من system_settings"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # ضمان وجود قيمة افتراضية
        c.execute('''INSERT OR IGNORE INTO system_settings (setting_key, setting_value, description)
                     VALUES ('tube_type', 'J305', 'نوع أنبوب Geiger المستخدم (SBM20 أو J305)')''')
        conn.commit()
        c.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'tube_type'")
        row = c.fetchone()
        conn.close()
        tube_type = row[0] if row and row[0] else 'J305'
        return jsonify({'success': True, 'tube_type': tube_type})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/set_tube_type', methods=['POST'])
def set_tube_type():
    """تعيين نوع أنبوب Geiger (SBM20 أو J305) ويُحفظ في system_settings"""
    try:
        data = request.json or {}
        tube_type = data.get('tube_type')
        if tube_type not in ['SBM20', 'J305']:
            return jsonify({'success': False, 'error': 'نوع أنبوب غير صحيح. استخدم SBM20 أو J305'}), 400
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO system_settings (setting_key, setting_value, description)
                     VALUES ('tube_type', 'J305', 'نوع أنبوب Geiger المستخدم (SBM20 أو J305)')''')
        c.execute('''UPDATE system_settings 
                     SET setting_value = ?, updated_at = CURRENT_TIMESTAMP
                     WHERE setting_key = 'tube_type' ''', (tube_type,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'tube_type': tube_type, 'message': f'تم تعيين نوع الأنبوب إلى {tube_type}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# واجهة إضافة موظف بدون صورة لنظام الإشعاع
@app.route('/api/add_radiation_employee', methods=['POST'])
def add_radiation_employee():
    """إضافة موظف جديد لنظام مراقبة الإشعاع (بدون صورة) - موحّد على attendance.db"""
    try:
        data = request.get_json() or {}
        
        employee_id = data.get('employee_id')
        name = data.get('name')
        department = data.get('department')
        daily_limit = float(data.get('daily_limit', 54.8))  # μSv
        monthly_limit = float(data.get('monthly_limit', 1500.0))  # μSv
        annual_limit = float(data.get('annual_limit', 20000.0))  # μSv
        
        # التحقق من الحقول المطلوبة
        if not employee_id or not name:
            return jsonify({'success': False, 'error': 'يرجى توفير رقم الموظف والاسم'}), 400
        
        # التحقق من صحة الحدود
        if daily_limit <= 0 or monthly_limit <= 0 or annual_limit <= 0:
            return jsonify({'success': False, 'error': 'حدود الإشعاع يجب أن تكون قيم موجبة'}), 400
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # محاولة إضافة أعمدة حدود الجرعات إذا لم تكن موجودة في جدول employees
        for col_def in [
            ("daily_limit", "REAL", "54.8"),
            ("monthly_limit", "REAL", "1500.0"),
            ("annual_limit", "REAL", "20000.0")
        ]:
            col, typ, dflt = col_def
            try:
                c.execute(f"ALTER TABLE employees ADD COLUMN {col} {typ} DEFAULT {dflt}")
            except Exception:
                pass  # العمود موجود بالفعل
        
        # التحقق من عدم وجود الموظف مسبقاً
        c.execute('SELECT employee_id FROM employees WHERE employee_id = ?', (employee_id,))
        if c.fetchone():
            # تحديث حدود الجرعات إذا كان الموظف موجوداً بالفعل
            try:
                c.execute('''UPDATE employees SET daily_limit = ?, monthly_limit = ?, annual_limit = ?, updated_at = CURRENT_TIMESTAMP
                             WHERE employee_id = ?''', (daily_limit, monthly_limit, annual_limit, employee_id))
                conn.commit()
            except Exception:
                pass
            conn.close()
            return jsonify({'success': False, 'error': f'الموظف {employee_id} موجود مسبقاً'}), 400
        
        # إدراج الموظف الجديد ثم تحديث الحدود
        c.execute('''INSERT INTO employees (employee_id, name, department)
                     VALUES (?, ?, ?)''', (employee_id, name, department))
        
        # تحديث حدود الجرعات
        try:
            c.execute('''UPDATE employees 
                         SET daily_limit = ?, monthly_limit = ?, annual_limit = ?, updated_at = CURRENT_TIMESTAMP
                         WHERE employee_id = ?''', (daily_limit, monthly_limit, annual_limit, employee_id))
        except Exception as upd_err:
            logger.warning(f"Failed to set dose limits for employee {employee_id}: {upd_err}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'تم إضافة الموظف {name} بنجاح',
            'employee': {
                'employee_id': employee_id,
                'name': name,
                'department': department,
                'daily_limit': daily_limit,
                'monthly_limit': monthly_limit,
                'annual_limit': annual_limit
            }
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': f'خطأ في البيانات: {str(e)}'}), 400
    except Exception as e:
        logger.exception(f"Error adding radiation employee: {e}")
        return jsonify({'success': False, 'error': f'خطأ في إضافة الموظف: {str(e)}'}), 500

@app.route('/api/employee/<employee_id>', methods=['GET'])
def get_radiation_employee(employee_id):
    """جلب معلومات موظف من نظام مراقبة الإشعاع - موحّد على attendance.db"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # ضمان أعمدة حدود الجرعات موجودة
        for col_def in ["daily_limit", "monthly_limit", "annual_limit"]:
            try:
                c.execute(f"ALTER TABLE employees ADD COLUMN {col_def} REAL")
            except Exception:
                pass
        
        c.execute('''SELECT employee_id, name, department, daily_limit, monthly_limit, annual_limit, created_at
                     FROM employees WHERE employee_id = ?''', (employee_id,))
        
        row = c.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'success': False, 'error': f'الموظف {employee_id} غير موجود'}), 404
        
        employee = {
            'employee_id': row[0],
            'name': row[1],
            'department': row[2] or 'غير محدد',
            'daily_limit': row[3],
            'monthly_limit': row[4], 
            'annual_limit': row[5],
            'created_at': row[6]
        }
        
        return jsonify({
            'success': True,
            'employee': employee
        })
        
    except Exception as e:
        logger.exception(f"Error getting employee info: {e}")
        return jsonify({'success': False, 'error': f'خطأ في جلب معلومات الموظف: {str(e)}'}), 500

# ===================================
# واجهات API لإدارة جلسات التعرض الإشعاعي
# ===================================

@app.route('/api/start_exposure_session', methods=['POST'])
def start_radiation_exposure_session():
    """بدء جلسة تعرض إشعاعي جديدة - موحّد على attendance.db"""
    try:
        data = request.get_json() or {}
        employee_id = data.get('employee_id')
        
        if not employee_id:
            return jsonify({'success': False, 'error': 'رقم الموظف مطلوب'}), 400
        
        # التحقق من وجود الموظف
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('SELECT employee_id, name FROM employees WHERE employee_id = ?', (employee_id,))
        employee = c.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({'success': False, 'error': f'الموظف {employee_id} غير موجود'}), 404
        
        # إنشاء جدول جلسات الإشعاع إذا لم يكن موجوداً في قاعدة البيانات الموحدة
        c.execute('''CREATE TABLE IF NOT EXISTS radiation_exposure_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT NOT NULL,
                    start_time DATETIME,
                    end_time DATETIME,
                    initial_dose REAL DEFAULT 0.0,
                    current_dose REAL DEFAULT 0.0,
                    final_dose REAL DEFAULT 0.0,
                    total_dose REAL DEFAULT 0.0,
                    duration_minutes REAL DEFAULT 0.0,
                    average_dose_rate REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
                )''')
        
        # التحقق من عدم وجود جلسة نشطة
        c.execute('''SELECT id, start_time FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND end_time IS NULL''', (employee_id,))
        active_session = c.fetchone()
        
        if active_session:
            conn.close()
            return jsonify({
                'success': True,
                'session': {
                    'session_id': active_session[0],
                    'employee_id': employee_id,
                    'start_time': active_session[1],
                    'status': 'already_active'
                },
                'message': 'يوجد جلسة نشطة بالفعل للموظف'
            })
        
        # إنشاء جلسة جديدة
        start_time = datetime.now().isoformat()
        
        c.execute('''INSERT INTO radiation_exposure_sessions 
                     (employee_id, start_time, initial_dose, current_dose, status)
                     VALUES (?, ?, 0.0, 0.0, 'active')''',
                 (employee_id, start_time))
        
        session_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'session': {
                'session_id': session_id,
                'employee_id': employee_id,
                'start_time': start_time,
                'status': 'new_session'
            },
            'message': 'تم بدء جلسة التعرض بنجاح'
        })
        
    except Exception as e:
        logger.exception(f"Error starting exposure session: {e}")
        return jsonify({'success': False, 'error': f'خطأ في بدء الجلسة: {str(e)}'}), 500

@app.route('/api/end_exposure_session', methods=['POST'])
def end_radiation_exposure_session():
    """إنهاء جلسة تعرض إشعاعي - موحّد على attendance.db"""
    try:
        data = request.get_json() or {}
        employee_id = data.get('employee_id')
        
        if not employee_id:
            return jsonify({'success': False, 'error': 'رقم الموظف مطلوب'}), 400
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # البحث عن الجلسة النشطة
        c.execute('''SELECT id, start_time, initial_dose, current_dose 
                     FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND end_time IS NULL''', (employee_id,))
        session = c.fetchone()
        
        if not session:
            conn.close()
            return jsonify({'success': False, 'error': 'لا توجد جلسة نشطة للموظف'}), 404
        
        session_id, start_time, initial_dose, current_dose = session
        end_time = datetime.now().isoformat()
        
        # حساب مدة الجلسة
        start_dt = datetime.fromisoformat(start_time)
        end_dt = datetime.fromisoformat(end_time)
        duration_seconds = (end_dt - start_dt).total_seconds()
        duration_minutes = duration_seconds / 60
        
        # حساب الجرعة الإجمالية للجلسة
        total_dose = max(0, current_dose - initial_dose)
        
        # حساب معدل الجرعة
        average_dose_rate = (total_dose / (duration_seconds / 3600)) if duration_seconds > 0 else 0
        
        # تحديث الجلسة
        c.execute('''UPDATE radiation_exposure_sessions 
                     SET end_time = ?, final_dose = ?, total_dose = ?, 
                         duration_minutes = ?, average_dose_rate = ?, status = 'completed'
                     WHERE id = ?''',
                 (end_time, current_dose, total_dose, duration_minutes, average_dose_rate, session_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'session': {
                'session_id': session_id,
                'employee_id': employee_id,
                'start_time': start_time,
                'end_time': end_time,
                'duration_minutes': round(duration_minutes, 2),
                'total_dose': round(total_dose, 3),
                'average_dose_rate': round(average_dose_rate, 3),
                'status': 'completed'
            },
            'message': 'تم إنهاء جلسة التعرض بنجاح'
        })
        
    except Exception as e:
        logger.exception(f"Error ending exposure session: {e}")
        return jsonify({'success': False, 'error': f'خطأ في إنهاء الجلسة: {str(e)}'}), 500

@app.route('/api/radiation_reading', methods=['POST'])
def receive_radiation_reading():
    """استقبال قراءة إشعاع من جهاز Arduino أو مصادر أخرى - موحّد على attendance.db"""
    try:
        data = request.get_json() or {}
        
        employee_id = data.get('employee_id')
        cpm = float(data.get('cpm', 0))
        absorbed_dose = float(data.get('absorbed_dose', 0))  # μSv
        cumulative_dose = float(data.get('cumulative_dose', 0))  # μSv
        tube_type = data.get('tube_type', 'J305')
        
        if not employee_id:
            return jsonify({'success': False, 'error': 'رقم الموظف مطلوب'}), 400
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # ضمان وجود جداول القراءات داخل قاعدة البيانات الموحدة
        c.execute('''CREATE TABLE IF NOT EXISTS radiation_exposure_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT NOT NULL,
                    start_time DATETIME,
                    end_time DATETIME,
                    initial_dose REAL DEFAULT 0.0,
                    current_dose REAL DEFAULT 0.0,
                    final_dose REAL DEFAULT 0.0,
                    total_dose REAL DEFAULT 0.0,
                    duration_minutes REAL DEFAULT 0.0,
                    average_dose_rate REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
                )''')

        c.execute('''CREATE TABLE IF NOT EXISTS radiation_readings_local (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id TEXT NOT NULL,
                    session_id INTEGER,
                    cpm REAL,
                    absorbed_dose_rate REAL,
                    cumulative_dose REAL,
                    tube_type TEXT DEFAULT 'J305',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES radiation_exposure_sessions(id)
                )''')
        
        # البحث عن جلسة نشطة للموظف
        c.execute('''SELECT id, initial_dose FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND end_time IS NULL''', (employee_id,))
        session = c.fetchone()
        
        session_id = None
        if session:
            session_id, initial_dose = session
            # تحديث الجرعة الحالية في الجلسة
            c.execute('''UPDATE radiation_exposure_sessions 
                         SET current_dose = ? WHERE id = ?''', 
                     (cumulative_dose, session_id))
        
        # إدراج القراءة الجديدة
        c.execute('''INSERT INTO radiation_readings_local 
                     (employee_id, session_id, cpm, absorbed_dose_rate, cumulative_dose, tube_type)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                 (employee_id, session_id, cpm, absorbed_dose, cumulative_dose, tube_type))
        
        reading_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'reading': {
                'id': reading_id,
                'employee_id': employee_id,
                'session_id': session_id,
                'cpm': cpm,
                'absorbed_dose': absorbed_dose,
                'cumulative_dose': cumulative_dose,
                'tube_type': tube_type
            },
            'message': 'تم حفظ القراءة بنجاح'
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': f'خطأ في البيانات الرقمية: {str(e)}'}), 400
    except Exception as e:
        logger.exception(f"Error saving radiation reading: {e}")
        return jsonify({'success': False, 'error': f'خطأ في حفظ القراءة: {str(e)}'}), 500

@app.route('/api/daily_dose_summary/<employee_id>', methods=['GET'])
def get_daily_dose_summary(employee_id):
    """جلب ملخص الجرعة اليومية لموظف محدد - موحّد على attendance.db"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # ضمان أعمدة حدود الجرعات موجودة
        for col_def in ["daily_limit", "monthly_limit", "annual_limit"]:
            try:
                c.execute(f"ALTER TABLE employees ADD COLUMN {col_def} REAL")
            except Exception:
                pass
        
        # التحقق من وجود الموظف وجلب حدوده
        c.execute('''SELECT name, daily_limit, monthly_limit, annual_limit 
                     FROM employees WHERE employee_id = ?''', (employee_id,))
        employee = c.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({'success': False, 'error': f'الموظف {employee_id} غير موجود'}), 404
        
        name, daily_limit, monthly_limit, annual_limit = employee
        daily_limit = daily_limit or 54.8
        
        # حساب الجرعة اليومية من الجلسات المكتملة
        today = datetime.now().date()
        c.execute('''SELECT SUM(total_dose) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND DATE(start_time) = ? AND status = 'completed' ''', 
                 (employee_id, today))
        
        completed_daily_dose = c.fetchone()[0] or 0.0
        
        # إضافة الجرعة من الجلسة النشطة (إن وجدت)
        c.execute('''SELECT id, initial_dose, current_dose FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND end_time IS NULL AND DATE(start_time) = ?''', 
                 (employee_id, today))
        active_session = c.fetchone()
        
        active_dose = 0.0
        if active_session:
            session_id, initial_dose, current_dose = active_session
            active_dose = max(0, (current_dose or 0) - (initial_dose or 0))
        
        total_daily_dose = (completed_daily_dose or 0.0) + (active_dose or 0.0)
        
        # حساب النسب المئوية
        daily_percentage = (total_daily_dose / daily_limit * 100) if daily_limit > 0 else 0
        
        # تحديد حالة الأمان
        if daily_percentage >= 100:
            safety_status = "خطر - تجاوز الحد اليومي"
            safety_class = "danger"
        elif daily_percentage >= 80:
            safety_status = "تحذير - اقتراب من الحد اليومي"
            safety_class = "warning"
        elif daily_percentage >= 50:
            safety_status = "مراقبة - نصف الحد اليومي"
            safety_class = "info"
        else:
            safety_status = "آمن"
            safety_class = "success"
        
        # التحقق من وجود تجاوزات
        has_warnings = daily_percentage >= 80
        
        conn.close()
        
        return jsonify({
            'success': True,
            'summary': {
                'employee_id': employee_id,
                'name': name,
                'date': today.isoformat(),
                'daily_dose': round(total_daily_dose, 3),
                'daily_limit': daily_limit,
                'daily_percentage': round(daily_percentage, 1),
                'completed_dose': round(completed_daily_dose, 3),
                'active_dose': round(active_dose, 3),
                'safety_status': safety_status,
                'safety_class': safety_class,
                'has_warnings': has_warnings,
                'warnings': [f'الجرعة اليومية: {total_daily_dose:.3f} μSv ({daily_percentage:.1f}%)'] if has_warnings else []
            }
        })
        
    except Exception as e:
        logger.exception(f"Error in daily dose summary: {e}")
        return jsonify({'success': False, 'error': f'خطأ في جلب ملخص الجرعة: {str(e)}'}), 500

@app.route('/api/cumulative_dose_summary/<employee_id>', methods=['GET'])
def get_cumulative_dose_summary(employee_id):
    """جلب ملخص الجرعة التراكمية لموظف محدد - موحّد على attendance.db"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # ضمان أعمدة حدود الجرعات موجودة
        for col_def in ["daily_limit", "monthly_limit", "annual_limit"]:
            try:
                c.execute(f"ALTER TABLE employees ADD COLUMN {col_def} REAL")
            except Exception:
                pass
        
        # التحقق من وجود الموظف
        c.execute('''SELECT name, daily_limit, monthly_limit, annual_limit 
                     FROM employees WHERE employee_id = ?''', (employee_id,))
        employee = c.fetchone()
        
        if not employee:
            conn.close()
            return jsonify({'success': False, 'error': f'الموظف {employee_id} غير موجود'}), 404
        
        name, daily_limit, monthly_limit, annual_limit = employee
        daily_limit = daily_limit or 54.8
        monthly_limit = monthly_limit or 1643.8
        annual_limit = annual_limit or 20000.0
        
        # حساب الجرعات التراكمية لفترات مختلفة
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        year_ago = today - timedelta(days=365)
        
        # الجرعة اليومية
        c.execute('''SELECT COALESCE(SUM(total_dose), 0) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND DATE(start_time) = ? AND status = 'completed' ''', 
                 (employee_id, today))
        daily_dose = c.fetchone()[0]
        
        # الجرعة الأسبوعية
        c.execute('''SELECT COALESCE(SUM(total_dose), 0) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND DATE(start_time) >= ? AND status = 'completed' ''', 
                 (employee_id, week_ago))
        weekly_dose = c.fetchone()[0]
        
        # الجرعة الشهرية
        c.execute('''SELECT COALESCE(SUM(total_dose), 0) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND DATE(start_time) >= ? AND status = 'completed' ''', 
                 (employee_id, month_ago))
        monthly_dose = c.fetchone()[0]
        
        # الجرعة السنوية
        c.execute('''SELECT COALESCE(SUM(total_dose), 0) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND DATE(start_time) >= ? AND status = 'completed' ''', 
                 (employee_id, year_ago))
        annual_dose = c.fetchone()[0]
        
        # إجمالي الجلسات
        c.execute('''SELECT COUNT(*) FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND status = 'completed' ''', (employee_id,))
        total_sessions = c.fetchone()[0]
        
        # آخر جلسة
        c.execute('''SELECT start_time, total_dose FROM radiation_exposure_sessions 
                     WHERE employee_id = ? AND status = 'completed' 
                     ORDER BY start_time DESC LIMIT 1''', (employee_id,))
        last_session = c.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'summary': {
                'employee_id': employee_id,
                'name': name,
                'daily_dose': round(daily_dose, 3),
                'weekly_dose': round(weekly_dose, 3),
                'monthly_dose': round(monthly_dose, 3),
                'annual_dose': round(annual_dose, 3),
                'daily_percentage': round((daily_dose / daily_limit * 100) if daily_limit > 0 else 0, 1),
                'monthly_percentage': round((monthly_dose / monthly_limit * 100) if monthly_limit > 0 else 0, 1),
                'annual_percentage': round((annual_dose / annual_limit * 100) if annual_limit > 0 else 0, 1),
                'total_sessions': total_sessions,
                'last_session_date': last_session[0] if last_session else None,
                'last_session_dose': round(last_session[1], 3) if last_session else 0,
                'limits': {
                    'daily': daily_limit,
                    'monthly': monthly_limit,
                    'annual': annual_limit
                }
            }
        })
        
    except Exception as e:
        logger.exception(f"Error in cumulative dose summary: {e}")
        return jsonify({'success': False, 'error': f'خطأ في جلب الملخص التراكمي: {str(e)}'}), 500

@app.route('/api/add_employee', methods=['POST'])
def api_add_employee():
    """إضافة موظف جديد"""
    try:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'لم يتم توفير صورة'}), 400


        employee_id = request.form.get('employee_id')
        name = request.form.get('name')
        job_title = request.form.get('job_title')
        gender = request.form.get('gender')
        pregnant = request.form.get('pregnant')

        image_file = request.files['image']

        # التحقق من الحقول المطلوبة
        if not employee_id or not name or not job_title or not gender:
            return jsonify({'success': False, 'error': 'يرجى ملء جميع الحقول'}), 400

        # إذا كان الجنس أنثى يجب تعبئة حقل الحمل
        if gender == 'أنثى' and not pregnant:
            return jsonify({'success': False, 'error': 'يرجى تحديد حالة الحمل'}), 400

        # إنشاء مجلد للموظف في dataset
        employee_dir = os.path.join('dataset', employee_id)
        if not os.path.exists(employee_dir):
            os.makedirs(employee_dir)

        # حفظ الصورة
        image_path = os.path.join(employee_dir, f'{employee_id}_1.jpg')
        image_file.save(image_path)

        # إضافة إلى قاعدة البيانات
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # التحقق من عدم وجود الموظف مسبقاً
        c.execute('SELECT employee_id FROM employees WHERE employee_id = ?', (employee_id,))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'رقم الموظف موجود مسبقاً'}), 400

        # إضافة الأعمدة الجديدة إذا لم تكن موجودة (مرة واحدة فقط)
        try:
            c.execute("ALTER TABLE employees ADD COLUMN job_title TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE employees ADD COLUMN gender TEXT")
        except Exception:
            pass
        try:
            c.execute("ALTER TABLE employees ADD COLUMN pregnant TEXT")
        except Exception:
            pass

        # إدراج الموظف الجديد
        c.execute('''INSERT INTO employees (employee_id, name, image_path, job_title, gender, pregnant)
                    VALUES (?, ?, ?, ?, ?, ?)''', (employee_id, name, image_path, job_title, gender, pregnant))
        conn.commit()
        conn.close()

        # إعادة تحميل الوجوه المعروفة
        global known_face_encodings, known_face_names
        known_face_encodings, known_face_names = load_known_faces()

        return jsonify({
            'success': True,
            'message': f'تم إضافة الموظف {name} بنجاح',
            'employee_id': employee_id
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في إضافة الموظف: {str(e)}'
        }), 500

@app.route('/api/reload_faces', methods=['POST'])
def reload_faces():
    """إعادة تحميل الوجوه المعروفة"""
    global known_face_encodings, known_face_names
    try:
        known_face_encodings, known_face_names = load_known_faces()
        return jsonify({
            'success': True,
            'message': f'تم تحميل {len(known_face_encodings)} وجه معروف',
            'faces_count': len(known_face_encodings)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في إعادة تحميل الوجوه: {str(e)}'
        }), 500

@app.route('/api/employees', methods=['GET'])
def get_employees():
    """جلب قائمة الموظفين"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute('''SELECT employee_id, name, job_title, gender, pregnant, created_at
                     FROM employees
                     ORDER BY name''')
        employees = []
        for row in c.fetchall():
            employees.append({
                'employee_id': row[0],
                'name': row[1],
                'job_title': row[2] if row[2] else 'غير محدد',
                'gender': row[3] if row[3] else 'غير محدد',
                'pregnant': row[4] if row[4] else 'غير محدد',
                'created_at': row[5]
            })
        conn.close()

        return jsonify({
            'success': True,
            'employees': employees,
            'count': len(employees)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في جلب الموظفين: {str(e)}'
        }), 500

@app.route('/api/employee_attendance_report/<employee_id>', methods=['GET'])
def get_employee_attendance_report(employee_id):
    """تقرير حضور موظف محدد"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # جلب بيانات الموظف
        c.execute('SELECT name, job_title FROM employees WHERE employee_id = ?', (employee_id,))
        employee = c.fetchone()

        if not employee:
            return jsonify({
                'success': False,
                'error': 'الموظف غير موجود'
            }), 404

        # جلب سجلات الحضور
        c.execute('''SELECT check_type, timestamp, image_path
                     FROM attendance
                     WHERE employee_id = ?
                     ORDER BY timestamp DESC
                     LIMIT 100''', (employee_id,))

        attendance_records = []
        for row in c.fetchall():
            attendance_records.append({
                'check_type': row[0],
                'timestamp': row[1],
                'image_path': row[2]
            })

        conn.close()

        return jsonify({
            'success': True,
            'employee': {
                'employee_id': employee_id,
                'name': employee[0],
                'job_title': employee[1]
            },
            'attendance_records': attendance_records,
            'total_records': len(attendance_records)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في جلب تقرير الحضور: {str(e)}'
        }), 500

def get_employee_attendance_status(employee_id):
    """التحقق من حالة حضور الموظف (موجود أم لا) لمنع التسجيل المكرر"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # البحث عن آخر حركة للموظف اليوم
        c.execute('''SELECT check_type, timestamp 
                     FROM attendance 
                     WHERE employee_id = ? 
                     AND DATE(timestamp) = DATE('now') 
                     ORDER BY timestamp DESC 
                     LIMIT 1''', (employee_id,))
        
        last_record = c.fetchone()
        conn.close()
        
        if last_record:
            last_check_type = last_record[0]
            last_timestamp = last_record[1]
            if last_check_type == 'check_in':
                return {
                    "status": "present", 
                    "message": "الموظف مسجل حضور بالفعل",
                    "last_action": "check_in",
                    "last_timestamp": last_timestamp
                }
            else:  # check_out
                return {
                    "status": "absent", 
                    "message": "الموظف مسجل انصراف",
                    "last_action": "check_out",
                    "last_timestamp": last_timestamp
                }
        else:
            return {
                "status": "absent", 
                "message": "لا يوجد حضور اليوم",
                "last_action": None,
                "last_timestamp": None
            }
            
    except Exception as e:
        print(f"❌ خطأ في فحص حالة الحضور: {e}")
        return {
            "status": "error", 
            "message": f"خطأ في فحص الحالة: {e}",
            "last_action": None,
            "last_timestamp": None
        }

@app.route('/api/check_attendance_status/<employee_id>', methods=['GET'])
def check_attendance_status(employee_id):
    """فحص حالة حضور موظف محدد"""
    try:
        status = get_employee_attendance_status(employee_id)
        employee_name = get_employee_name_by_id(employee_id)
        
        return jsonify({
            'success': True,
            'employee_id': employee_id,
            'employee_name': employee_name,
            'attendance_status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'خطأ في فحص حالة الحضور: {str(e)}'
        }), 500

@app.route('/api/register_attendance', methods=['POST'])
def register_attendance():
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    
    image_file = request.files['image']
    check_type = request.form.get('check_type')
    
    # حفظ الصورة مؤقتاً
    temp_path = f"static/temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    image_file.save(temp_path)
    
    # التعرف على الوجه
    image = face_recognition.load_image_file(temp_path)
    face_locations = face_recognition.face_locations(image)
    
    if not face_locations:
        os.remove(temp_path)
        return jsonify({'error': 'No face detected'}), 400
    
    face_encoding = face_recognition.face_encodings(image)[0]

    # البحث عن مطابقة في الوجوه المحملة من dataset
    if not known_face_encodings:
        os.remove(temp_path)
        return jsonify({'error': 'No registered faces found'}), 404

    # مقارنة الوجه مع الوجوه المعروفة
    matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.6)

    if True in matches:
        # العثور على أول مطابقة
        first_match_index = matches.index(True)
        employee_id = known_face_names[first_match_index]

        # الحصول على اسم الموظف من قاعدة البيانات
        employee_name = get_employee_name_by_id(employee_id)
        
        # ✅ التحقق من حالة الحضور لمنع التسجيل المكرر
        attendance_status = get_employee_attendance_status(employee_id)
        
        print(f"🔍 فحص حالة الحضور للموظف {employee_id} ({employee_name}):")
        print(f"   الحالة: {attendance_status['status']}")
        print(f"   الرسالة: {attendance_status['message']}")
        print(f"   آخر عملية: {attendance_status.get('last_action', 'لا توجد')}")
        
        # التحقق من منع تسجيل الحضور المكرر
        if check_type == 'check_in' and attendance_status["status"] == "present":
            os.remove(temp_path)
            print(f"🚫 رفض تسجيل حضور مكرر للموظف {employee_name}")
            return jsonify({
                'success': False,
                'error': 'duplicate_check_in',
                'error_code': 'DUPLICATE_CHECK_IN',
                'message': f'الموظف {employee_name} مسجل حضور بالفعل اليوم.',
                'detailed_message': 'لا يمكن إعادة تسجيل الحضور. الموظف موجود في المكان بالفعل.',
                'employee_name': employee_name,
                'employee_id': employee_id,
                'last_check_time': attendance_status.get('last_timestamp'),
                'suggestion': 'يمكنك تسجيل الانصراف إذا كنت تريد المغادرة.'
            }), 409  # 409 Conflict
            
        # التحقق من منع تسجيل الانصراف بدون حضور
        elif check_type == 'check_out' and attendance_status["status"] == "absent":
            os.remove(temp_path)
            print(f"🚫 رفض تسجيل انصراف بدون حضور للموظف {employee_name}")
            return jsonify({
                'success': False,
                'error': 'check_out_without_check_in',
                'error_code': 'NO_CHECK_IN_TODAY',
                'message': f'الموظف {employee_name} غير مسجل حضور اليوم.',
                'detailed_message': 'يجب تسجيل الحضور أولاً قبل تسجيل الانصراف.',
                'employee_name': employee_name,
                'employee_id': employee_id,
                'last_check_time': attendance_status.get('last_timestamp'),
                'suggestion': 'يرجى تسجيل الحضور أولاً ثم تسجيل الانصراف.'
            }), 409  # 409 Conflict
        
        # إذا مر التحقق بنجاح، طباعة رسالة التأكيد
        action_text = 'الحضور' if check_type == 'check_in' else 'الانصراف'
        print(f"✅ السماح بتسجيل {action_text} للموظف {employee_name}")

        # تسجيل الحضور في قاعدة البيانات بوقت دقيق
        timestamp = get_current_time_precise()

        # حذف الصورة المؤقتة بدلاً من حفظها
        os.remove(temp_path)

        # حفظ في قاعدة البيانات
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # إدراج سجل الحضور باستخدام الوقت الدقيق
        date_str = timestamp.strftime('%Y-%m-%d')
        time_str = timestamp.strftime('%H:%M:%S.%f')[:-3]  # مع الميلي ثانية

        # حفظ في جدول الحضور بدون مسار الصورة
        c.execute('''INSERT INTO attendance (employee_id, name, check_type, timestamp, date, time)
                    VALUES (?, ?, ?, ?, ?, ?)''',
                 (employee_id, employee_name, check_type, timestamp, date_str, time_str))

        conn.commit()
        conn.close()

        # الربط التلقائي مع نظام مراقبة التعرض
        exposure_result = None
        if check_type == 'check_in':
            # بدء أو استئناف مراقبة التعرض تلقائياً عند تسجيل الحضور
            print(f"🔄 محاولة بدء/استئناف مراقبة التعرض للموظف {employee_id}")
            exposure_result = start_exposure_session(employee_id)

            if exposure_result and exposure_result.get('success'):
                if exposure_result.get('resumed'):
                    print(f"🔄 تم استئناف جلسة التعرض الموجودة - Session ID: {exposure_result.get('session_id')}")
                else:
                    print(f"✅ تم بدء جلسة تعرض جديدة - Session ID: {exposure_result.get('session_id')}")
            else:
                print(f"❌ فشل في بدء/استئناف مراقبة التعرض: {exposure_result}")

        elif check_type == 'check_out':
            # إنهاء مراقبة التعرض تلقائياً عند تسجيل الانصراف
            print(f"🔄 محاولة إنهاء مراقبة التعرض للموظف {employee_id}")
            exposure_result = end_exposure_session(employee_id)
            print(f"📊 نتيجة إنهاء مراقبة التعرض: {exposure_result}")

        # إعداد الاستجابة مع معلومات التعرض
        response_data = {
            'success': True,
            'employee_id': employee_id,
            'employee_name': employee_name,
            'check_type': check_type,
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }

        # إضافة معلومات التعرض إلى الاستجابة
        if exposure_result:
            # تحديد الرسالة المناسبة حسب نوع العملية
            if check_type == 'check_in':
                if exposure_result.get('resumed'):
                    exposure_message = 'تم استئناف جلسة مراقبة التعرض الموجودة'
                else:
                    exposure_message = 'تم بدء جلسة مراقبة تعرض جديدة'
            else:
                exposure_message = 'تم إنهاء مراقبة التعرض'

            response_data['exposure'] = {
                'success': exposure_result.get('success', False),
                'message': exposure_message,
                'data': exposure_result
            }

            # إضافة بيانات إضافية للعرض في الرسالة
            if check_type == 'check_out' and exposure_result.get('success'):
                response_data['exposure']['display_data'] = {
                    'duration_formatted': exposure_result.get('duration_formatted', '0 دقيقة'),
                    'total_exposure_display': f"{exposure_result.get('total_exposure', 0):.3f} μSv",
                    'average_dose_rate_display': f"{exposure_result.get('average_dose_rate', 0):.3f} μSv/h",
                    'safety_status': exposure_result.get('safety_status', 'غير محدد'),
                    'safety_percentage': f"{exposure_result.get('safety_percentage', 0):.1f}%"
                }

            if exposure_result.get('success'):
                if check_type == 'check_in':
                    if exposure_result.get('resumed'):
                        print(f"🔄 تم استئناف مراقبة التعرض بنجاح للموظف {employee_id}")
                    else:
                        print(f"✅ تم بدء مراقبة التعرض بنجاح للموظف {employee_id}")
                else:
                    print(f"🛑 تم إنهاء مراقبة التعرض بنجاح للموظف {employee_id}")
            else:
                action_text = 'بدء/استئناف' if check_type == 'check_in' else 'إنهاء'
                print(f"⚠️ تحذير: فشل في {action_text} مراقبة التعرض: {exposure_result.get('error', 'خطأ غير معروف')}")
        else:
            print("⚠️ لم يتم تنفيذ عملية مراقبة التعرض")

        return jsonify(response_data)

    os.remove(temp_path)
    return jsonify({'error': 'Face not recognized'}), 404



@app.route('/api/exposure_statistics', methods=['GET'])
def get_exposure_statistics():
    """الحصول على إحصائيات التعرض"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # إجمالي الموظفين
        c.execute('SELECT COUNT(*) FROM employees')
        total_employees = c.fetchone()[0]

        # إجمالي فترات التعرض
        c.execute('SELECT COUNT(*) FROM employee_exposure_sessions')
        total_sessions = c.fetchone()[0]

        # متوسط التعرض
        c.execute('SELECT AVG(total_exposure) FROM employee_exposure_sessions WHERE total_exposure IS NOT NULL')
        avg_exposure_result = c.fetchone()
        average_exposure = avg_exposure_result[0] if avg_exposure_result[0] else 0

        # إجمالي تنبيهات الأمان
        c.execute('SELECT SUM(safety_alerts) FROM employee_exposure_sessions')
        safety_alerts_result = c.fetchone()
        safety_alerts = safety_alerts_result[0] if safety_alerts_result[0] else 0

        conn.close()

        return jsonify({
            "success": True,
            "statistics": {
                "total_employees": total_employees,
                "total_sessions": total_sessions,
                "average_exposure": average_exposure,
                "safety_alerts": safety_alerts
            }
        })

    except Exception as e:
        print(f"❌ خطأ في الحصول على الإحصائيات: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

if __name__ == '__main__':
    # الحصول على عنوان IP المحلي
    local_ip = get_local_ip()
    port = 5000

    print("\n" + "="*60)
    print("🚀 بدء تشغيل نظام RadMeter")
    print("="*60)
    print(f"📍 عنوان IP المحلي: {local_ip}")
    print(f"🌐 منفذ الخادم: {port}")
    print()
    print("🔗 روابط الوصول:")
    print(f"   الموقع الرئيسي: http://{local_ip}:{port}")
    print(f"   localhost:        http://127.0.0.1:{port}")
    print(f"   شبكة محلية:     http://{local_ip}:{port}")
    print()
    print("📡 رابط استقبال بيانات ESP32:")
    print(f"   POST: http://{local_ip}:{port}/data")
    print()
    print("📊 روابط API:")
    print(f"   بيانات الإشعاع: http://{local_ip}:{port}/api/radiation_data")
    print(f"   حالة النظام:    http://{local_ip}:{port}/api/system_status")
    print(f"   إحصائيات Cache: http://{local_ip}:{port}/api/cache_stats")
    print()
    print("💾 حالة قاعدة البيانات:")
    print("   نوع: SQLite محلي")
    print("   حالة: متصل")
    print()
    print("✅ النظام جاهز لاستقبال بيانات ESP32!")
    print("="*60 + "\n")

    # تحديث التخزين المؤقت من البيانات المحلية عند بدء التشغيل
    update_cache_from_local_db()

def classify_radiation_safety(dose_rate_per_hour, total_dose, session_duration_minutes, employee_id=None):
    """
    تصنيف مستوى الأمان الإشعاعي بناءً على المعايير الدولية

    المعايير المستخدمة:
    - ICRP (اللجنة الدولية للحماية الإشعاعية)
    - معايير الوكالة الدولية للطاقة الذرية (IAEA)
    - حدود خاصة للنساء الحوامل (ICRP Publication 103)

    Args:
        dose_rate_per_hour: معدل التعرض بالساعة (μSv/h)
        total_dose: إجمالي التعرض للجلسة (μSv)
        session_duration_minutes: مدة الجلسة بالدقائق
        employee_id: رقم الموظف (للتحقق من حالة الحمل)

    Returns:
        tuple: (safety_status, safety_percentage, risk_level, is_pregnant)
    """

    # التحقق من حالة الحمل للموظف
    is_pregnant = False
    if employee_id:
        try:
            conn = sqlite3.connect('attendance.db')
            c = conn.cursor()
            c.execute('SELECT pregnant FROM employees WHERE employee_id = ?', (employee_id,))
            result = c.fetchone()
            if result and result[0] == 'نعم':
                is_pregnant = True
            conn.close()
        except Exception:
            pass  # في حالة عدم وجود الموظف أو خطأ في قاعدة البيانات

    # المعايير الدولية للعاملين في المجال الإشعاعي (μSv/h)
    # بناءً على معايير ICRP و UNSCEAR و IAEA
    # تم تعديل الحدود حسب متطلبات المشروع
    NATURAL_BACKGROUND = 0.3      # الخلفية الطبيعية القصوى - آمن (UNSCEAR: 0.06-0.3 μSv/h)
    WARNING_LEVEL = 2.38          # مستوى تحذير - يتطلب مراقبة
    DANGER_LEVEL = 2.38           # مستوى خطر - أي قيمة >= 2.38 تعتبر خطيرة

    # الحدود القديمة (للمرجع فقط - غير مستخدمة)
    # WORKER_SAFE_LEVEL = 2.0       # مستوى آمن للعاملين (أقل من الحد القانوني)
    # WORKER_LIMIT_HOURLY = 6.8     # الحد القانوني للعاملين (54.8 μSv/يوم ÷ 8 ساعات)
    # ELEVATED_LEVEL = 15.0         # مستوى مرتفع يتطلب مراقبة مشددة
    # EMERGENCY_LEVEL = 100.0       # مستوى طوارئ - خطر شديد

    # المعايير اليومية للعاملين (μSv/يوم)
    # بناءً على ICRP: 20 mSv/سنة للعاملين
    WORKER_DAILY_LIMIT = 54.8     # الحد اليومي للعاملين (20 mSv/سنة ÷ 365 يوم)
    WORKER_WEEKLY_LIMIT = 383.6   # الحد الأسبوعي للعاملين (54.8 × 7)
    WORKER_ANNUAL_LIMIT = 20000.0 # الحد السنوي للعاملين (20 mSv)

    # المعايير الخاصة بالنساء الحوامل (ICRP Publication 103)
    # الحد الأقصى للجنين: 1 mSv خلال فترة الحمل المتبقية
    PREGNANT_TOTAL_LIMIT = 1000.0    # 1 mSv = 1000 μSv للجنين خلال الحمل
    PREGNANT_DAILY_LIMIT = 3.7       # تقريباً 1000 μSv ÷ 270 يوم (9 أشهر)
    PREGNANT_WARNING_LEVEL = 2.38    # نفس حد التحذير للعاملين العاديين

    # تحديد مستوى الخطر بناءً على حالة الحمل
    if is_pregnant:
        # معايير خاصة للنساء الحوامل - نفس النظام المبسط
        # الحدود: <= 0.3 آمن | < 2.38 تحذير | >= 2.38 خطر

        if dose_rate_per_hour <= NATURAL_BACKGROUND:
            safety_status = "آمن - حامل"
            risk_level = "منخفض جداً"
            safety_percentage = 100.0

        elif dose_rate_per_hour < PREGNANT_WARNING_LEVEL:
            safety_status = "تحذير - حامل"
            risk_level = "متوسط"
            safety_percentage = round(100 - ((dose_rate_per_hour - NATURAL_BACKGROUND) / (PREGNANT_WARNING_LEVEL - NATURAL_BACKGROUND) * 50), 1)

        else:
            # >= 2.38 μSv/h - خطر على الحامل
            safety_status = "خطر - حامل"
            risk_level = "عالي"
            safety_percentage = max(0, round(50 - ((dose_rate_per_hour - PREGNANT_WARNING_LEVEL) / PREGNANT_WARNING_LEVEL * 50), 1))

    else:
        # معايير العاملين العاديين - النظام الجديد المبسط
        # الحدود: <= 0.3 آمن | < 2.38 تحذير | >= 2.38 خطر

        if dose_rate_per_hour <= NATURAL_BACKGROUND:
            # <= 0.3 μSv/h - آمن تماماً
            safety_status = "آمن"
            risk_level = "منخفض جداً"
            safety_percentage = 100.0

        elif dose_rate_per_hour < WARNING_LEVEL:
            # > 0.3 و < 2.38 μSv/h - تحذير
            safety_status = "تحذير"
            risk_level = "متوسط"
            # حساب النسبة: كلما اقتربنا من 2.38 تقل النسبة
            safety_percentage = round(100 - ((dose_rate_per_hour - NATURAL_BACKGROUND) / (WARNING_LEVEL - NATURAL_BACKGROUND) * 50), 1)

        else:
            # >= 2.38 μSv/h - خطر
            safety_status = "خطر"
            risk_level = "عالي"
            # النسبة تقل كلما زادت القيمة فوق 2.38
            safety_percentage = max(0, round(50 - ((dose_rate_per_hour - DANGER_LEVEL) / DANGER_LEVEL * 50), 1))

    # فحص إضافي للجرعة الإجمالية
    if is_pregnant:
        # فحص الحدود الخاصة بالحوامل
        if total_dose > PREGNANT_DAILY_LIMIT:
            safety_status = "خطر - تجاوز الحد اليومي للحامل"
            risk_level = "حرج"
            safety_percentage = 0.0
        elif total_dose > (PREGNANT_DAILY_LIMIT * 0.8):  # 80% من الحد اليومي للحامل
            if "طبيعي" in safety_status or "آمن" in safety_status:
                safety_status = "تحذير - اقتراب من الحد اليومي للحامل"
                risk_level = "عالي"
                safety_percentage = min(safety_percentage, 20.0)
        elif total_dose > (PREGNANT_DAILY_LIMIT * 0.5):  # 50% من الحد اليومي للحامل
            if "طبيعي" in safety_status or "آمن" in safety_status:
                safety_status = "مراقبة - نصف الحد اليومي للحامل"
                risk_level = "متوسط"
                safety_percentage = min(safety_percentage, 50.0)
    else:
        # فحص الحدود العادية للعاملين
        if total_dose > WORKER_DAILY_LIMIT:
            safety_status = "خطر - تجاوز الحد اليومي للعاملين"
            risk_level = "حرج"
            safety_percentage = 0.0
        elif total_dose > (WORKER_DAILY_LIMIT * 0.9):  # 90% من الحد اليومي
            if safety_status in ["طبيعي", "آمن", "ضمن الحد المسموح"]:
                safety_status = "تحذير - اقتراب من الحد اليومي"
                risk_level = "عالي"
                safety_percentage = min(safety_percentage, 15.0)
        elif total_dose > (WORKER_DAILY_LIMIT * 0.75):  # 75% من الحد اليومي
            if safety_status in ["طبيعي", "آمن"]:
                safety_status = "مراقبة - ثلاثة أرباع الحد اليومي"
                risk_level = "متوسط"
                safety_percentage = min(safety_percentage, 35.0)
        elif total_dose > (WORKER_DAILY_LIMIT * 0.5):  # 50% من الحد اليومي
            if safety_status in ["طبيعي", "آمن"]:
                safety_status = "مراقبة - نصف الحد اليومي"
                risk_level = "منخفض-متوسط"
                safety_percentage = min(safety_percentage, 65.0)

    return safety_status, safety_percentage, risk_level, is_pregnant

@app.route('/api/exposure_reports', methods=['GET'])
def get_exposure_reports():
    """API لجلب تقارير التعرض الفعلية من قاعدة البيانات"""
    try:
        employee_id = request.args.get('employee_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')

        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        query = '''
            SELECT ses.employee_id, e.name AS employee_name,
                   ses.check_in_time, ses.check_out_time,
                   ses.exposure_duration_minutes, ses.total_exposure,
                   ses.average_dose_rate, ses.max_dose_rate, ses.min_dose_rate,
                   ses.initial_total_dose, ses.final_total_dose, ses.safety_alerts, ses.notes
            FROM employee_exposure_sessions ses
            LEFT JOIN employees e ON ses.employee_id = e.employee_id
            WHERE 1=1
        '''
        params = []

        if employee_id:
            query += ' AND ses.employee_id = ?'
            params.append(employee_id)

        if date_from:
            query += ' AND DATE(ses.check_in_time) >= ?'
            params.append(date_from)

        if date_to:
            query += ' AND DATE(ses.check_in_time) <= ?'
            params.append(date_to)

        query += ' ORDER BY ses.check_in_time DESC'

        c.execute(query, params)
        reports = []
        for row in c.fetchall():
            reports.append({
                'employee_id': row[0],
                'employee_name': row[1],
                'check_in_time': row[2],
                'check_out_time': row[3],
                'exposure_duration_minutes': row[4],
                'total_exposure': row[5],
                'average_dose_rate': row[6],
                'max_dose_rate': row[7],
                'min_dose_rate': row[8],
                'initial_total_dose': row[9],
                'final_total_dose': row[10],
                'safety_alerts': row[11],
                'notes': row[12]
            })
        conn.close()

        return jsonify({
            'success': True,
            'reports': reports,
            'count': len(reports),
            'filters': {
                'employee_id': employee_id,
                'date_from': date_from,
                'date_to': date_to
            }
        })

    except Exception as e:
        print(f"❌ خطأ في جلب تقارير التعرض: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/raw_radiation_data', methods=['GET'])
def get_raw_radiation_data():
    """API مؤقت لجلب جميع قراءات الإشعاع الخام من قاعدة البيانات المحلية"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute('''SELECT id, cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp
                     FROM radiation_readings_local
                     ORDER BY timestamp DESC
                     LIMIT 100''') # جلب آخر 100 قراءة
        
        readings = []
        for row in c.fetchall():
            readings.append({
                'id': row[0],
                'cpm': row[1],
                'source_power': row[2],
                'absorbed_dose_rate': row[3],
                'total_absorbed_dose': row[4],
                'timestamp': row[5]
            })
        conn.close()

        return jsonify({
            'success': True,
            'readings': readings,
            'count': len(readings)
        })
    except Exception as e:
        print(f"❌ خطأ في جلب بيانات الإشعاع الخام: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/force_start_session/<employee_id>', methods=['POST'])
def force_start_session(employee_id):
    """إنشاء جلسة تعرض نشطة يدوياً لأغراض التشخيص"""
    try:
        result = start_exposure_session(employee_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/force_end_session/<employee_id>', methods=['POST'])
def force_end_session(employee_id):
    """إنهاء جلسة التعرض يدوياً لأغراض التشخيص"""
    try:
        result = end_exposure_session(employee_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/current_radiation', methods=['GET'])
def get_current_radiation():
    """الحصول على البيانات الحالية من التخزين المؤقت"""
    try:
        if radiation_cache and hasattr(radiation_cache, 'get_latest_reading'):
            latest_reading = radiation_cache.get_latest_reading()
            if latest_reading:
                return jsonify({
                    "success": True,
                    "data": {
                        "cpm": latest_reading.cpm,
                        "source_power": latest_reading.source_power,
                        "absorbed_dose_rate": latest_reading.absorbed_dose_rate,
                        "total_absorbed_dose": latest_reading.total_absorbed_dose,
                        "timestamp": latest_reading.timestamp.isoformat(),
                        "sensor_id": latest_reading.sensor_id
                    }
                })

        return jsonify({"success": False, "error": "No data available in cache"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/debug_status', methods=['GET'])
def debug_status():
    """API للتحقق من حالة النظام لأغراض التشخيص"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # جلسات التعرض النشطة
        c.execute("SELECT employee_id, check_in_time FROM employee_exposure_sessions WHERE check_out_time IS NULL")
        active_sessions = [{"employee_id": row[0], "check_in_time": row[1]} for row in c.fetchall()]

        # آخر قراءات الإشعاع
        c.execute("SELECT cpm, source_power, absorbed_dose_rate, total_absorbed_dose, timestamp FROM radiation_readings_local ORDER BY timestamp DESC LIMIT 3")
        recent_readings = [{"cpm": row[0], "source_power": row[1], "absorbed_dose_rate": row[2], "total_absorbed_dose": row[3], "timestamp": row[4]} for row in c.fetchall()]

        # آخر جرعة إجمالية
        c.execute("SELECT total_absorbed_dose FROM radiation_readings_local ORDER BY timestamp DESC LIMIT 1")
        last_dose_row = c.fetchone()
        last_total_dose = last_dose_row[0] if last_dose_row else 0.0

        conn.close()

        return jsonify({
            "success": True,
            "active_sessions": active_sessions,
            "recent_readings": recent_readings,
            "last_total_dose": last_total_dose,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/unified_reports', methods=['GET'])
def get_unified_reports():
    """API موحد لجلب بيانات الحضور والتعرض معاً"""
    try:
        employee_id = request.args.get('employee_id', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')

        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # بناء الاستعلام للحضور
        attendance_query = '''
            SELECT a.employee_id, a.name, a.check_type, a.timestamp, a.date, a.time,
                   e.job_title
            FROM attendance a
            LEFT JOIN employees e ON a.employee_id = e.employee_id
            WHERE a.employee_id IS NOT NULL
        '''
        attendance_params = []

        if employee_id:
            attendance_query += ' AND a.employee_id = ?'
            attendance_params.append(employee_id)

        if date_from:
            attendance_query += ' AND a.date >= ?'
            attendance_params.append(date_from)

        if date_to:
            attendance_query += ' AND a.date <= ?'
            attendance_params.append(date_to)

        attendance_query += ' ORDER BY a.timestamp DESC'

        # تنفيذ استعلام الحضور
        c.execute(attendance_query, attendance_params)
        attendance_records = []
        for row in c.fetchall():
            attendance_records.append({
                'employee_id': row[0],
                'name': row[1],
                'check_type': row[2],
                'timestamp': row[3],
                'date': row[4],
                'time': row[5],
                'job_title': row[6] if row[6] else ''
            })

        # جلب بيانات التعرض الفعلية بدلاً من المحاكاة
        exposure_records = []
        exposure_query = '''
            SELECT ses.employee_id, e.name AS employee_name,
                   ses.check_in_time, ses.check_out_time,
                   ses.exposure_duration_minutes, ses.total_exposure,
                   ses.average_dose_rate, ses.max_dose_rate, ses.min_dose_rate,
                   ses.initial_total_dose, ses.final_total_dose, ses.safety_alerts, ses.notes
            FROM employee_exposure_sessions ses
            LEFT JOIN employees e ON ses.employee_id = e.employee_id
            WHERE 1=1
        '''
        exposure_params = []

        if employee_id:
            exposure_query += ' AND ses.employee_id = ?'
            exposure_params.append(employee_id)

        if date_from:
            exposure_query += ' AND DATE(ses.check_in_time) >= ?'
            exposure_params.append(date_from)

        if date_to:
            exposure_query += ' AND DATE(ses.check_in_time) <= ?'
            exposure_params.append(date_to)

        exposure_query += ' ORDER BY ses.check_in_time DESC'

        c.execute(exposure_query, exposure_params)
        for row in c.fetchall():
            # تصنيف مستوى الأمان
            safety_status, safety_percentage, risk_level, is_pregnant = classify_radiation_safety(
                row[6] if row[6] else 0.0, # average_dose_rate
                row[5] if row[5] else 0.0, # total_exposure
                row[4] if row[4] else 0,   # exposure_duration_minutes
                row[1]                     # employee_id
            )

            exposure_records.append({
                'employee_id': row[0],
                'name': row[1],
                'check_in_time': row[2],
                'check_out_time': row[3],
                'exposure_duration_minutes': row[4] if row[4] is not None else None,
                'total_exposure': round(row[5] if row[5] else 0.0, 5),
                'average_dose_rate': round(row[6] if row[6] else 0.0, 5),
                'max_dose_rate': round(row[7] if row[7] else 0.0, 5),
                'min_dose_rate': round(row[8] if row[8] else 0.0, 5),
                'initial_total_dose': round(row[9] if row[9] else 0.0, 5),
                'final_total_dose': round(row[10] if row[10] else 0.0, 5),
                'safety_alerts': row[11],
                'notes': row[12],
                'safety_status': safety_status,
                'safety_percentage': safety_percentage,
                'risk_level': risk_level,
                'daily_limit_percentage': round(((row[5] if row[5] else 0.0) / 55.0) * 100, 1),
                'annual_projection': round((row[5] if row[5] else 0.0) * 365, 1),
                # توافق مع تسميات الواجهة الحالية (aliases)
                'total_dose': round(row[5] if row[5] else 0.0, 5),
                'avg_dose_rate': round(row[6] if row[6] else 0.0, 5),
                'dose_rate': round(row[6] if row[6] else 0.0, 5),
                'session_duration': row[4] if row[4] is not None else None,
                'date': (row[2] or '')[:10] if row[2] else None,
                'start_time': (row[2] or '')[11:16] if row[2] else None
            })


        # جلب قائمة الموظفين للفلتر
        c.execute('SELECT DISTINCT employee_id, name FROM employees ORDER BY name')
        employees = []
        for row in c.fetchall():
            employees.append({
                'employee_id': row[0],
                'name': row[1]
            })

        conn.close()

        return jsonify({
            'success': True,
            'attendance_records': attendance_records,
            'exposure_records': exposure_records, # Fixed: JavaScript expects exposure_records
            'employees': employees,
            'total_attendance_records': len(attendance_records),
            'total_exposure_records': len(exposure_records),
            'filters': {
                'employee_id': employee_id,
                'date_from': date_from,
                'date_to': date_to
            }
        })

    except Exception as e:
        print(f"❌ خطأ في API التقارير الموحدة: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cumulative_doses', methods=['GET'])
def get_cumulative_doses():
    """API لجلب الجرعات التراكمية لجميع الموظفين"""
    try:
        employee_id = request.args.get('employee_id', '')
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # بناء الاستعلام - محدث لإضافة عدد القراءات والمدة الزمنية
        query = '''
            SELECT 
                e.employee_id,
                e.name,
                e.department,
                e.position,
                -- ✨ تصحيح: استخدام ABS لضمان عدم وجود قيم سالبة + فقط الجلسات مع جرعة موجبة
                COALESCE(SUM(CASE WHEN DATE(ses.session_date) = DATE('now') 
                    AND ses.is_active = 0 AND COALESCE(ses.total_exposure, 0) > 0 
                    THEN COALESCE(ses.total_exposure, 0) ELSE 0 END), 0) as daily_dose,
                COALESCE(SUM(CASE WHEN DATE(ses.session_date) >= DATE('now', '-7 days') 
                    AND ses.is_active = 0 AND COALESCE(ses.total_exposure, 0) > 0 
                    THEN COALESCE(ses.total_exposure, 0) ELSE 0 END), 0) as weekly_dose,
                COALESCE(SUM(CASE WHEN DATE(ses.session_date) >= DATE('now', '-30 days') 
                    AND ses.is_active = 0 AND COALESCE(ses.total_exposure, 0) > 0 
                    THEN COALESCE(ses.total_exposure, 0) ELSE 0 END), 0) as monthly_dose,
                COALESCE(SUM(CASE WHEN DATE(ses.session_date) >= DATE('now', '-365 days') 
                    AND ses.is_active = 0 AND COALESCE(ses.total_exposure, 0) > 0 
                    THEN COALESCE(ses.total_exposure, 0) ELSE 0 END), 0) as annual_dose,
                COALESCE(SUM(CASE WHEN ses.is_active = 0 AND COALESCE(ses.total_exposure, 0) > 0 
                    THEN COALESCE(ses.total_exposure, 0) ELSE 0 END), 0) as total_cumulative_dose,
                COUNT(CASE WHEN ses.is_active = 0 THEN 1 END) as total_sessions,
                MAX(ses.check_out_time) as last_exposure_date,
                (
                    -- ✅ احتساب القراءات من الجلسات المغلقة والنشطة معاً
                    SELECT COUNT(*) 
                    FROM radiation_readings_local r 
                    WHERE r.session_id IN (
                        SELECT id FROM employee_exposure_sessions 
                        WHERE employee_id = e.employee_id AND is_active IN (0, 1)
                    )
                ) as total_readings,
                -- ✨ إضافة حساب المدة الإجمالية بالدقائق من الجلسات المغلقة
                COALESCE(SUM(CASE WHEN ses.is_active = 0 THEN COALESCE(ses.exposure_duration_minutes, 0) ELSE 0 END), 0) as total_duration_minutes
            FROM employees e
            LEFT JOIN employee_exposure_sessions ses ON e.employee_id = ses.employee_id
            WHERE 1=1
        '''
        params = []

        if employee_id:
            query += ' AND e.employee_id = ?'
            params.append(employee_id)

        query += ' GROUP BY e.employee_id, e.name, e.department, e.position ORDER BY annual_dose DESC'

        c.execute(query, params)
        
        cumulative_data = []
        for row in c.fetchall():
            emp_id = row[0]
            daily_dose = float(row[4])
            weekly_dose = float(row[5])
            monthly_dose = float(row[6])
            annual_dose = float(row[7])
            total_dose = float(row[8])
            total_sessions = int(row[9]) if row[9] is not None else 0
            last_exposure_date = row[10]
            total_readings = int(row[11]) if row[11] is not None else 0  # عدد القراءات
            total_duration_minutes = float(row[12]) if row[12] is not None else 0.0  # ✨ المدة الإجمالية

            # ✅ إضافة جرعات الجلسات النشطة حالياً (إن وجدت) إلى المجاميع
            c2 = conn.cursor()
            c2.execute('''SELECT id, initial_total_dose, session_date, check_in_time
                          FROM employee_exposure_sessions
                          WHERE employee_id = ? AND is_active = 1''', (emp_id,))
            active_sessions = c2.fetchall()

            active_exposure_sum = 0.0
            for s in active_sessions:
                sess_id, initial_total_dose, session_date, check_in_time = s
                
                # ✨ الطريقة المصححة: حساب الفرق بين أول وآخر قراءة في الجلسة
                c2.execute('''SELECT total_absorbed_dose 
                              FROM radiation_readings_local 
                              WHERE session_id = ? 
                              ORDER BY timestamp ASC LIMIT 1''', (sess_id,))
                first_reading = c2.fetchone()
                
                c2.execute('''SELECT total_absorbed_dose 
                              FROM radiation_readings_local 
                              WHERE session_id = ? 
                              ORDER BY timestamp DESC LIMIT 1''', (sess_id,))
                last_reading = c2.fetchone()
                
                if first_reading and last_reading and first_reading[0] is not None and last_reading[0] is not None:
                    first_dose = float(first_reading[0])
                    last_dose = float(last_reading[0])
                    exposure_now = max(0.0, last_dose - first_dose)
                    active_exposure_sum += exposure_now

                    # إضافة التعرض الحالي إلى اليومي/الأسبوعي/الشهري/السنوي حسب التاريخ
                    daily_dose += exposure_now if str(session_date) == str(datetime.now().date()) else 0.0
                    weekly_dose += exposure_now  # اليوم ضمن الأسبوع الحالي
                    monthly_dose += exposure_now  # اليوم ضمن الشهر الحالي
                    annual_dose += exposure_now   # اليوم ضمن السنة الحالية
                    total_dose += exposure_now
                    
                    print(f"✨ حساب الجلسة النشطة {sess_id}: {first_dose:.6f} -> {last_dose:.6f} = {exposure_now:.6f} μSv")
                    
                    # ✨ حساب مدة الجلسة النشطة بالدقائق
                    if check_in_time:
                        try:
                            check_in_dt = datetime.fromisoformat(check_in_time.replace('Z', '+00:00'))
                            current_time = datetime.now(timezone.utc)
                            duration_minutes = (current_time - check_in_dt).total_seconds() / 60
                            total_duration_minutes += max(0, duration_minutes)
                        except Exception:
                            pass

            # زيادة عدد الجلسات بالجلسات النشطة أيضاً
            total_sessions += len(active_sessions)

            # حساب النسب المئوية من الحدود
            daily_limit = 54.8  # μSv/day
            weekly_limit = 383.6  # μSv/week
            monthly_limit = 1643.8  # μSv/month (~54.8 * 30)
            annual_limit = 20000.0  # μSv/year
            
            daily_percentage = (daily_dose / daily_limit * 100) if daily_limit > 0 else 0
            weekly_percentage = (weekly_dose / weekly_limit * 100) if weekly_limit > 0 else 0
            monthly_percentage = (monthly_dose / monthly_limit * 100) if monthly_limit > 0 else 0
            annual_percentage = (annual_dose / annual_limit * 100) if annual_limit > 0 else 0
            
            # تحديد مستوى الأمان
            if annual_percentage >= 100:
                safety_status = "خطر - تجاوز الحد السنوي"
                status_class = "danger"
            elif annual_percentage >= 80:
                safety_status = "تحذير - اقتراب من الحد السنوي"
                status_class = "warning"
            elif annual_percentage >= 50:
                safety_status = "مراقبة - نصف الحد السنوي"
                status_class = "info"
            else:
                safety_status = "آمن"
                status_class = "success"
            
            # ✨ حساب معدل الجرعة بالساعة (μSv/h)
            total_duration_hours = total_duration_minutes / 60 if total_duration_minutes > 0 else 0
            dose_rate_per_hour = (total_dose / total_duration_hours) if total_duration_hours > 0 else 0
            
            cumulative_data.append({
                'employee_id': emp_id,
                'name': row[1],
                'department': row[2] or '-',
                'position': row[3] or '-',
                'daily_dose': round(daily_dose, 6),
                'weekly_dose': round(weekly_dose, 6),
                'monthly_dose': round(monthly_dose, 6),
                'annual_dose': round(annual_dose, 6),
                'total_cumulative_dose': round(total_dose, 6),
                'total_sessions': total_sessions,
                'total_readings': total_readings,  # ✨ جديد
                'last_exposure_date': last_exposure_date,
                'daily_percentage': round(daily_percentage, 2),
                'weekly_percentage': round(weekly_percentage, 2),
                'monthly_percentage': round(monthly_percentage, 2),
                'annual_percentage': round(annual_percentage, 2),
                'safety_status': safety_status,
                'status_class': status_class,
                'daily_limit': daily_limit,
                'weekly_limit': weekly_limit,
                'monthly_limit': monthly_limit,
                'annual_limit': annual_limit,
                # ✨ حسابات زمنية جديدة
                'total_duration_minutes': round(total_duration_minutes, 2),
                'total_duration_hours': round(total_duration_hours, 2),
                'dose_rate_per_hour': round(dose_rate_per_hour, 6)
            })

        conn.close()

        return jsonify({
            'success': True,
            'cumulative_data': cumulative_data,
            'total_employees': len(cumulative_data)
        })

    except Exception as e:
        print(f"❌ خطأ في API الجرعات التراكمية: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cumulative_doses_fast', methods=['GET'])
def get_cumulative_doses_fast():
    """API سريع لجلب الجرعات التراكمية من جدول البيانات المجمعة"""
    try:
        employee_id = request.args.get('employee_id', '')
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()

        # بناء الاستعلام من الجدول الجديد
        query = '''
            SELECT 
                ecd.employee_id,
                e.name,
                e.department,
                e.position,
                ecd.daily_exposure,
                ecd.weekly_exposure,
                ecd.monthly_exposure,
                ecd.annual_exposure,
                ecd.total_cumulative_exposure,
                ecd.total_sessions,
                ecd.completed_sessions,
                ecd.active_sessions,
                ecd.total_readings,
                ecd.total_duration_minutes,
                ecd.total_duration_hours,
                ecd.average_dose_rate_per_hour,
                ecd.daily_exposure_percentage,
                ecd.weekly_exposure_percentage,
                ecd.monthly_exposure_percentage,
                ecd.annual_exposure_percentage,
                ecd.safety_status,
                ecd.safety_class,
                ecd.risk_level,
                ecd.last_session_date,
                ecd.last_completed_session_date,
                ecd.average_exposure_per_session,
                ecd.max_single_session_exposure,
                ecd.min_single_session_exposure,
                ecd.first_session_date
            FROM employee_cumulative_data ecd
            JOIN employees e ON ecd.employee_id = e.employee_id
            WHERE 1=1
        '''
        params = []

        if employee_id:
            query += ' AND ecd.employee_id = ?'
            params.append(employee_id)

        query += ' ORDER BY ecd.annual_exposure DESC'

        c.execute(query, params)
        
        cumulative_data = []
        employees = []
        for row in c.fetchall():
            # حدود الأمان
            daily_limit = 54.8
            weekly_limit = 383.6
            monthly_limit = 1643.8
            annual_limit = 20000.0
            
            # تجميع بصيغة داخلية (توافق قديم)
            item = {
                'employee_id': row[0],
                'name': row[1],
                'department': row[2] or '-',
                'position': row[3] or '-',
                'daily_dose': round(row[4], 6),
                'weekly_dose': round(row[5], 6),
                'monthly_dose': round(row[6], 6),
                'annual_dose': round(row[7], 6),
                'total_cumulative_dose': round(row[8], 6),
                'total_sessions': row[9],
                'completed_sessions': row[10],
                'active_sessions': row[11], 
                'total_readings': row[12],
                'total_duration_minutes': round(row[13], 2),
                'total_duration_hours': round(row[14], 2),
                'dose_rate_per_hour': round(row[15], 6),
                'daily_percentage': round(row[16], 2),
                'weekly_percentage': round(row[17], 2),
                'monthly_percentage': round(row[18], 2),
                'annual_percentage': round(row[19], 2),
                'safety_status': row[20],
                'status_class': row[21],
                'risk_level': row[22],
                'last_session_date': row[23],
                'last_completed_session_date': row[24],
                'average_exposure_per_session': round(row[25], 6),
                'max_single_session_exposure': round(row[26], 6),
                'min_single_session_exposure': round(row[27], 6),
                'first_session_date': row[28],
                'daily_limit': daily_limit,
                'weekly_limit': weekly_limit,
                'monthly_limit': monthly_limit,
                'annual_limit': annual_limit
            }
            cumulative_data.append(item)

            # تجميع بصيغة متوافقة مع الواجهة الأمامية (employees)
            employees.append({
                'employee_id': item['employee_id'],
                'name': item['name'],
                'department': item['department'],
                'position': item['position'],
                'daily_exposure': item['daily_dose'],
                'weekly_exposure': item['weekly_dose'],
                'monthly_exposure': item['monthly_dose'],
                'annual_exposure': item['annual_dose'],
                'total_cumulative_exposure': item['total_cumulative_dose'],
                'total_sessions': item['total_sessions'],
                'completed_sessions': item['completed_sessions'],
                'active_sessions': item['active_sessions'],
                'total_readings': item['total_readings'],
                'total_duration_minutes': item['total_duration_minutes'],
                'total_duration_hours': item['total_duration_hours'],
                'average_dose_rate_per_hour': item['dose_rate_per_hour'],
                'dose_rate_per_hour': item['dose_rate_per_hour'],
                'daily_exposure_percentage': item['daily_percentage'],
                'weekly_exposure_percentage': item['weekly_percentage'],
                'monthly_exposure_percentage': item['monthly_percentage'],
                'annual_exposure_percentage': item['annual_percentage'],
                'safety_status': item['safety_status'],
                'safety_class': item['status_class'],
                'risk_level': item['risk_level'],
                'last_session_date': item['last_session_date'],
                'last_completed_session_date': item['last_completed_session_date'],
                'average_exposure_per_session': item['average_exposure_per_session'],
                'max_single_session_exposure': item['max_single_session_exposure'],
                'min_single_session_exposure': item['min_single_session_exposure'],
                'first_session_date': item['first_session_date'],
                'daily_limit': item['daily_limit'],
                'weekly_limit': item['weekly_limit'],
                'monthly_limit': item['monthly_limit'],
                'annual_limit': item['annual_limit']
            })

        conn.close()

        return jsonify({
            'success': True,
            'cumulative_data': cumulative_data,
            'employees': employees,
            'total_employees': len(employees),
            'data_source': 'employee_cumulative_data_table',
            'note': 'البيانات من جدول البيانات التراكمية المجمعة - أسرع في الأداء'
        })

    except Exception as e:
        print(f"❌ خطأ في API الجرعات التراكمية السريع: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/update_cumulative_data', methods=['POST'])
def update_cumulative_data():
    """تحديث جدول البيانات التراكمية لجميع الموظفين أو موظف محدد"""
    try:
        employee_id = request.json.get('employee_id') if request.is_json else None
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # تحديد القائمة المراد تحديثها
        if employee_id:
            employees_to_update = [(employee_id,)]
            print(f"🔄 تحديث بيانات الموظف: {employee_id}")
        else:
            c.execute('SELECT DISTINCT employee_id FROM employee_exposure_sessions')
            employees_to_update = c.fetchall()
            print(f"🔄 تحديث بيانات جميع الموظفين: {len(employees_to_update)} موظف")
        
        updated_count = 0
        
        for emp in employees_to_update:
            emp_id = emp[0]
            
            # حساب البيانات التراكمية
            cumulative_data = calculate_employee_cumulative_data_inline(c, emp_id)
            
            # تحديث أو إدراج البيانات
            c.execute('''
                INSERT OR REPLACE INTO employee_cumulative_data (
                    employee_id, total_sessions, completed_sessions, active_sessions,
                    total_duration_minutes, total_duration_hours, average_session_duration_minutes,
                    total_cumulative_exposure, average_exposure_per_session, average_dose_rate_per_hour,
                    max_single_session_exposure, min_single_session_exposure,
                    daily_exposure, weekly_exposure, monthly_exposure, annual_exposure,
                    daily_exposure_percentage, weekly_exposure_percentage, 
                    monthly_exposure_percentage, annual_exposure_percentage,
                    total_readings, average_readings_per_session,
                    first_session_date, last_session_date, last_completed_session_date,
                    safety_status, safety_class, risk_level, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                emp_id,
                cumulative_data['total_sessions'],
                cumulative_data['completed_sessions'],
                cumulative_data['active_sessions'],
                cumulative_data['total_duration_minutes'],
                cumulative_data['total_duration_hours'],
                cumulative_data['average_session_duration_minutes'],
                cumulative_data['total_cumulative_exposure'],
                cumulative_data['average_exposure_per_session'],
                cumulative_data['average_dose_rate_per_hour'],
                cumulative_data['max_single_session_exposure'],
                cumulative_data['min_single_session_exposure'],
                cumulative_data['daily_exposure'],
                cumulative_data['weekly_exposure'],
                cumulative_data['monthly_exposure'],
                cumulative_data['annual_exposure'],
                cumulative_data['daily_exposure_percentage'],
                cumulative_data['weekly_exposure_percentage'],
                cumulative_data['monthly_exposure_percentage'],
                cumulative_data['annual_exposure_percentage'],
                cumulative_data['total_readings'],
                cumulative_data['average_readings_per_session'],
                cumulative_data['first_session_date'],
                cumulative_data['last_session_date'],
                cumulative_data['last_completed_session_date'],
                cumulative_data['safety_status'],
                cumulative_data['safety_class'],
                cumulative_data['risk_level'],
                datetime.now().isoformat()
            ))
            
            updated_count += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'updated_employees': updated_count,
            'message': f'تم تحديث بيانات {updated_count} موظف بنجاح'
        })
        
    except Exception as e:
        print(f"❌ خطأ في تحديث البيانات التراكمية: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def calculate_employee_cumulative_data_inline(cursor, employee_id):
    """حساب البيانات التراكمية لموظف محدد (نسخة مبسطة)"""
    
    # حدود الأمان
    daily_limit = 54.8
    weekly_limit = 383.6
    monthly_limit = 1643.8
    annual_limit = 20000.0
    
    # جلب بيانات الجلسات
    cursor.execute('''
        SELECT 
            id, session_date, check_in_time, check_out_time,
            exposure_duration_minutes, total_exposure, is_active
        FROM employee_exposure_sessions 
        WHERE employee_id = ?
        ORDER BY session_date, check_in_time
    ''', (employee_id,))
    
    sessions = cursor.fetchall()
    
    # حساب الإحصائيات
    total_sessions = len(sessions)
    completed_sessions = len([s for s in sessions if s[6] == 0])
    active_sessions = len([s for s in sessions if s[6] == 1])
    
    # حساب المدد والجرعات
    completed_session_data = [s for s in sessions if s[6] == 0 and s[5] is not None]
    
    total_duration_minutes = sum(s[4] or 0 for s in completed_session_data)
    total_duration_hours = total_duration_minutes / 60
    avg_session_duration = total_duration_minutes / max(completed_sessions, 1)
    
    exposures = [s[5] for s in completed_session_data if s[5] is not None]
    total_cumulative_exposure = sum(exposures) if exposures else 0.0
    avg_exposure_per_session = total_cumulative_exposure / max(completed_sessions, 1)
    avg_dose_rate_per_hour = total_cumulative_exposure / max(total_duration_hours, 1)
    max_exposure = max(exposures) if exposures else 0.0
    min_exposure = min(exposures) if exposures else 0.0
    
    # حساب الجرعات حسب الفترات
    today = datetime.now().date()
    daily_exposure = sum(s[5] or 0 for s in completed_session_data if s[1] == str(today))
    weekly_exposure = sum(s[5] or 0 for s in completed_session_data if (today - datetime.fromisoformat(s[1]).date()).days <= 7)
    monthly_exposure = sum(s[5] or 0 for s in completed_session_data if (today - datetime.fromisoformat(s[1]).date()).days <= 30)
    annual_exposure = sum(s[5] or 0 for s in completed_session_data if (today - datetime.fromisoformat(s[1]).date()).days <= 365)
    
    # حساب النسب المئوية
    daily_percentage = (daily_exposure / daily_limit * 100) if daily_limit > 0 else 0
    weekly_percentage = (weekly_exposure / weekly_limit * 100) if weekly_limit > 0 else 0
    monthly_percentage = (monthly_exposure / monthly_limit * 100) if monthly_limit > 0 else 0
    annual_percentage = (annual_exposure / annual_limit * 100) if annual_limit > 0 else 0
    
    # حساب عدد القراءات
    total_readings = 0
    for session in sessions:
        cursor.execute('SELECT COUNT(*) FROM radiation_readings_local WHERE session_id = ?', (session[0],))
        count = cursor.fetchone()[0]
        total_readings += count
    
    avg_readings_per_session = total_readings / max(total_sessions, 1)
    
    # التواريخ المهمة
    first_session_date = sessions[0][1] if sessions else None
    last_session_date = sessions[-1][1] if sessions else None
    completed_sessions_dates = [s[1] for s in sessions if s[6] == 0]
    last_completed_session_date = max(completed_sessions_dates) if completed_sessions_dates else None
    
    # حالة الأمان
    if annual_percentage >= 100:
        safety_status = "خطر - تجاوز الحد السنوي"
        safety_class = "danger"
        risk_level = "عالي جداً"
    elif annual_percentage >= 80:
        safety_status = "تحذير - اقتراب من الحد السنوي"
        safety_class = "warning"
        risk_level = "عالي"
    elif annual_percentage >= 50:
        safety_status = "مراقبة - نصف الحد السنوي"
        safety_class = "info"
        risk_level = "متوسط"
    else:
        safety_status = "آمن"
        safety_class = "success"
        risk_level = "منخفض"
    
    return {
        'total_sessions': total_sessions,
        'completed_sessions': completed_sessions,
        'active_sessions': active_sessions,
        'total_duration_minutes': total_duration_minutes,
        'total_duration_hours': total_duration_hours,
        'average_session_duration_minutes': avg_session_duration,
        'total_cumulative_exposure': total_cumulative_exposure,
        'average_exposure_per_session': avg_exposure_per_session,
        'average_dose_rate_per_hour': avg_dose_rate_per_hour,
        'max_single_session_exposure': max_exposure,
        'min_single_session_exposure': min_exposure,
        'daily_exposure': daily_exposure,
        'weekly_exposure': weekly_exposure,
        'monthly_exposure': monthly_exposure,
        'annual_exposure': annual_exposure,
        'daily_exposure_percentage': daily_percentage,
        'weekly_exposure_percentage': weekly_percentage,
        'monthly_exposure_percentage': monthly_percentage,
        'annual_exposure_percentage': annual_percentage,
        'total_readings': total_readings,
        'average_readings_per_session': avg_readings_per_session,
        'first_session_date': first_session_date,
        'last_session_date': last_session_date,
        'last_completed_session_date': last_completed_session_date,
        'safety_status': safety_status,
        'safety_class': safety_class,
        'risk_level': risk_level
    }

# =================================================================
# API endpoints للتحكم في مُجدول البيانات التراكمية
# =================================================================

@app.route('/api/scheduler/start', methods=['POST'])
def start_scheduler():
    """بدء تشغيل مُجدول البيانات التراكمية"""
    global global_scheduler
    
    try:
        if not SCHEDULER_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'مُجدول البيانات غير متاح'
            }), 400
        
        # تهيئة المُجدول إذا لم يكن موجوداً
        if global_scheduler is None:
            initialize_scheduler()
        
        if global_scheduler is None:
            return jsonify({
                'success': False,
                'error': 'فشل في تهيئة المُجدول'
            }), 500
        
        # بدء تشغيل المُجدول
        global_scheduler.start_scheduler()
        
        return jsonify({
            'success': True,
            'message': 'تم بدء تشغيل مُجدول البيانات التراكمية بنجاح',
            'status': global_scheduler.get_status()
        })
        
    except Exception as e:
        print(f"❌ خطأ في بدء تشغيل المُجدول: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scheduler/stop', methods=['POST'])
def stop_scheduler():
    """إيقاف مُجدول البيانات التراكمية"""
    global global_scheduler
    
    try:
        if global_scheduler is None:
            return jsonify({
                'success': False,
                'error': 'المُجدول غير مُعرَّف'
            }), 400
        
        global_scheduler.stop_scheduler()
        
        return jsonify({
            'success': True,
            'message': 'تم إيقاف مُجدول البيانات التراكمية بنجاح'
        })
        
    except Exception as e:
        print(f"❌ خطأ في إيقاف المُجدول: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """الحصول على حالة مُجدول البيانات التراكمية"""
    global global_scheduler
    
    try:
        if not SCHEDULER_AVAILABLE:
            return jsonify({
                'available': False,
                'message': 'مُجدول البيانات غير متاح'
            })
        
        if global_scheduler is None:
            return jsonify({
                'available': True,
                'initialized': False,
                'running': False,
                'message': 'المُجدول غير مُعرَّف بعد'
            })
        
        status = global_scheduler.get_status()
        status.update({
            'available': True,
            'initialized': True
        })
        
        return jsonify(status)
        
    except Exception as e:
        print(f"❌ خطأ في جلب حالة المُجدول: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/scheduler/force_update', methods=['POST'])
def force_scheduler_update():
    """إجبار تحديث فوري للبيانات التراكمية"""
    global global_scheduler
    
    try:
        employee_id = request.json.get('employee_id') if request.is_json else None
        
        if global_scheduler is None:
            return jsonify({
                'success': False,
                'error': 'المُجدول غير مُعرَّف'
            }), 400
        
        # تنفيذ تحديث فوري
        success = global_scheduler.update_cumulative_data_direct(employee_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'تم التحديث الفوري {"لموظف " + employee_id if employee_id else "لجميع الموظفين"} بنجاح'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'فشل في التحديث الفوري'
            }), 500
        
    except Exception as e:
        print(f"❌ خطأ في التحديث الفوري: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/employee_sessions/<employee_id>', methods=['GET'])
def get_employee_sessions(employee_id):
    """جلب جميع الجلسات الخاصة بموظف محدد مع التفاصيل الزمنية"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # جلب معلومات الموظف
        c.execute('SELECT name, department, position FROM employees WHERE employee_id = ?', (employee_id,))
        emp_info = c.fetchone()
        
        if not emp_info:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'لم يتم العثور على الموظف'
            }), 404
        
        # جلب جميع الجلسات (النشطة والمغلقة)
        c.execute('''SELECT 
                        id,
                        session_date,
                        check_in_time,
                        check_out_time,
                        exposure_duration_minutes,
                        total_exposure,
                        average_dose_rate,
                        max_dose_rate,
                        min_dose_rate,
                        is_active,
                        initial_total_dose,
                        final_total_dose
                     FROM employee_exposure_sessions
                     WHERE employee_id = ?
                     ORDER BY session_date DESC, check_in_time DESC''', (employee_id,))
        
        sessions = []
        for row in c.fetchall():
            session_id = row[0]
            is_active = row[9]
            check_in_time = row[2]
            check_out_time = row[3]
            duration_minutes = row[4]
            total_exposure = row[5] if row[5] is not None else 0.0
            initial_total_dose = row[10] if row[10] is not None else 0.0
            final_total_dose = row[11] if row[11] is not None else 0.0
            
            # ✨ حساب التعرض الصحيح باستخدام الفرق بين أول وآخر قراءة
            c2 = conn.cursor()
            c2.execute('''SELECT total_absorbed_dose 
                          FROM radiation_readings_local 
                          WHERE session_id = ? 
                          ORDER BY timestamp ASC LIMIT 1''', (session_id,))
            first_reading = c2.fetchone()
            
            c2.execute('''SELECT total_absorbed_dose 
                          FROM radiation_readings_local 
                          WHERE session_id = ? 
                          ORDER BY timestamp DESC LIMIT 1''', (session_id,))
            last_reading = c2.fetchone()
            
            if first_reading and last_reading and first_reading[0] is not None and last_reading[0] is not None:
                first_dose = float(first_reading[0])
                last_dose = float(last_reading[0])
                total_exposure = max(0.0, last_dose - first_dose)
                final_total_dose = last_dose
            elif total_exposure < 0:  # إذا كان هناك تعرض سالب في قاعدة البيانات، اجعله صفر
                total_exposure = 0.0
            
            # حساب المدة (نشطة أو مغلقة)
            if is_active and check_in_time:
                try:
                    check_in_dt = datetime.fromisoformat(check_in_time.replace('Z', '+00:00'))
                    current_time = datetime.now(timezone.utc)
                    duration_minutes = (current_time - check_in_dt).total_seconds() / 60
                except Exception:
                    duration_minutes = 0
            
            # حساب معدل الجرعة بالساعة
            duration_hours = duration_minutes / 60 if duration_minutes and duration_minutes > 0 else 0
            dose_rate_per_hour = (total_exposure / duration_hours) if duration_hours > 0 else 0
            
            # حساب عدد القراءات في هذه الجلسة
            c2 = conn.cursor()
            c2.execute('SELECT COUNT(*) FROM radiation_readings_local WHERE session_id = ?', (session_id,))
            readings_count = c2.fetchone()[0]
            
            sessions.append({
                'session_id': session_id,
                'session_date': row[1],
                'check_in_time': check_in_time,
                'check_out_time': check_out_time,
                'duration_minutes': round(duration_minutes, 2) if duration_minutes else None,
                'duration_hours': round(duration_hours, 2) if duration_hours else None,
                'total_exposure': round(total_exposure, 6),
                'average_dose_rate': round(row[6], 6) if row[6] else 0,
                'dose_rate_per_hour': round(dose_rate_per_hour, 6),
                'max_dose_rate': round(row[7], 6) if row[7] else 0,
                'min_dose_rate': round(row[8], 6) if row[8] else 0,
                'is_active': bool(is_active),
                'readings_count': readings_count,
                'initial_total_dose': round(initial_total_dose, 6),
                'final_total_dose': round(final_total_dose, 6)
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'employee_info': {
                'employee_id': employee_id,
                'name': emp_info[0],
                'department': emp_info[1] or '-',
                'position': emp_info[2] or '-'
            },
            'sessions': sessions,
            'total_sessions': len(sessions)
        })
        
    except Exception as e:
        print(f"❌ خطأ في جلب جلسات الموظف: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/session_readings/<int:session_id>', methods=['GET'])
def get_session_readings(session_id):
    """جلب جميع القراءات الخاصة بجلسة محددة"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # جلب معلومات الجلسة
        c.execute('''SELECT 
                        ses.id,
                        ses.employee_id,
                        e.name,
                        ses.check_in_time,
                        ses.check_out_time,
                        ses.session_date,
                        ses.exposure_duration_minutes,
                        ses.total_exposure,
                        ses.average_dose_rate,
                        ses.max_dose_rate,
                        ses.min_dose_rate
                     FROM employee_exposure_sessions ses
                     JOIN employees e ON ses.employee_id = e.employee_id
                     WHERE ses.id = ?''', (session_id,))
        
        session_info = c.fetchone()
        if not session_info:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'لم يتم العثور على الجلسة'
            }), 404
        
        # جلب جميع قراءات الجلسة
        c.execute('''SELECT 
                        id,
                        cpm,
                        source_power,
                        absorbed_dose_rate,
                        total_absorbed_dose,
                        timestamp
                     FROM radiation_readings_local
                     WHERE session_id = ?
                     ORDER BY timestamp ASC''', (session_id,))
        
        readings = []
        for row in c.fetchall():
            readings.append({
                'id': row[0],
                'cpm': row[1],
                'source_power': round(row[2], 6),
                'absorbed_dose_rate': round(row[3], 6),
                'total_absorbed_dose': round(row[4], 6),
                'timestamp': row[5]
            })
        
        conn.close()
        
        # حساب إحصائيات القراءات
        if readings:
            avg_cpm = sum(r['cpm'] for r in readings) / len(readings)
            avg_absorbed_dose_rate = sum(r['absorbed_dose_rate'] for r in readings) / len(readings)
        else:
            avg_cpm = 0
            avg_absorbed_dose_rate = 0
        
        return jsonify({
            'success': True,
            'session_info': {
                'session_id': session_info[0],
                'employee_id': session_info[1],
                'employee_name': session_info[2],
                'check_in_time': session_info[3],
                'check_out_time': session_info[4],
                'session_date': session_info[5],
                'duration_minutes': session_info[6],
                'total_exposure': round(session_info[7], 6) if session_info[7] else 0,
                'average_dose_rate': round(session_info[8], 6) if session_info[8] else 0,
                'max_dose_rate': round(session_info[9], 6) if session_info[9] else 0,
                'min_dose_rate': round(session_info[10], 6) if session_info[10] else 0
            },
            'readings': readings,
            'total_readings': len(readings),
            'readings_stats': {
                'avg_cpm': round(avg_cpm, 2),
                'avg_absorbed_dose_rate': round(avg_absorbed_dose_rate, 6)
            }
        })
        
    except Exception as e:
        print(f"❌ خطأ في جلب قراءات الجلسة: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ===================================
# نظام التنبيهات (Safety Alerts System)
# ===================================

# ===================================
# نظام التنبيهات (Safety Alerts System)
# ===================================

def create_safety_alert(employee_id, alert_type, alert_level, message, dose_value, threshold_value):
    """إنشاء تنبيه أمان جديد"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        # التحقق من عدم تكرار التنبيه في آخر 5 دقائق
        c.execute('''SELECT id FROM safety_alerts 
                     WHERE employee_id = ? 
                     AND alert_type = ? 
                     AND timestamp > datetime('now', '-5 minutes')
                     ORDER BY timestamp DESC LIMIT 1''', 
                  (employee_id, alert_type))
        
        recent_alert = c.fetchone()
        if recent_alert:
            conn.close()
            return False  # تنبيه مكرر
        
        # إنشاء التنبيه
        c.execute('''INSERT INTO safety_alerts 
                     (employee_id, alert_type, alert_level, message, dose_value, threshold_value)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (employee_id, alert_type, alert_level, message, dose_value, threshold_value))
        
        conn.commit()
        conn.close()
        
        print(f"🔔 تنبيه جديد: {message} - الموظف: {employee_id}")
        return True
        
    except Exception as e:
        print(f"❌ خطأ في إنشاء التنبيه: {e}")
        return False

def check_and_create_alerts(employee_id, dose_rate, daily_dose, annual_dose):
    """
    فحص وإنشاء التنبيهات تلقائياً وفقاً لمعايير الأمان للعاملين في المجال الإشعاعي
    بناءً على معايير ICRP-103 و IAEA
    """
    try:
        # ═══════════════════════════════════════════════════════════
        # الحدود الساعية (Hourly Limits)
        # ═══════════════════════════════════════════════════════════
        NATURAL_BACKGROUND = 0.3      # آمن: ≥ 0.3 μSv/h (الخلفية الطبيعية)
        DOSE_RATE_WARNING = 2.38      # تحذير: > 2.38 μSv/h
        DOSE_RATE_DANGER = 2.38       # خطر: ≤ 2.38 μSv/h
        
        # ═══════════════════════════════════════════════════════════
        # الحدود اليومية (Daily Limits)
        # ═══════════════════════════════════════════════════════════
        DAILY_LIMIT = 54.8            # الحد اليومي: 54.8 μSv/يوم
        DAILY_WARNING_80 = 43.8       # تحذير عند: 43.8 μSv (80%)
        DAILY_MONITORING_50 = 27.4    # مراقبة عند: 27.4 μSv (50%)
        
        # ═══════════════════════════════════════════════════════════
        # الحدود السنوية (Annual Limits)
        # ═══════════════════════════════════════════════════════════
        ANNUAL_LIMIT = 20000.0        # الحد السنوي: 20 mSv/سنة = 20000 μSv
        WEEKLY_LIMIT = 383.6          # الحد الأسبوعي: 383.6 μSv/أسبوع
        
        # جلب معلومات الموظف
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        c.execute('SELECT name FROM employees WHERE employee_id = ?', (employee_id,))
        result = c.fetchone()
        employee_name = result[0] if result else employee_id
        conn.close()
        
        # ═══════════════════════════════════════════════════════════
        # 1️⃣ تنبيهات معدل الجرعة الساعي
        # ═══════════════════════════════════════════════════════════
        
        if dose_rate > DOSE_RATE_DANGER:
            # خطر: معدل الجرعة أعلى من 2.38 μSv/h
            create_safety_alert(
                employee_id,
                'dose_rate_danger',
                'danger',
                f'⚠️ معدل جرعة خطر للموظف {employee_name}: {dose_rate:.2f} μSv/h (الحد: {DOSE_RATE_DANGER} μSv/h)',
                dose_rate,
                DOSE_RATE_DANGER
            )
        elif dose_rate > NATURAL_BACKGROUND:
            # تحذير: معدل الجرعة بين 0.3 و 2.38 μSv/h
            create_safety_alert(
                employee_id,
                'dose_rate_warning',
                'warning',
                f'⚠️ معدل جرعة مرتفع للموظف {employee_name}: {dose_rate:.2f} μSv/h (فوق الخلفية الطبيعية {NATURAL_BACKGROUND} μSv/h)',
                dose_rate,
                NATURAL_BACKGROUND
            )
        
        # ═══════════════════════════════════════════════════════════
        # 2️⃣ تنبيهات الجرعة اليومية
        # ═══════════════════════════════════════════════════════════
        
        daily_percentage = (daily_dose / DAILY_LIMIT) * 100
        
        if daily_dose >= DAILY_LIMIT:
            # خطر حرج: تجاوز الحد اليومي (≥ 100%)
            create_safety_alert(
                employee_id,
                'daily_limit_exceeded',
                'critical',
                f'🚨 تجاوز الحد اليومي للموظف {employee_name}: {daily_dose:.2f} μSv ({daily_percentage:.1f}%) | الحد: {DAILY_LIMIT} μSv',
                daily_dose,
                DAILY_LIMIT
            )
        elif daily_dose >= DAILY_WARNING_80:
            # تحذير: اقتراب من الحد اليومي (≥ 80%)
            create_safety_alert(
                employee_id,
                'daily_limit_warning_80',
                'warning',
                f'⚠️ اقتراب من الحد اليومي للموظف {employee_name}: {daily_dose:.2f} μSv ({daily_percentage:.1f}%) | الحد: {DAILY_LIMIT} μSv',
                daily_dose,
                DAILY_LIMIT
            )
        elif daily_dose >= DAILY_MONITORING_50:
            # مراقبة: وصول لنصف الحد اليومي (≥ 50%)
            create_safety_alert(
                employee_id,
                'daily_limit_monitoring_50',
                'info',
                f'📊 مراقبة - نصف الحد اليومي للموظف {employee_name}: {daily_dose:.2f} μSv ({daily_percentage:.1f}%) | الحد: {DAILY_LIMIT} μSv',
                daily_dose,
                DAILY_LIMIT
            )
        
        # ═══════════════════════════════════════════════════════════
        # 3️⃣ تنبيهات الجرعة السنوية
        # ═══════════════════════════════════════════════════════════
        
        annual_percentage = (annual_dose / ANNUAL_LIMIT) * 100
        
        if annual_dose >= ANNUAL_LIMIT:
            # خطر حرج: تجاوز الحد السنوي (≥ 100%)
            create_safety_alert(
                employee_id,
                'annual_limit_exceeded',
                'critical',
                f'🚨 تجاوز الحد السنوي للموظف {employee_name}: {annual_dose:.2f} μSv ({annual_percentage:.1f}%) | الحد: {ANNUAL_LIMIT/1000:.1f} mSv',
                annual_dose,
                ANNUAL_LIMIT
            )
        elif annual_percentage >= 80:
            # تحذير: اقتراب من الحد السنوي (≥ 80%)
            create_safety_alert(
                employee_id,
                'annual_limit_warning_80',
                'warning',
                f'⚠️ اقتراب من الحد السنوي للموظف {employee_name}: {annual_dose:.2f} μSv ({annual_percentage:.1f}%) | الحد: {ANNUAL_LIMIT/1000:.1f} mSv',
                annual_dose,
                ANNUAL_LIMIT
            )
        elif annual_percentage >= 50:
            # مراقبة: وصول لنصف الحد السنوي (≥ 50%)
            create_safety_alert(
                employee_id,
                'annual_limit_monitoring_50',
                'info',
                f'📊 مراقبة - نصف الحد السنوي للموظف {employee_name}: {annual_dose:.2f} μSv ({annual_percentage:.1f}%) | الحد: {ANNUAL_LIMIT/1000:.1f} mSv',
                annual_dose,
                ANNUAL_LIMIT
            )
        
        print(f"✅ تم فحص التنبيهات للموظف {employee_name}: معدل={dose_rate:.2f}, يومي={daily_dose:.2f}, سنوي={annual_dose:.2f}")
        
    except Exception as e:
        print(f"❌ خطأ في فحص التنبيهات: {e}")

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """API لجلب التنبيهات"""
    try:
        employee_id = request.args.get('employee_id', '')
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        limit = int(request.args.get('limit', 50))
        
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        query = '''
            SELECT a.id, a.employee_id, e.name, a.alert_type, a.alert_level, 
                   a.message, a.dose_value, a.threshold_value, a.timestamp, a.acknowledged
            FROM safety_alerts a
            LEFT JOIN employees e ON a.employee_id = e.employee_id
            WHERE 1=1
        '''
        params = []
        
        if employee_id:
            query += ' AND a.employee_id = ?'
            params.append(employee_id)
        
        if unread_only:
            query += ' AND a.acknowledged = 0'
        
        query += ' ORDER BY a.timestamp DESC LIMIT ?'
        params.append(limit)
        
        c.execute(query, params)
        
        alerts = []
        for row in c.fetchall():
            alerts.append({
                'id': row[0],
                'employee_id': row[1],
                'employee_name': row[2] or row[1],
                'alert_type': row[3],
                'alert_level': row[4],
                'message': row[5],
                'dose_value': row[6],
                'threshold_value': row[7],
                'timestamp': row[8],
                'acknowledged': bool(row[9])
            })
        
        # حساب عدد التنبيهات غير المقروءة
        c.execute('SELECT COUNT(*) FROM safety_alerts WHERE acknowledged = 0')
        unread_count = c.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'total_alerts': len(alerts),
            'unread_count': unread_count
        })
        
    except Exception as e:
        print(f"❌ خطأ في جلب التنبيهات: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['POST'])
def acknowledge_alert(alert_id):
    """تحديد تنبيه كمقروء"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        c.execute('UPDATE safety_alerts SET acknowledged = 1 WHERE id = ?', (alert_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'تم تحديد التنبيه كمقروء'
        })
        
    except Exception as e:
        print(f"❌ خطأ في تحديث التنبيه: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/alerts/acknowledge_all', methods=['POST'])
def acknowledge_all_alerts():
    """تحديد جميع التنبيهات كمقروءة"""
    try:
        conn = sqlite3.connect('attendance.db')
        c = conn.cursor()
        
        c.execute('UPDATE safety_alerts SET acknowledged = 1 WHERE acknowledged = 0')
        updated_count = c.rowcount
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'تم تحديد {updated_count} تنبيه كمقروء'
        })
        
    except Exception as e:
        print(f"❌ خطأ في تحديث التنبيهات: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # تهيئة قواعد البيانات والنظام
    print("🚀 بدء تشغيل نظام مراقبة الإشعاع...")
    init_db()
    update_cache_from_local_db()
    
    # تشغيل تلقائي لمُجدول البيانات التراكمية
    if SCHEDULER_AVAILABLE:
        try:
            print("🔄 تهيئة مُجدول البيانات التراكمية...")
            initialize_scheduler()
            if global_scheduler:
                def delayed_scheduler_start():
                    """تشغيل مُؤجل للمُجدول بعد بدء الخادم"""
                    time.sleep(5)  # انتظار 5 ثواني لضمان بدء تشغيل الخادم
                    try:
                        global_scheduler.start_scheduler()
                        print("✅ تم بدء تشغيل مُجدول البيانات التراكمية تلقائياً")
                    except Exception as e:
                        print(f"❌ فشل في تشغيل المُجدول التلقائي: {e}")
                
                # بدء المُجدول في thread منفصل
                threading.Thread(target=delayed_scheduler_start, daemon=True).start()
        except Exception as e:
            print(f"❌ خطأ في تهيئة المُجدول: {e}")
    else:
        print("⚠️ مُجدول البيانات التراكمية غير متاح")
    
    # عرض معلومات الشبكة
    local_ip = get_local_ip()
    print(f"🌍 الخادم يعمل على:")
    print(f"    http://localhost:{port}/")
    print(f"    http://{local_ip}:{port}/")
    
    try:
        # تشغيل التطبيق
        app.run(host='0.0.0.0', port=port, debug=True)
    except KeyboardInterrupt:
        print("\n🛑 إيقاف النظام...")
        # إيقاف المُجدول عند إغلاق النظام
        if global_scheduler:
            try:
                global_scheduler.stop_scheduler()
                print("✅ تم إيقاف مُجدول البيانات التراكمية")
            except Exception as e:
                print(f"❌ خطأ في إيقاف المُجدول: {e}")
        print("👋 تم إنهاء النظام بنجاح")

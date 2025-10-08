"""
Configuration file for AI Face Recognition Attendance System
ملف التكوين لنظام تسجيل الحضور بالذكاء الاصطناعي
"""

# Camera Settings / إعدادات الكاميرا
CAMERA_INDEX = 1  # Camera index (1 for external camera)
CAMERA_WIDTH = 640  # تم تعديل الدقة لتحسين الأداء
CAMERA_HEIGHT = 480  # تم تعديل الدقة لتحسين الأداء
CAMERA_FPS = 30
CAMERA_FALLBACK_INDEX = 0  # استخدام الكاميرا 0 كبديل في حالة فشل الكاميرا 1

# Face Recognition Settings / إعدادات التعرف على الوجوه
FACE_RECOGNITION_TOLERANCE = 0.6  # Lower = more strict, Higher = more lenient
MIN_IMAGES_FOR_REGISTRATION = 5   # Minimum images required for user registration
FACE_DETECTION_MODEL = "hog"      # "hog" or "cnn" (cnn is more accurate but slower)

# Database Settings / إعدادات قاعدة البيانات
DATABASE_NAME = "attendance.db"
DATASET_FOLDER = "dataset"

# UI Settings / إعدادات الواجهة
WINDOW_TITLE = "DoseMeter - Radiation Monitoring"
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 800

# Colors / الألوان
PRIMARY_COLOR = "#4CAF50"
SECONDARY_COLOR = "#3498db"
DANGER_COLOR = "#e74c3c"
WARNING_COLOR = "#f39c12"
SUCCESS_COLOR = "#27ae60"
NEUTRAL_COLOR = "#95a5a6"

# Attendance Settings / إعدادات الحضور
ATTENDANCE_COOLDOWN_HOURS = 1  # Hours between attendance records for same person
AUTO_SAVE_INTERVAL = 30        # Seconds between auto-saves

# Language Settings / إعدادات اللغة
DEFAULT_LANGUAGE = "en"  # default English UI
RTL_LAYOUT = False        # Left-to-right layout for English

# File Formats / تنسيقات الملفات
SUPPORTED_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp']
IMAGE_QUALITY = 95  # JPEG quality (1-100)

# Security Settings / إعدادات الأمان
MAX_FAILED_ATTEMPTS = 10
LOCKOUT_DURATION_MINUTES = 5

# Performance Settings / إعدادات الأداء
FRAME_SKIP = 2  # Process every nth frame for better performance
MAX_FACE_DISTANCE = 0.6  # Maximum distance for face matching
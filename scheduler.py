#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
مُجدول تحديث البيانات التراكمية للموظفين
يقوم بتحديث جدول employee_cumulative_data تلقائياً كل فترة محددة
"""

import sqlite3
import time
import threading
from datetime import datetime, timedelta
import schedule
import requests
import json

class CumulativeDataScheduler:
    def __init__(self, api_base_url="http://localhost:5000"):
        """
        إعداد المُجدول
        :param api_base_url: عنوان API الخاص بالتطبيق
        """
        self.api_base_url = api_base_url
        self.db_path = 'attendance.db'
        self.is_running = False
        self.update_thread = None
        
        # إعدادات المجدول
        self.update_interval_minutes = 5  # كل 5 دقائق
        self.force_update_interval_hours = 1  # إجباري كل ساعة
        
        print("🕒 تم تهيئة مُجدول البيانات التراكمية")
    
    def update_cumulative_data_direct(self, employee_id=None):
        """تحديث البيانات مباشرة عبر قاعدة البيانات"""
        try:
            print(f"🔄 بدء تحديث البيانات التراكمية - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # تحديد الموظفين المراد تحديثهم
            if employee_id:
                employees_to_update = [(employee_id,)]
                print(f"   📋 تحديث موظف محدد: {employee_id}")
            else:
                cursor.execute('SELECT DISTINCT employee_id FROM employee_exposure_sessions')
                employees_to_update = cursor.fetchall()
                print(f"   📋 تحديث جميع الموظفين: {len(employees_to_update)} موظف")
            
            updated_count = 0
            
            for emp in employees_to_update:
                emp_id = emp[0]
                
                # التحقق من وجود جلسات نشطة أو تغييرات حديثة
                cursor.execute('''
                    SELECT COUNT(*) FROM employee_exposure_sessions 
                    WHERE employee_id = ? AND (
                        is_active = 1 OR 
                        datetime(created_at) > datetime('now', '-1 hour')
                    )
                ''', (emp_id,))
                
                has_recent_activity = cursor.fetchone()[0] > 0
                
                # التحقق من آخر تحديث للبيانات التراكمية
                cursor.execute('''
                    SELECT last_updated FROM employee_cumulative_data 
                    WHERE employee_id = ?
                ''', (emp_id,))
                
                last_update_result = cursor.fetchone()
                needs_update = True
                
                if last_update_result and not has_recent_activity:
                    last_update = datetime.fromisoformat(last_update_result[0])
                    if datetime.now() - last_update < timedelta(minutes=self.update_interval_minutes):
                        needs_update = False
                
                if needs_update:
                    self.calculate_and_update_employee_data(cursor, emp_id)
                    updated_count += 1
                    print(f"   ✅ تم تحديث بيانات الموظف: {emp_id}")
            
            conn.commit()
            conn.close()
            
            print(f"✨ انتهى التحديث - تم تحديث {updated_count} موظف")
            return True
            
        except Exception as e:
            print(f"❌ خطأ في التحديث المباشر: {e}")
            return False
    
    def update_cumulative_data_via_api(self, employee_id=None):
        """تحديث البيانات عبر API"""
        try:
            url = f"{self.api_base_url}/api/update_cumulative_data"
            
            data = {}
            if employee_id:
                data['employee_id'] = employee_id
            
            response = requests.post(url, 
                                   json=data, 
                                   headers={'Content-Type': 'application/json'},
                                   timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ تحديث عبر API ناجح: {result.get('message', 'تم التحديث')}")
                return True
            else:
                print(f"⚠️ خطأ في API: {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"🌐 خطأ في الاتصال بـ API: {e}")
            return False
        except Exception as e:
            print(f"❌ خطأ عام في التحديث عبر API: {e}")
            return False
    
    def calculate_and_update_employee_data(self, cursor, employee_id):
        """حساب وتحديث بيانات موظف واحد"""
        
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
        
        # تحديث أو إدراج البيانات
        cursor.execute('''
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
            employee_id,
            total_sessions, completed_sessions, active_sessions,
            total_duration_minutes, total_duration_hours, avg_session_duration,
            total_cumulative_exposure, avg_exposure_per_session, avg_dose_rate_per_hour,
            max_exposure, min_exposure,
            daily_exposure, weekly_exposure, monthly_exposure, annual_exposure,
            daily_percentage, weekly_percentage, monthly_percentage, annual_percentage,
            total_readings, avg_readings_per_session,
            first_session_date, last_session_date, last_completed_session_date,
            safety_status, safety_class, risk_level,
            datetime.now().isoformat()
        ))
    
    def scheduled_update(self):
        """المهمة المُجدولة للتحديث"""
        print(f"⏰ تشغيل التحديث المُجدول - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # محاولة التحديث عبر API أولاً
        success = self.update_cumulative_data_via_api()
        
        # إذا فشل API، جرب التحديث المباشر
        if not success:
            print("🔄 محاولة التحديث المباشر...")
            success = self.update_cumulative_data_direct()
        
        if success:
            print("✅ تم التحديث المُجدول بنجاح")
        else:
            print("❌ فشل التحديث المُجدول")
    
    def forced_full_update(self):
        """تحديث شامل إجباري لجميع الموظفين"""
        print(f"🔥 تحديث شامل إجباري - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.update_cumulative_data_direct()
    
    def start_scheduler(self):
        """بدء تشغيل المُجدول"""
        if self.is_running:
            print("⚠️ المُجدول يعمل بالفعل!")
            return
        
        # إعداد المهام المُجدولة
        schedule.every(self.update_interval_minutes).minutes.do(self.scheduled_update)
        schedule.every(self.force_update_interval_hours).hours.do(self.forced_full_update)
        
        # تحديث أولي
        print("🚀 تشغيل تحديث أولي...")
        self.forced_full_update()
        
        self.is_running = True
        
        def run_scheduler():
            while self.is_running:
                schedule.run_pending()
                time.sleep(10)  # فحص كل 10 ثواني
        
        self.update_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.update_thread.start()
        
        print(f"✅ تم تشغيل مُجدول البيانات التراكمية")
        print(f"   📅 التحديث العادي: كل {self.update_interval_minutes} دقيقة")
        print(f"   📅 التحديث الشامل: كل {self.force_update_interval_hours} ساعة")
    
    def stop_scheduler(self):
        """إيقاف المُجدول"""
        if not self.is_running:
            print("⚠️ المُجدول متوقف بالفعل!")
            return
        
        self.is_running = False
        schedule.clear()
        
        if self.update_thread:
            self.update_thread.join(timeout=5)
        
        print("⏹️ تم إيقاف مُجدول البيانات التراكمية")
    
    def get_status(self):
        """الحصول على حالة المُجدول"""
        return {
            'is_running': self.is_running,
            'update_interval_minutes': self.update_interval_minutes,
            'force_update_interval_hours': self.force_update_interval_hours,
            'next_runs': [str(job.next_run) for job in schedule.jobs] if self.is_running else []
        }


# مثال للاستخدام المستقل
if __name__ == "__main__":
    print("🎯 تشغيل مُجدول البيانات التراكمية")
    
    # إنشاء مُجدول
    scheduler = CumulativeDataScheduler()
    
    try:
        # تشغيل المُجدول
        scheduler.start_scheduler()
        
        print("⏳ المُجدول يعمل... (اضغط Ctrl+C للإيقاف)")
        
        # الحفاظ على تشغيل البرنامج
        while True:
            time.sleep(60)
            status = scheduler.get_status()
            print(f"📊 حالة المُجدول: {status}")
            
    except KeyboardInterrupt:
        print("\n🛑 إيقاف المُجدول...")
        scheduler.stop_scheduler()
        print("👋 تم إنهاء البرنامج")
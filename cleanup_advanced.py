#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
أداة تنظيف قاعدة البيانات المتقدمة
Advanced Database Cleanup Tool

خيارات التنظيف:
1. تنظيف كامل (جميع البيانات)
2. تنظيف الموظفين فقط
3. تنظيف الحضور فقط
4. تنظيف قراءات الإشعاع فقط
5. تنظيف جلسات التعرض فقط
6. تنظيف الصور فقط
"""

import sqlite3
import os
import shutil
from datetime import datetime
import argparse

class AdvancedDatabaseCleanup:
    """فئة تنظيف قاعدة البيانات المتقدمة"""
    
    def __init__(self, db_path='attendance.db'):
        self.db_path = db_path
        self.backup_path = None
        
    def create_backup(self):
        """إنشاء نسخة احتياطية"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = 'database_backups'
            
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            self.backup_path = os.path.join(backup_dir, f'attendance_backup_{timestamp}.db')
            shutil.copy2(self.db_path, self.backup_path)
            
            print(f"✅ نسخة احتياطية: {self.backup_path}")
            return True
            
        except Exception as e:
            print(f"❌ فشل النسخ الاحتياطي: {e}")
            return False
    
    def clean_employees(self):
        """تنظيف بيانات الموظفين"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM employees")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM employees")
            conn.commit()
            conn.close()
            
            # حذف صور الموظفين
            if os.path.exists('dataset'):
                for folder in os.listdir('dataset'):
                    folder_path = os.path.join('dataset', folder)
                    if os.path.isdir(folder_path):
                        shutil.rmtree(folder_path)
            
            if os.path.exists('static/employees'):
                for file in os.listdir('static/employees'):
                    os.remove(os.path.join('static/employees', file))
            
            print(f"✅ تم حذف {count} موظف")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_attendance(self):
        """تنظيف سجلات الحضور"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM attendance")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM attendance")
            conn.commit()
            conn.close()
            
            # حذف صور الحضور
            if os.path.exists('static/attendance'):
                for file in os.listdir('static/attendance'):
                    os.remove(os.path.join('static/attendance', file))
            
            print(f"✅ تم حذف {count} سجل حضور")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_radiation(self):
        """تنظيف قراءات الإشعاع"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM radiation_readings_local")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM radiation_readings_local")
            conn.commit()
            conn.close()
            
            print(f"✅ تم حذف {count} قراءة إشعاع")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_exposure_sessions(self):
        """تنظيف جلسات التعرض"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM employee_exposure_sessions")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM employee_exposure_sessions")
            conn.commit()
            conn.close()
            
            print(f"✅ تم حذف {count} جلسة تعرض")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_safety_alerts(self):
        """تنظيف التنبيهات الأمنية"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM safety_alerts")
            count = cursor.fetchone()[0]
            
            cursor.execute("DELETE FROM safety_alerts")
            conn.commit()
            conn.close()
            
            print(f"✅ تم حذف {count} تنبيه أمني")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_images_only(self):
        """حذف الصور فقط"""
        try:
            deleted = 0
            
            # صور الموظفين
            if os.path.exists('dataset'):
                for folder in os.listdir('dataset'):
                    folder_path = os.path.join('dataset', folder)
                    if os.path.isdir(folder_path):
                        for file in os.listdir(folder_path):
                            os.remove(os.path.join(folder_path, file))
                            deleted += 1
            
            if os.path.exists('static/employees'):
                for file in os.listdir('static/employees'):
                    os.remove(os.path.join('static/employees', file))
                    deleted += 1
            
            # صور الحضور
            if os.path.exists('static/attendance'):
                for file in os.listdir('static/attendance'):
                    os.remove(os.path.join('static/attendance', file))
                    deleted += 1
            
            print(f"✅ تم حذف {deleted} صورة")
            return True
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
            return False
    
    def clean_all(self):
        """تنظيف كامل"""
        print("\n🧹 تنظيف شامل...")
        
        self.clean_safety_alerts()
        self.clean_exposure_sessions()
        self.clean_radiation()
        self.clean_attendance()
        self.clean_employees()
        
        # إعادة تعيين العدادات
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sqlite_sequence")
            conn.commit()
            conn.close()
            print("✅ تم إعادة تعيين العدادات")
        except:
            pass
        
        return True
    
    def show_menu(self):
        """عرض القائمة التفاعلية"""
        print("\n" + "=" * 60)
        print("🧹 أداة تنظيف قاعدة البيانات المتقدمة")
        print("=" * 60)
        print("\nالخيارات المتاحة:")
        print("  1. تنظيف كامل (جميع البيانات)")
        print("  2. تنظيف الموظفين فقط")
        print("  3. تنظيف الحضور فقط")
        print("  4. تنظيف قراءات الإشعاع فقط")
        print("  5. تنظيف جلسات التعرض فقط")
        print("  6. تنظيف التنبيهات الأمنية فقط")
        print("  7. تنظيف الصور فقط")
        print("  8. عرض الإحصائيات")
        print("  0. خروج")
        print("=" * 60)
    
    def get_stats(self):
        """عرض الإحصائيات"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            print("\n📊 إحصائيات قاعدة البيانات:")
            print("-" * 60)
            
            tables = [
                ('employees', 'الموظفين'),
                ('attendance', 'سجلات الحضور'),
                ('radiation_readings_local', 'قراءات الإشعاع'),
                ('employee_exposure_sessions', 'جلسات التعرض'),
                ('safety_alerts', 'التنبيهات الأمنية')
            ]
            
            total = 0
            for table, name in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                total += count
                print(f"  {name:.<40} {count:>5}")
            
            print("-" * 60)
            print(f"  {'الإجمالي':.<40} {total:>5}")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ خطأ: {e}")
    
    def run_interactive(self):
        """تشغيل الوضع التفاعلي"""
        while True:
            self.show_menu()
            
            try:
                choice = input("\n👉 اختر رقم العملية: ").strip()
                
                if choice == '0':
                    print("\n👋 إلى اللقاء!")
                    break
                
                if choice == '8':
                    self.get_stats()
                    continue
                
                # تأكيد العملية
                print("\n⚠️  تحذير: هذه العملية لا يمكن التراجع عنها!")
                confirm = input("❓ هل تريد المتابعة؟ (yes/no): ").strip().lower()
                
                if confirm != 'yes':
                    print("❌ تم الإلغاء")
                    continue
                
                # إنشاء نسخة احتياطية
                backup = input("❓ إنشاء نسخة احتياطية؟ (y/n): ").strip().lower()
                if backup == 'y':
                    self.create_backup()
                
                # تنفيذ العملية
                if choice == '1':
                    self.clean_all()
                elif choice == '2':
                    self.clean_employees()
                elif choice == '3':
                    self.clean_attendance()
                elif choice == '4':
                    self.clean_radiation()
                elif choice == '5':
                    self.clean_exposure_sessions()
                elif choice == '6':
                    self.clean_safety_alerts()
                elif choice == '7':
                    self.clean_images_only()
                else:
                    print("❌ خيار غير صحيح!")
                
                print("\n✅ تمت العملية بنجاح!")
                
            except KeyboardInterrupt:
                print("\n\n👋 تم الإيقاف")
                break
            except Exception as e:
                print(f"\n❌ خطأ: {e}")


def main():
    """الدالة الرئيسية"""
    
    parser = argparse.ArgumentParser(description='أداة تنظيف قاعدة البيانات')
    parser.add_argument('--all', action='store_true', help='تنظيف كامل')
    parser.add_argument('--employees', action='store_true', help='تنظيف الموظفين')
    parser.add_argument('--attendance', action='store_true', help='تنظيف الحضور')
    parser.add_argument('--radiation', action='store_true', help='تنظيف الإشعاع')
    parser.add_argument('--exposure', action='store_true', help='تنظيف جلسات التعرض')
    parser.add_argument('--images', action='store_true', help='تنظيف الصور')
    parser.add_argument('--stats', action='store_true', help='عرض الإحصائيات')
    parser.add_argument('--no-backup', action='store_true', help='بدون نسخة احتياطية')
    
    args = parser.parse_args()
    
    cleanup = AdvancedDatabaseCleanup()
    
    # إذا لم يتم تحديد أي خيار، تشغيل الوضع التفاعلي
    if not any([args.all, args.employees, args.attendance, args.radiation, 
                args.exposure, args.images, args.stats]):
        cleanup.run_interactive()
        return
    
    # تنفيذ الخيارات من سطر الأوامر
    if args.stats:
        cleanup.get_stats()
        return
    
    if not args.no_backup:
        cleanup.create_backup()
    
    if args.all:
        cleanup.clean_all()
    else:
        if args.employees:
            cleanup.clean_employees()
        if args.attendance:
            cleanup.clean_attendance()
        if args.radiation:
            cleanup.clean_radiation()
        if args.exposure:
            cleanup.clean_exposure_sessions()
        if args.images:
            cleanup.clean_images_only()


if __name__ == "__main__":
    main()


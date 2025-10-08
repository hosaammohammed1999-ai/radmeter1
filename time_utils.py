# -*- coding: utf-8 -*-
"""
نظام حسابات زمنية محسن لدقة أعلى في قياس التعرض الإشعاعي
Enhanced Time Calculation System for Higher Precision in Radiation Exposure Measurement
"""

from datetime import datetime, timezone, timedelta
from typing import Union, Tuple, Optional
import pytz
from decimal import Decimal, ROUND_HALF_UP
import time

# إعدادات المنطقة الزمنية
TIMEZONE = pytz.timezone('Asia/Baghdad')  # التوقيت العراقي/بغداد
UTC = pytz.UTC

# إعداد اللغة الافتراضية (استخدام config إذا كان متاحاً)
try:
    from config import DEFAULT_LANGUAGE as _DEFAULT_LANG
except Exception:
    _DEFAULT_LANG = 'en'

class PrecisionTimeCalculator:
    """حاسبة زمنية عالية الدقة للتطبيقات الإشعاعية"""
    
    def __init__(self, timezone_name: str = 'Asia/Baghdad'):
        """
        تهيئة الحاسبة الزمنية

        Args:
            timezone_name: اسم المنطقة الزمنية (افتراضي: Asia/Baghdad)
        """
        self.local_tz = pytz.timezone(timezone_name)
        self.utc = pytz.UTC
        
    def get_current_time(self, use_utc: bool = False) -> datetime:
        """
        الحصول على الوقت الحالي بدقة عالية
        
        Args:
            use_utc: استخدام UTC بدلاً من التوقيت المحلي
            
        Returns:
            datetime: الوقت الحالي مع معلومات المنطقة الزمنية
        """
        if use_utc:
            return datetime.now(self.utc)
        else:
            return datetime.now(self.local_tz)
    
    def normalize_datetime(self, dt: Union[str, datetime]) -> datetime:
        """
        توحيد تنسيق التاريخ والوقت
        
        Args:
            dt: التاريخ والوقت (string أو datetime)
            
        Returns:
            datetime: تاريخ ووقت موحد مع معلومات المنطقة الزمنية
        """
        if isinstance(dt, str):
            # محاولة تحليل التنسيقات مع المنطقة الزمنية أولاً
            try:
                # إذا كان التاريخ يحتوي على معلومات المنطقة الزمنية
                if '+' in dt or 'Z' in dt:
                    # استخدام fromisoformat للتعامل مع ISO format مع المنطقة الزمنية
                    if dt.endswith('Z'):
                        dt = dt.replace('Z', '+00:00')
                    parsed_dt = datetime.fromisoformat(dt)
                    # تحويل إلى المنطقة الزمنية المحلية
                    return parsed_dt.astimezone(self.local_tz)
            except ValueError:
                pass

            # إزالة معلومات المنطقة الزمنية للتحليل التقليدي
            clean_dt_str = dt.replace('Z', '').replace('+00:00', '')
            # إزالة أي معلومات منطقة زمنية أخرى
            import re
            clean_dt_str = re.sub(r'[+-]\d{2}:\d{2}$', '', clean_dt_str)

            # محاولة تحليل التنسيقات المختلفة
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',  # مع الميكروثانية
                '%Y-%m-%d %H:%M:%S',     # بدون الميكروثانية
                '%Y-%m-%dT%H:%M:%S.%f',  # ISO format مع الميكروثانية
                '%Y-%m-%dT%H:%M:%S',     # ISO format بدون الميكروثانية
            ]
            
            parsed_dt = None
            for fmt in formats:
                try:
                    parsed_dt = datetime.strptime(clean_dt_str, fmt)
                    break
                except ValueError:
                    continue
            
            if parsed_dt is None:
                raise ValueError(f"Unable to parse datetime string: {dt}")
            
            # إضافة معلومات المنطقة الزمنية إذا لم تكن موجودة
            if parsed_dt.tzinfo is None:
                parsed_dt = self.local_tz.localize(parsed_dt)
            
            return parsed_dt
        
        elif isinstance(dt, datetime):
            # إضافة معلومات المنطقة الزمنية إذا لم تكن موجودة
            if dt.tzinfo is None:
                return self.local_tz.localize(dt)
            return dt
        
        else:
            raise TypeError(f"Unsupported datetime type: {type(dt)}")
    
    def calculate_duration(self, start_time: Union[str, datetime], 
                          end_time: Union[str, datetime] = None) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
        """
        حساب المدة بدقة عالية
        
        Args:
            start_time: وقت البداية
            end_time: وقت النهاية (افتراضي: الوقت الحالي)
            
        Returns:
            Tuple: (ثواني, دقائق, ساعات, أيام) بدقة عالية
        """
        start_dt = self.normalize_datetime(start_time)
        
        if end_time is None:
            end_dt = self.get_current_time()
        else:
            end_dt = self.normalize_datetime(end_time)
        
        # التأكد من أن كلا التوقيتين في نفس المنطقة الزمنية
        if start_dt.tzinfo != end_dt.tzinfo:
            end_dt = end_dt.astimezone(start_dt.tzinfo)
        
        # حساب الفرق بدقة الميكروثانية
        duration = end_dt - start_dt
        total_seconds = Decimal(str(duration.total_seconds()))
        
        # حساب الوحدات المختلفة بدقة عالية
        seconds = total_seconds
        minutes = total_seconds / Decimal('60')
        hours = total_seconds / Decimal('3600')
        days = total_seconds / Decimal('86400')
        
        return seconds, minutes, hours, days
    
    def calculate_precise_exposure(self, dose_rate: float, duration_hours: Decimal) -> Decimal:
        """
        حساب التعرض بدقة عالية
        
        Args:
            dose_rate: معدل الجرعة (μSv/h)
            duration_hours: المدة بالساعات
            
        Returns:
            Decimal: التعرض الإجمالي (μSv) بدقة عالية
        """
        dose_rate_decimal = Decimal(str(dose_rate))
        exposure = dose_rate_decimal * duration_hours
        
        # تقريب إلى 6 خانات عشرية
        return exposure.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    
    def format_duration(self, seconds: Decimal, language: str = None) -> str:
        """
        تنسيق المدة بشكل قابل للقراءة (يدعم العربية والإنجليزية)
        
        Args:
            seconds: المدة بالثواني
            language: رمز اللغة ('ar' أو 'en'). إذا لم يحدد، يُستخدم من الإعدادات.
            
        Returns:
            str: المدة منسقة، مثال EN: "2 hours 30 minutes 15 seconds"، AR: "2 ساعة 30 دقيقة 15 ثانية"
        """
        total_seconds = int(seconds)
        
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        lang = (language or _DEFAULT_LANG or 'en').lower()
        parts = []
        
        if lang.startswith('en'):
            # صيغ إنجليزية مع مفرد/جمع صحيح
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            if minutes > 0:
                parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
            if secs > 0 or not parts:
                parts.append(f"{secs} second{'s' if secs != 1 else ''}")
        else:
            # صيغة عربية
            if days > 0:
                parts.append(f"{days} يوم")
            if hours > 0:
                parts.append(f"{hours} ساعة")
            if minutes > 0:
                parts.append(f"{minutes} دقيقة")
            if secs > 0 or not parts:
                parts.append(f"{secs} ثانية")
        
        return " ".join(parts)
    def get_time_intervals(self, start_time: Union[str, datetime], 
                          end_time: Union[str, datetime], 
                          interval_minutes: int = 1) -> list:
        """
        تقسيم الفترة الزمنية إلى فترات فرعية
        
        Args:
            start_time: وقت البداية
            end_time: وقت النهاية
            interval_minutes: طول الفترة الفرعية بالدقائق
            
        Returns:
            list: قائمة بالفترات الزمنية
        """
        start_dt = self.normalize_datetime(start_time)
        end_dt = self.normalize_datetime(end_time)
        
        intervals = []
        current_time = start_dt
        interval_delta = timedelta(minutes=interval_minutes)
        
        while current_time < end_dt:
            next_time = min(current_time + interval_delta, end_dt)
            intervals.append({
                'start': current_time,
                'end': next_time,
                'duration_minutes': (next_time - current_time).total_seconds() / 60
            })
            current_time = next_time
        
        return intervals
    
    def validate_time_sequence(self, times: list) -> bool:
        """
        التحقق من تسلسل الأوقات
        
        Args:
            times: قائمة بالأوقات
            
        Returns:
            bool: True إذا كانت الأوقات متسلسلة بشكل صحيح
        """
        normalized_times = [self.normalize_datetime(t) for t in times]
        
        for i in range(1, len(normalized_times)):
            if normalized_times[i] <= normalized_times[i-1]:
                return False
        
        return True
    
    def get_business_hours_duration(self, start_time: Union[str, datetime], 
                                   end_time: Union[str, datetime],
                                   work_start_hour: int = 8,
                                   work_end_hour: int = 17) -> Decimal:
        """
        حساب ساعات العمل الفعلية فقط
        
        Args:
            start_time: وقت البداية
            end_time: وقت النهاية
            work_start_hour: ساعة بداية العمل (افتراضي: 8)
            work_end_hour: ساعة نهاية العمل (افتراضي: 17)
            
        Returns:
            Decimal: ساعات العمل الفعلية
        """
        start_dt = self.normalize_datetime(start_time)
        end_dt = self.normalize_datetime(end_time)
        
        total_work_hours = Decimal('0')
        current_date = start_dt.date()
        
        while current_date <= end_dt.date():
            # تحديد بداية ونهاية يوم العمل
            work_start = self.local_tz.localize(
                datetime.combine(current_date, datetime.min.time().replace(hour=work_start_hour))
            )
            work_end = self.local_tz.localize(
                datetime.combine(current_date, datetime.min.time().replace(hour=work_end_hour))
            )
            
            # تحديد الفترة الفعلية للعمل في هذا اليوم
            day_start = max(start_dt, work_start)
            day_end = min(end_dt, work_end)
            
            # إضافة ساعات العمل إذا كانت هناك فترة عمل فعلية
            if day_start < day_end:
                day_duration = (day_end - day_start).total_seconds() / 3600
                total_work_hours += Decimal(str(day_duration))
            
            current_date += timedelta(days=1)
        
        return total_work_hours.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

# إنشاء مثيل عام للاستخدام
time_calculator = PrecisionTimeCalculator()

# دوال مساعدة للاستخدام السريع
def get_current_time_precise(use_utc: bool = False) -> datetime:
    """الحصول على الوقت الحالي بدقة عالية"""
    return time_calculator.get_current_time(use_utc)

def calculate_duration_precise(start_time: Union[str, datetime], 
                             end_time: Union[str, datetime] = None) -> dict:
    """حساب المدة بدقة عالية وإرجاع النتائج في قاموس"""
    seconds, minutes, hours, days = time_calculator.calculate_duration(start_time, end_time)
    
    return {
        'seconds': float(seconds),
        'minutes': float(minutes),
        'hours': float(hours),
        'days': float(days),
        'formatted': time_calculator.format_duration(seconds)
    }

def calculate_exposure_precise(dose_rate: float, start_time: Union[str, datetime], 
                             end_time: Union[str, datetime] = None) -> dict:
    """حساب التعرض الإشعاعي بدقة عالية"""
    _, _, hours, _ = time_calculator.calculate_duration(start_time, end_time)
    exposure = time_calculator.calculate_precise_exposure(dose_rate, hours)
    
    return {
        'duration_hours': float(hours),
        'dose_rate': dose_rate,
        'total_exposure': float(exposure),
        'exposure_precise': str(exposure)
    }

"""
Radiation Data Cache Manager
إدارة التخزين المؤقت لبيانات الإشعاع المستقبلة من ESP32
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

# إعداد السجل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RadiationReading:
    """فئة تمثل قراءة إشعاع واحدة"""
    def __init__(self, cpm: int, source_power: float, absorbed_dose_rate: float,
                 total_absorbed_dose: float, sensor_id: str = "ESP32_001"):
        self.cpm = cpm
        self.source_power = source_power
        self.absorbed_dose_rate = absorbed_dose_rate
        self.total_absorbed_dose = total_absorbed_dose
        self.sensor_id = sensor_id
        self.timestamp = datetime.now()
        self.saved_to_db = False  # هل تم حفظها في قاعدة البيانات؟
        self.save_attempts = 0    # عدد محاولات الحفظ

    def to_dict(self) -> Dict:
        """تحويل القراءة إلى قاموس"""
        return {
            "cpm": self.cpm,
            "source_power": self.source_power,
            "absorbed_dose_rate": self.absorbed_dose_rate,
            "total_absorbed_dose": self.total_absorbed_dose,
            "sensor_id": self.sensor_id,
            "timestamp": self.timestamp.isoformat(),
            "saved_to_db": self.saved_to_db
        }

    def to_db_format(self) -> Dict:
        """تحويل القراءة إلى تنسيق قاعدة البيانات"""
        return {
            "sensor_id": self.sensor_id,
            "cpm": self.cpm,
            "source_power": self.source_power,
            "absorbed_dose_rate": self.absorbed_dose_rate,
            "total_absorbed_dose": self.total_absorbed_dose,
            "timestamp": self.timestamp
        }

class RadiationCache:
    """إدارة التخزين المؤقت لبيانات الإشعاع"""

    def __init__(self, max_readings: int = 100, cleanup_interval: int = 300):
        self.max_readings = max_readings
        self.cleanup_interval = cleanup_interval  # ثواني
        self.readings: List[RadiationReading] = []
        self.lock = threading.Lock()
        self.last_cleanup = datetime.now()

        # بدء خيط التنظيف التلقائي
        self.cleanup_thread = threading.Thread(target=self._auto_cleanup, daemon=True)
        self.cleanup_thread.start()

        logger.info(f"✅ تم إنشاء RadiationCache بحد أقصى {max_readings} قراءة")

    def add_reading(self, cpm: int, source_power: float, absorbed_dose_rate: float,
                   total_absorbed_dose: float, sensor_id: str = "ESP32_001") -> RadiationReading:
        """إضافة قراءة جديدة إلى التخزين المؤقت"""
        with self.lock:
            reading = RadiationReading(cpm, source_power, absorbed_dose_rate,
                                     total_absorbed_dose, sensor_id)

            self.readings.append(reading)

            # الحفاظ على الحد الأقصى
            if len(self.readings) > self.max_readings:
                # إزالة أقدم القراءات المحفوظة في قاعدة البيانات
                self.readings = [r for r in self.readings if not r.saved_to_db][-self.max_readings:]

            logger.info(f"📊 تم إضافة قراءة جديدة: CPM={cpm}, Total Dose={total_absorbed_dose:.5f} μSv")
            return reading

    def get_latest_reading(self) -> Optional[RadiationReading]:
        """الحصول على أحدث قراءة"""
        with self.lock:
            return self.readings[-1] if self.readings else None

    def get_readings_since(self, since_timestamp: datetime) -> List[RadiationReading]:
        """الحصول على القراءات من وقت معين"""
        with self.lock:
            return [r for r in self.readings if r.timestamp >= since_timestamp]

    def get_unsaved_readings(self) -> List[RadiationReading]:
        """الحصول على القراءات غير المحفوظة في قاعدة البيانات"""
        with self.lock:
            return [r for r in self.readings if not r.saved_to_db]

    def mark_as_saved(self, reading: RadiationReading):
        """تحديد قراءة كمحفوظة في قاعدة البيانات"""
        with self.lock:
            reading.saved_to_db = True
            reading.save_attempts = 0
            logger.info(f"✅ تم تحديد القراءة كمحفوظة: {reading.timestamp}")

    def mark_save_failed(self, reading: RadiationReading):
        """تحديد فشل حفظ قراءة"""
        with self.lock:
            reading.save_attempts += 1
            logger.warning(f"❌ فشل حفظ القراءة (محاولة {reading.save_attempts}): {reading.timestamp}")

    def get_cache_stats(self) -> Dict:
        """الحصول على إحصائيات التخزين المؤقت"""
        with self.lock:
            total_readings = len(self.readings)
            saved_readings = len([r for r in self.readings if r.saved_to_db])
            unsaved_readings = total_readings - saved_readings

            return {
                "total_readings": total_readings,
                "saved_readings": saved_readings,
                "unsaved_readings": unsaved_readings,
                "oldest_timestamp": self.readings[0].timestamp if self.readings else None,
                "newest_timestamp": self.readings[-1].timestamp if self.readings else None
            }

    def get_statistics(self) -> Dict:
        """اسم بديل لدالة get_cache_stats للتوافق مع الاختبارات"""
        return self.get_cache_stats()

    def _auto_cleanup(self):
        """تنظيف تلقائي للقراءات القديمة"""
        while True:
            time.sleep(self.cleanup_interval)

            try:
                with self.lock:
                    now = datetime.now()

                    # إزالة القراءات المحفوظة التي مضى عليها أكثر من ساعة
                    cutoff_time = now - timedelta(hours=1)
                    old_saved_readings = [r for r in self.readings
                                        if r.saved_to_db and r.timestamp < cutoff_time]

                    if old_saved_readings:
                        for reading in old_saved_readings:
                            self.readings.remove(reading)

                        logger.info(f"🧹 تم تنظيف {len(old_saved_readings)} قراءة قديمة محفوظة")

                    self.last_cleanup = now

            except Exception as e:
                logger.error(f"❌ خطأ في التنظيف التلقائي: {e}")

    def clear_cache(self):
        """مسح جميع القراءات من التخزين المؤقت"""
        with self.lock:
            cleared_count = len(self.readings)
            self.readings.clear()
            logger.info(f"🗑️ تم مسح {cleared_count} قراءة من التخزين المؤقت")

# إنشاء كائن عام للتخزين المؤقت
radiation_cache = RadiationCache()

def get_radiation_cache() -> RadiationCache:
    """الحصول على كائن التخزين المؤقت العام"""
    return radiation_cache
/*
 * ════════════════════════════════════════════════════════════════════════════
 * RadMeter - ESP32 Geiger Counter with Dual Tube Support
 * ════════════════════════════════════════════════════════════════════════════
 * 
 * يدعم هذا الكود أنبوبي Geiger:
 * - SBM-20 (روسي): معامل 0.00812 μSv/h per CPM
 * - J305 (صيني):  معامل 0.00332 μSv/h per CPM
 * 
 * المميزات:
 * ✓ التبديل التلقائي بين الأنبوبين
 * ✓ حفظ الإعداد في الذاكرة الدائمة (EEPROM)
 * ✓ WebServer لاستقبال أوامر التحكم
 * ✓ إرسال البيانات للخادم Flask
 * ✓ حسابات دقيقة للجرعة الممتصة
 * 
 * ════════════════════════════════════════════════════════════════════════════
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <Preferences.h>
#include <ArduinoJson.h>  // تأكد من تثبيت مكتبة ArduinoJson

// ═══════════════════════════════════════════════════════════════════════════
// إعدادات الواي فاي
// ═══════════════════════════════════════════════════════════════════════════
const char* ssid = "MSR-2";
const char* password = "[REDACTED:password]";  // ضع كلمة المرور الخاصة بك

// ═══════════════════════════════════════════════════════════════════════════
// عناوين الخوادم
// ═══════════════════════════════════════════════════════════════════════════
const char* serverUrl = "http://192.168.0.190:5000/data";            // إرسال البيانات
const char* settingsUrl = "http://192.168.0.190:5000/api/get_tube_settings";  // جلب الإعدادات

// ═══════════════════════════════════════════════════════════════════════════
// إعدادات الأجهزة
// ═══════════════════════════════════════════════════════════════════════════
const int geigerPin = 25;  // GPIO 25 لعد نبضات Geiger
const unsigned long MEASURE_INTERVAL = 60000;  // قياس كل 60 ثانية

// ═══════════════════════════════════════════════════════════════════════════
// معاملات التحويل للأنابيب (بناءً على التحليل العلمي)
// ═══════════════════════════════════════════════════════════════════════════

// أنبوب SBM-20 (روسي - معايرة Cs-137)
const float SBM20_FACTOR_EXPOSURE = 0.00926;   // جرعة التعرض (Exposure Dose)
const float SBM20_FACTOR_ABSORBED = 0.00812;   // الجرعة الممتصة (Absorbed Dose) ⭐ موصى به

// أنبوب J305 (صيني - معايرة Co-60)
const float J305_FACTOR_EXPOSURE = 0.00378;    // جرعة التعرض (Exposure Dose)
const float J305_FACTOR_ABSORBED = 0.00332;    // الجرعة الممتصة (Absorbed Dose) ⭐ موصى به

// ملاحظة: نستخدم معامل الجرعة الممتصة (Absorbed Dose) لأنه يمثل
// التأثير الفعلي على جسم الإنسان بناءً على نموذج الجسم الوهمي (Phantom Model)

// ═══════════════════════════════════════════════════════════════════════════
// المتغيرات العامة
// ═══════════════════════════════════════════════════════════════════════════
volatile unsigned long counts = 0;           // عداد النبضات
unsigned long previousMillis = 0;
double totalAbsorbedDose = 0.0;              // الجرعة التراكمية (μSv)

// إعدادات الأنبوب الحالي
String currentTubeType = "J305";             // النوع الافتراضي
float currentFactorExposure = J305_FACTOR_EXPOSURE;
float currentFactorAbsorbed = J305_FACTOR_ABSORBED;

// ═══════════════════════════════════════════════════════════════════════════
// كائنات النظام
// ═══════════════════════════════════════════════════════════════════════════
WebServer server(80);        // خادم ويب للتحكم
Preferences preferences;     // ذاكرة دائمة لحفظ الإعدادات

// ═══════════════════════════════════════════════════════════════════════════
// دالة المقاطعة لعد النبضات
// ═══════════════════════════════════════════════════════════════════════════
void IRAM_ATTR countPulse() {
  counts++;
}

// ═══════════════════════════════════════════════════════════════════════════
// تحديث معاملات التحويل بناءً على نوع الأنبوب
// ═══════════════════════════════════════════════════════════════════════════
void updateConversionFactors() {
  if (currentTubeType == "SBM20") {
    currentFactorExposure = SBM20_FACTOR_EXPOSURE;
    currentFactorAbsorbed = SBM20_FACTOR_ABSORBED;
    Serial.println("📡 معاملات SBM-20 مُفعّلة");
  } else if (currentTubeType == "J305") {
    currentFactorExposure = J305_FACTOR_EXPOSURE;
    currentFactorAbsorbed = J305_FACTOR_ABSORBED;
    Serial.println("📡 معاملات J305 مُفعّلة");
  }
  
  Serial.printf("   - معامل التعرض: %.5f μSv/h per CPM\n", currentFactorExposure);
  Serial.printf("   - معامل الامتصاص: %.5f μSv/h per CPM\n", currentFactorAbsorbed);
}

// ═══════════════════════════════════════════════════════════════════════════
// تحميل الإعدادات من الذاكرة الدائمة
// ═══════════════════════════════════════════════════════════════════════════
void loadSettings() {
  preferences.begin("radmeter", false);  // false = read/write mode
  
  // تحميل نوع الأنبوب (افتراضي: J305)
  currentTubeType = preferences.getString("tube_type", "J305");
  
  // تحميل الجرعة التراكمية المحفوظة (اختياري)
  totalAbsorbedDose = preferences.getDouble("total_dose", 0.0);
  
  preferences.end();
  
  Serial.println("✅ تم تحميل الإعدادات من الذاكرة:");
  Serial.printf("   - نوع الأنبوب: %s\n", currentTubeType.c_str());
  Serial.printf("   - الجرعة التراكمية: %.5f μSv\n", totalAbsorbedDose);
  
  // تحديث المعاملات
  updateConversionFactors();
}

// ═══════════════════════════════════════════════════════════════════════════
// حفظ الإعدادات في الذاكرة الدائمة
// ═══════════════════════════════════════════════════════════════════════════
void saveSettings() {
  preferences.begin("radmeter", false);
  preferences.putString("tube_type", currentTubeType);
  preferences.putDouble("total_dose", totalAbsorbedDose);
  preferences.end();
  
  Serial.println("💾 تم حفظ الإعدادات في الذاكرة");
}

// ═══════════════════════════════════════════════════════════════════════════
// API: تغيير نوع الأنبوب
// POST /set_tube
// Body: {"tube": "SBM20"} أو {"tube": "J305"}
// ═══════════════════════════════════════════════════════════════════════════
void handleSetTube() {
  if (server.hasArg("plain")) {
    String body = server.arg("plain");
    Serial.println("📥 طلب تغيير الأنبوب:");
    Serial.println(body);
    
    // تحليل JSON
    StaticJsonDocument<200> doc;
    DeserializationError error = deserializeJson(doc, body);
    
    if (error) {
      Serial.println("❌ خطأ في تحليل JSON");
      server.send(400, "application/json", 
                 "{\"success\":false,\"error\":\"Invalid JSON\"}");
      return;
    }
    
    String newTube = doc["tube"].as<String>();
    
    // التحقق من صحة النوع
    if (newTube == "SBM20" || newTube == "J305") {
      currentTubeType = newTube;
      updateConversionFactors();
      saveSettings();
      
      // إرسال استجابة نجاح
      String response = "{\"success\":true,\"tube\":\"" + currentTubeType + 
                       "\",\"factor_absorbed\":" + String(currentFactorAbsorbed, 5) + 
                       ",\"factor_exposure\":" + String(currentFactorExposure, 5) + "}";
      
      server.send(200, "application/json", response);
      
      Serial.println("✅ تم التبديل إلى أنبوب: " + currentTubeType);
    } else {
      server.send(400, "application/json", 
                 "{\"success\":false,\"error\":\"Invalid tube type. Use SBM20 or J305\"}");
      Serial.println("❌ نوع أنبوب غير صحيح: " + newTube);
    }
  } else {
    server.send(400, "application/json", 
               "{\"success\":false,\"error\":\"No data received\"}");
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// API: الحصول على نوع الأنبوب الحالي
// GET /get_tube
// ═══════════════════════════════════════════════════════════════════════════
void handleGetTube() {
  String response = "{\"success\":true,\"tube\":\"" + currentTubeType + 
                   "\",\"factor_absorbed\":" + String(currentFactorAbsorbed, 5) + 
                   ",\"factor_exposure\":" + String(currentFactorExposure, 5) + 
                   ",\"total_dose\":" + String(totalAbsorbedDose, 5) + "}";
  
  server.send(200, "application/json", response);
}

// ═══════════════════════════════════════════════════════════════════════════
// API: إعادة تعيين الجرعة التراكمية
// POST /reset_dose
// ═══════════════════════════════════════════════════════════════════════════
void handleResetDose() {
  totalAbsorbedDose = 0.0;
  saveSettings();
  
  server.send(200, "application/json", 
             "{\"success\":true,\"message\":\"Total dose reset to 0\"}");
  
  Serial.println("🔄 تم إعادة تعيين الجرعة التراكمية");
}

// ═══════════════════════════════════════════════════════════════════════════
// API: الحصول على حالة النظام
// GET /status
// ═══════════════════════════════════════════════════════════════════════════
void handleStatus() {
  String response = "{";
  response += "\"success\":true,";
  response += "\"tube\":\"" + currentTubeType + "\",";
  response += "\"wifi_rssi\":" + String(WiFi.RSSI()) + ",";
  response += "\"uptime\":" + String(millis() / 1000) + ",";
  response += "\"total_dose\":" + String(totalAbsorbedDose, 5) + ",";
  response += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  response += "}";
  
  server.send(200, "application/json", response);
}

// ═══════════════════════════════════════════════════════════════════════════
// جلب إعدادات نوع الأنبوب من الخادم
// يتم استدعاؤها بعد كل إرسال للبيانات
// ═══════════════════════════════════════════════════════════════════════════
void fetchTubeSettings() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("⚠️  الواي فاي غير متصل - لا يمكن جلب الإعدادات");
    return;
  }
  
  HTTPClient http;
  http.begin(settingsUrl);
  http.setTimeout(3000);  // انتظار 3 ثواني كحد أقصى
  
  int httpResponseCode = http.GET();
  
  if (httpResponseCode == 200) {
    String payload = http.getString();
    Serial.println("📥 استلام إعدادات من الخادم:");
    Serial.println(payload);
    
    // تحليل JSON
    StaticJsonDocument<300> doc;
    DeserializationError error = deserializeJson(doc, payload);
    
    if (!error) {
      bool success = doc["success"];
      
      if (success) {
        String serverTubeType = doc["tube_type"].as<String>();
        
        // التحقق من تغيير نوع الأنبوب
        if (serverTubeType != currentTubeType) {
          Serial.println("🔄 تغيير في نوع الأنبوب:");
          Serial.printf("   من: %s\n", currentTubeType.c_str());
          Serial.printf("   إلى: %s\n", serverTubeType.c_str());
          
          // تطبيق التغيير
          currentTubeType = serverTubeType;
          updateConversionFactors();
          saveSettings();
          
          Serial.println("✅ تم تطبيق التغيير بنجاح!");
        } else {
          Serial.println("✓ نوع الأنبوب لم يتغير: " + currentTubeType);
        }
      } else {
        Serial.println("⚠️  الخادم لم يرجع نجاح");
      }
    } else {
      Serial.println("❌ خطأ في تحليل JSON من الخادم");
    }
  } else if (httpResponseCode > 0) {
    Serial.printf("⚠️  استجابة غير متوقعة من الخادم: %d\n", httpResponseCode);
  } else {
    // الخادم غير متاح - لا بأس، نستمر بالإعدادات الحالية
    // Serial.printf("⚠️  لا يمكن الاتصال بالخادم: %d\n", httpResponseCode);
  }
  
  http.end();
}

// ═══════════════════════════════════════════════════════════════════════════
// Setup - التهيئة الأولية
// ═══════════════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  Serial.println("\n\n");
  Serial.println("════════════════════════════════════════════════════════");
  Serial.println("   RadMeter - ESP32 Geiger Counter v2.0");
  Serial.println("   Dual Tube Support: SBM-20 & J305");
  Serial.println("════════════════════════════════════════════════════════");
  
  // إعداد مدخل Geiger
  pinMode(geigerPin, INPUT);
  attachInterrupt(digitalPinToInterrupt(geigerPin), countPulse, FALLING);
  Serial.println("✅ تم إعداد مدخل Geiger (GPIO 25)");
  
  // تحميل الإعدادات المحفوظة
  loadSettings();
  
  // الاتصال بالواي فاي
  Serial.print("\n📡 الاتصال بالواي فاي");
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ تم الاتصال بالواي فاي بنجاح!");
    Serial.print("   IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("   Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println("\n❌ فشل الاتصال بالواي فاي!");
    Serial.println("   سيتم المحاولة مرة أخرى في Loop");
  }
  
  // إعداد خادم الويب
  server.on("/set_tube", HTTP_POST, handleSetTube);
  server.on("/get_tube", HTTP_GET, handleGetTube);
  server.on("/reset_dose", HTTP_POST, handleResetDose);
  server.on("/status", HTTP_GET, handleStatus);
  
  server.begin();
  Serial.println("✅ خادم الويب يعمل على المنفذ 80");
  
  Serial.println("\n════════════════════════════════════════════════════════");
  Serial.println("   النظام جاهز!");
  Serial.println("════════════════════════════════════════════════════════\n");
  
  previousMillis = millis();
}

// ═══════════════════════════════════════════════════════════════════════════
// Loop - الحلقة الرئيسية
// ═══════════════════════════════════════════════════════════════════════════
void loop() {
  // معالجة طلبات خادم الويب
  server.handleClient();
  
  // التحقق من وقت القياس
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= MEASURE_INTERVAL) {
    previousMillis = currentMillis;
    
    // ═══════════════════════════════════════════════════════════════════════
    // 1️⃣ حساب CPM
    // ═══════════════════════════════════════════════════════════════════════
    unsigned long cpm = counts;
    counts = 0;  // إعادة تعيين العداد
    
    // ═══════════════════════════════════════════════════════════════════════
    // 2️⃣ حساب معدلات الجرعة (μSv/h)
    // ═══════════════════════════════════════════════════════════════════════
    double sourcePower = cpm * currentFactorExposure;      // جرعة التعرض
    double absorbedDoseRate = cpm * currentFactorAbsorbed; // معدل الجرعة الممتصة
    
    // ═══════════════════════════════════════════════════════════════════════
    // 3️⃣ حساب الجرعة التراكمية
    // ═══════════════════════════════════════════════════════════════════════
    // معدل الجرعة بوحدة μSv/h، نحتاج لحساب الجرعة في دقيقة واحدة
    // الجرعة في دقيقة = (معدل الجرعة بالساعة) / 60
    double absorbedDosePerMinute = absorbedDoseRate / 60.0;  // μSv/min
    totalAbsorbedDose += absorbedDosePerMinute;               // μSv إجمالي
    
    // حفظ الجرعة التراكمية كل 10 قياسات (كل 10 دقائق)
    static int saveCounter = 0;
    if (++saveCounter >= 10) {
      saveSettings();
      saveCounter = 0;
    }
    
    // ═══════════════════════════════════════════════════════════════════════
    // 4️⃣ طباعة القياسات
    // ═══════════════════════════════════════════════════════════════════════
    Serial.println("\n════════════════ MEASUREMENT ════════════════");
    Serial.printf("🔬 أنبوب Geiger:           %s\n", currentTubeType.c_str());
    Serial.printf("📊 CPM:                     %lu\n", cpm);
    Serial.printf("☢️  جرعة التعرض:           %.5f μSv/h\n", sourcePower);
    Serial.printf("💉 معدل الجرعة الممتصة:    %.5f μSv/h\n", absorbedDoseRate);
    Serial.printf("📈 الجرعة لهذه الدقيقة:    %.5f μSv\n", absorbedDosePerMinute);
    Serial.printf("📊 الجرعة التراكمية:       %.5f μSv\n", totalAbsorbedDose);
    Serial.println("═════════════════════════════════════════════");
    
    // ═══════════════════════════════════════════════════════════════════════
    // 5️⃣ إرسال البيانات للخادم
    // ═══════════════════════════════════════════════════════════════════════
    if (WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      http.begin(serverUrl);
      http.addHeader("Content-Type", "application/json");
      
      // بناء JSON بنفس التنسيق المتوقع من الخادم
      String jsonData = "{";
      jsonData += "\"cpm\":" + String(cpm) + ",";
      jsonData += "\"source_power\":" + String(sourcePower, 5) + ",";
      jsonData += "\"absorbed_dose\":" + String(absorbedDoseRate, 5) + ",";
      jsonData += "\"total_dose\":" + String(totalAbsorbedDose, 5);
      jsonData += "}";
      
      // إرسال POST
      int httpResponseCode = http.POST(jsonData);
      
      if (httpResponseCode > 0) {
        Serial.printf("✅ تم إرسال البيانات للخادم - استجابة: %d\n", httpResponseCode);
        String response = http.getString();
        Serial.println("   الاستجابة: " + response);
      } else {
        Serial.printf("❌ خطأ في إرسال البيانات: %d\n", httpResponseCode);
        Serial.println("   السبب: " + http.errorToString(httpResponseCode));
      }
      
      http.end();
      
      // ═══════════════════════════════════════════════════════════════════
      // 6️⃣ جلب إعدادات نوع الأنبوب من الخادم
      // ═══════════════════════════════════════════════════════════════════
      delay(500);  // انتظار قصير بين الطلبات
      fetchTubeSettings();
      
    } else {
      Serial.println("⚠️  الواي فاي غير متصل - لم يتم إرسال البيانات");
      // محاولة إعادة الاتصال
      WiFi.reconnect();
    }
    
    Serial.println();
  }
}

/*
 * ════════════════════════════════════════════════════════════════════════════
 * ملاحظات التثبيت والاستخدام:
 * ════════════════════════════════════════════════════════════════════════════
 * 
 * 1. المكتبات المطلوبة:
 *    - WiFi (مدمجة في ESP32)
 *    - HTTPClient (مدمجة في ESP32)
 *    - WebServer (مدمجة في ESP32)
 *    - Preferences (مدمجة في ESP32)
 *    - ArduinoJson (يجب تثبيتها من Library Manager)
 * 
 * 2. إعداد الخادم:
 *    - عدّل serverUrl في السطر 34 (عنوان إرسال البيانات)
 *    - عدّل settingsUrl في السطر 35 (عنوان جلب الإعدادات)
 *    - يجب أن يكونا نفس الخادم، فقط المسارات مختلفة
 * 
 * 3. آلية العمل:
 *    ┌─────────────────────────────────────────────┐
 *    │ كل 60 ثانية:                               │
 *    │  1. قراءة CPM وحساب الجرعة                │
 *    │  2. إرسال البيانات إلى /data (POST)       │
 *    │  3. جلب الإعدادات من /api/get_tube_settings│
 *    │  4. تطبيق التغيير إذا لزم الأمر            │
 *    └─────────────────────────────────────────────┘
 * 
 * 4. API Endpoints المحلية (WebServer على ESP32):
 *    POST /set_tube       - تغيير نوع الأنبوب محلياً
 *    GET  /get_tube       - الحصول على نوع الأنبوب الحالي
 *    POST /reset_dose     - إعادة تعيين الجرعة التراكمية
 *    GET  /status         - حالة النظام
 * 
 * 5. أمثلة الاستخدام (التحكم المحلي):
 *    curl -X POST http://ESP_IP/set_tube -H "Content-Type: application/json" -d '{"tube":"SBM20"}'
 *    curl http://ESP_IP/get_tube
 *    curl -X POST http://ESP_IP/reset_dose
 *    curl http://ESP_IP/status
 * 
 * 6. معاملات التحويل المستخدمة:
 *    SBM-20: 0.00812 μSv/h per CPM (الجرعة الممتصة - موصى به)
 *    J305:   0.00332 μSv/h per CPM (الجرعة الممتصة - موصى به)
 * 
 * 7. الحدود المراقبة (معايير ICRP-103 & IAEA):
 *    ساعياً:  آمن ≤ 0.3 | تحذير > 2.38 | خطر ≥ 2.38 μSv/h
 *    يومياً:  الحد 54.8 μSv | تحذير عند 80% | مراقبة عند 50%
 *    سنوياً:  الحد 20 mSv (20000 μSv) | تحذير عند 80%
 * 
 * ════════════════════════════════════════════════════════════════════════════
 */

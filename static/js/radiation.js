// نظام إدارة بيانات الإشعاع
class RadiationMonitor {
    constructor() {
        this.isConnected = false;
        this.lastUpdate = null;
        this.dataSource = 'unknown'; // 'cache', 'database', 'default'
        this.currentData = {
            cpm: 0,
            sourcePower: 0,
            absorbedDose: 0,
            totalDose: 0
        };

        // بدء المراقبة
        this.init();

        // تحديث ملخص التعرض
        this.updateExposureSummary();
    }

    init() {
        console.log('🔄 بدء تشغيل نظام مراقبة الإشعاع...');

        // تحديث البيانات فوراً
        console.log('🚀 تحديث البيانات الأولي...');
        this.updateData();

        // تحديث البيانات كل 10 ثوانٍ للاختبار (بدلاً من دقيقة)
        console.log('⏰ إعداد تحديث البيانات كل 10 ثوانٍ...');
        setInterval(() => {
            console.log('⏰ تحديث دوري للبيانات...');
            this.updateData();
        }, 10000);

        // تحديث ملخص التعرض كل 5 دقائق
        setInterval(() => this.updateExposureSummary(), 300000);

        // فحص الاتصال كل 30 ثانية
        // تم حذف قسم حالة النظام - تعطيل فحص الاتصال وحالة النظام
        // this.checkConnection();
        // setInterval(() => this.checkConnection(), 30000);

        // فحص حالة النظام كل 60 ثانية
        // this.checkSystemStatus();
        // setInterval(() => this.checkSystemStatus(), 60000);

        // تحديث الوقت كل ثانية
        // setInterval(() => this.updateLastUpdateTime(), 1000);

        console.log('✅ تم إعداد جميع المؤقتات');
    }

    async updateData() {
        try {
            console.log('📡 جاري جلب بيانات الإشعاع...');

            // إضافة timestamp لمنع التخزين المؤقت
            const timestamp = new Date().getTime();
            const url = `/api/radiation_data?t=${timestamp}`;
            console.log('🌐 URL:', url);

            const response = await fetch(url, {
                cache: 'no-cache',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });

            console.log('📡 Response status:', response.status);
            console.log('📡 Response ok:', response.ok);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('📥 Raw response data:', data);

            if (data.success) {
                console.log('📥 تم استلام البيانات من الخادم:', data);

                this.currentData = data.data;
                this.lastUpdate = new Date();
                this.isConnected = true;

                // تحديث معلومات المصدر
                this.dataSource = data.data.source || 'unknown';

                console.log('🔄 بدء تحديث الواجهة...');
                this.updateDisplay();
                this.updateSafetyLevel();
                this.updateDataSourceInfo();

                console.log('✅ تم تحديث البيانات بنجاح:', this.currentData);
                console.log('📊 مصدر البيانات:', this.dataSource);
            } else {
                console.error('❌ فشل في جلب البيانات:', data);
                throw new Error(data.message || 'فشل في جلب البيانات');
            }

        } catch (error) {
            console.error('❌ خطأ في جلب البيانات:', error);
            this.isConnected = false;
            // this.updateConnectionStatus(); // تم حذف قسم حالة النظام
        }
    }

    updateDisplay() {
        console.log('🎨 بدء تحديث الواجهة مع البيانات:', this.currentData);

        // تحديث CPM
        this.updateValueDisplay('cpm', this.currentData.cpm, '');

        // تحديث Source Power
        this.updateValueDisplay('source-power', this.currentData.sourcePower.toFixed(5), 'μSv/h');

        // تحديث Absorbed Dose
        this.updateValueDisplay('absorbed-dose', this.currentData.absorbedDose.toFixed(5), 'μSv/h');

        // تحديث Total Dose
        this.updateValueDisplay('total-dose', this.currentData.totalDose.toFixed(5), 'μSv');

        // تحديث حالة الاتصال - تم حذف قسم حالة النظام
        // this.updateConnectionStatus();

        console.log('✅ تم الانتهاء من تحديث الواجهة');
    }

    updateValueDisplay(type, value, unit) {
        console.log(`🔄 تحديث ${type}: ${value} ${unit || ''}`);

        const valueElement = document.getElementById(`${type}-value`);
        const statusElement = document.getElementById(`${type}-status`);

        if (valueElement) {
            valueElement.textContent = value;
            console.log(`✅ تم تحديث ${type}-value إلى: ${value}`);

            // إضافة تأثيرات بصرية حسب القيمة
            this.applyValueEffects(valueElement, type, parseFloat(value));
        } else {
            console.error(`❌ لم يتم العثور على العنصر: ${type}-value`);
        }

        if (statusElement) {
            const level = this.getRadiationLevel(type, parseFloat(value));
            statusElement.innerHTML = this.getStatusBadge(level);
        } else {
            console.error(`❌ لم يتم العثور على العنصر: ${type}-status`);
        }
    }

    applyValueEffects(element, type, value) {
        // إزالة الكلاسات السابقة
        element.classList.remove('critical-value', 'warning-value');
        
        const level = this.getRadiationLevel(type, value);
        
        if (level === 'danger') {
            element.classList.add('critical-value');
        } else if (level === 'warning' || level === 'caution') {
            element.classList.add('warning-value');
        }
    }

    getRadiationLevel(type, value) {
        // تحديد مستوى الخطر حسب النوع والقيمة (محدث وفقاً للمعايير الدولية)
        switch (type) {
            case 'cpm':
                // CPM limits (تقريبية - تعتمد على نوع الكاشف)
                if (value > 200) return 'danger';
                if (value > 100) return 'warning';
                if (value > 50) return 'caution';
                return 'safe';

            case 'source-power':
            case 'absorbed-dose':
                // معدل الجرعة (μSv/h) - الحدود الجديدة المبسطة
                if (value >= 2.38) return 'danger';   // خطر: >= 2.38
                if (value > 0.3) return 'warning';    // تحذير: > 0.3 و < 2.38
                return 'safe';                        // آمن: <= 0.3

            case 'total-dose':
                // الجرعة الإجمالية (μSv)
                if (value > 54.8) return 'danger';    // تجاوز الحد اليومي
                if (value > 41.1) return 'warning';   // 75% من الحد اليومي
                if (value > 27.4) return 'caution';   // 50% من الحد اليومي
                return 'safe';

            default:
                return 'safe';
        }
    }

    getStatusBadge(level) {
        const badges = {
            safe: '<span class="badge bg-success">آمن</span>',
            caution: '<span class="badge bg-info">انتباه</span>',
            warning: '<span class="badge bg-warning">تحذير</span>',
            danger: '<span class="badge bg-danger">خطر</span>'
        };
        
        return badges[level] || badges.safe;
    }

    updateSafetyLevel() {
        // تم حذف قسم حالة النظام - تعطيل تحديث مستوى الأمان
        // const safetyIcon = document.getElementById('safety-icon');
        // const safetyLevel = document.getElementById('safety-level');

        // تحديد المستوى العام للأمان
        const levels = [
            this.getRadiationLevel('cpm', this.currentData.cpm),
            this.getRadiationLevel('source-power', this.currentData.sourcePower),
            this.getRadiationLevel('absorbed-dose', this.currentData.absorbedDose),
            this.getRadiationLevel('total-dose', this.currentData.totalDose)
        ];

        const overallLevel = this.getOverallSafetyLevel(levels);

        // if (safetyIcon && safetyLevel) {
        //     const config = this.getSafetyConfig(overallLevel);
        //     safetyIcon.className = `fas fa-shield-alt fa-2x mb-2 ${config.iconClass}`;
        //     safetyLevel.innerHTML = config.badge;
        // }
    }

    getOverallSafetyLevel(levels) {
        if (levels.includes('danger')) return 'danger';
        if (levels.includes('warning')) return 'warning';
        if (levels.includes('caution')) return 'caution';
        return 'safe';
    }

    getSafetyConfig(level) {
        const configs = {
            safe: {
                iconClass: 'safety-safe',
                badge: '<span class="badge bg-success">مستوى آمن</span>'
            },
            caution: {
                iconClass: 'safety-caution',
                badge: '<span class="badge bg-info">يتطلب انتباه</span>'
            },
            warning: {
                iconClass: 'safety-warning',
                badge: '<span class="badge bg-warning">مستوى تحذيري</span>'
            },
            danger: {
                iconClass: 'safety-danger',
                badge: '<span class="badge bg-danger">مستوى خطر</span>'
            }
        };
        
        return configs[level] || configs.safe;
    }

    async checkConnection() {
        // تم حذف قسم حالة النظام - تعطيل فحص الاتصال
        // try {
        //     const response = await fetch('/api/system_status');
        //     this.isConnected = response.ok;
        // } catch (error) {
        //     this.isConnected = false;
        // }

        // this.updateConnectionStatus();
    }

    async checkSystemStatus() {
        // تم حذف قسم حالة النظام - تعطيل فحص حالة النظام
        // try {
        //     const response = await fetch('/api/system_status');
        //     if (!response.ok) {
        //         throw new Error(`HTTP error! status: ${response.status}`);
        //     }

        //     const data = await response.json();
        //     if (data.success) {
        //         this.updateSystemStatusDisplay(data);
        //     }
        // } catch (error) {
        //     console.error('❌ خطأ في جلب حالة النظام:', error);
        // }
    }

    updateSystemStatusDisplay(systemData) {
        // تم حذف قسم حالة النظام - تعطيل تحديث حالة قاعدة البيانات
        // const dbStatusElement = document.getElementById('database-status');
        // if (dbStatusElement && systemData.database) {
        //     const dbConfig = this.getDatabaseStatusConfig(systemData.database);
        //     dbStatusElement.innerHTML = dbConfig.badge;
        //     dbStatusElement.className = `badge ${dbConfig.class}`;
        // }

        // تم حذف قسم معلومات التخزين المؤقت - تعطيل التحديث
        // const cacheInfoElement = document.getElementById('cache-info');
        // if (cacheInfoElement && systemData.cache) {
        //     const cache = systemData.cache;
        //     cacheInfoElement.innerHTML = `
        //         <small>
        //             <i class="fas fa-memory me-1"></i>
        //             ${cache.total_readings} قراءة (${cache.saved_readings} محفوظة)
        //         </small>
        //     `;
        // }

        console.log('📊 تم تحديث معلومات النظام:', systemData);
    }

    getDatabaseStatusConfig(database) {
        const configs = {
            connected: {
                badge: '<i class="fas fa-check-circle me-1"></i>متصلة',
                class: 'bg-success'
            },
            disconnected: {
                badge: '<i class="fas fa-times-circle me-1"></i>غير متصلة',
                class: 'bg-danger'
            },
            error: {
                badge: '<i class="fas fa-exclamation-triangle me-1"></i>خطأ',
                class: 'bg-warning'
            },
            unknown: {
                badge: '<i class="fas fa-question me-1"></i>غير معروف',
                class: 'bg-secondary'
            }
        };

        return configs[database.status] || configs.unknown;
    }

    updateConnectionStatus() {
        // تم حذف قسم حالة النظام - تعطيل تحديث حالة الاتصال
        // const connectionIcon = document.getElementById('connection-icon');
        // const connectionStatus = document.getElementById('connection-status');

        // if (connectionIcon && connectionStatus) {
        //     if (this.isConnected) {
        //         connectionIcon.className = 'fas fa-wifi fa-2x mb-2 text-success';
        //         connectionStatus.innerHTML = '<span class="badge bg-success">متصل</span>';
        //     } else {
        //         connectionIcon.className = 'fas fa-wifi fa-2x mb-2 text-danger';
        //         connectionStatus.innerHTML = '<span class="badge bg-danger">غير متصل</span>';
        //     }
        // }
    }

    updateDataSourceInfo() {
        // تم حذف قسم حالة النظام - تعطيل تحديث معلومات مصدر البيانات
        // const sourceElement = document.getElementById('data-source-info');
        // if (sourceElement) {
        //     const sourceConfig = this.getDataSourceConfig(this.dataSource);
        //     sourceElement.innerHTML = sourceConfig.badge;
        //     sourceElement.className = `badge ${sourceConfig.class}`;
        // }
    }

    getDataSourceConfig(source) {
        const configs = {
            cache: {
                badge: '<i class="fas fa-memory me-1"></i>ذاكرة مؤقتة',
                class: 'bg-info'
            },
            database: {
                badge: '<i class="fas fa-database me-1"></i>قاعدة البيانات',
                class: 'bg-primary'
            },
            default: {
                badge: '<i class="fas fa-exclamation-triangle me-1"></i>افتراضي',
                class: 'bg-warning'
            },
            unknown: {
                badge: '<i class="fas fa-question me-1"></i>غير محدد',
                class: 'bg-secondary'
            }
        };

        return configs[source] || configs.unknown;
    }

    updateLastUpdateTime() {
        // تم حذف قسم حالة النظام - تعطيل تحديث وقت آخر تحديث
        // const lastUpdateElement = document.getElementById('last-update');

        // if (lastUpdateElement && this.lastUpdate) {
        //     const now = new Date();
        //     const diffSeconds = Math.floor((now - this.lastUpdate) / 1000);

        //     let timeText;
        //     if (diffSeconds < 60) {
        //         timeText = `${diffSeconds} ثانية`;
        //     } else if (diffSeconds < 3600) {
        //         timeText = `${Math.floor(diffSeconds / 60)} دقيقة`;
        //     } else {
        //         timeText = `${Math.floor(diffSeconds / 3600)} ساعة`;
        //     }

        //     lastUpdateElement.textContent = `منذ ${timeText}`;
        // }
    }
}

// تشغيل النظام عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 تحميل نظام مراقبة الإشعاع...');
    window.radiationMonitor = new RadiationMonitor();
});

RadiationMonitor.prototype.updateExposureSummary = async function() {
        try {
            console.log('📊 تحديث ملخص التعرض...');

            const response = await fetch('/api/unified_reports', {
                cache: 'no-cache',
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.success) {
                this.exposureSummary = data;
                this.displayExposureSummary();
            } else {
                throw new Error(data.error || 'فشل في جلب بيانات التعرض');
            }

        } catch (error) {
            console.error('❌ خطأ في تحديث ملخص التعرض:', error);
            this.displayExposureError();
        }
    }

RadiationMonitor.prototype.displayExposureSummary = function() {
        if (!this.exposureSummary) return;

        const exposureRecords = this.exposureSummary.exposure_records || [];
        const attendanceRecords = this.exposureSummary.attendance_records || [];

        // حساب الإحصائيات
        const activeEmployees = new Set(attendanceRecords.map(r => r.employee_id)).size;

        // مستوى الأمان العام
        let safetyLevel = 'آمن';
        let safetyColor = 'success';

        if (exposureRecords.length > 0) {
            const dangerCount = exposureRecords.filter(r => r.safety_status === 'خطر').length;
            const warningCount = exposureRecords.filter(r => r.safety_status === 'تحذير').length;

            if (dangerCount > 0) {
                safetyLevel = 'خطر';
                safetyColor = 'danger';
            } else if (warningCount > 0) {
                safetyLevel = 'تحذير';
                safetyColor = 'warning';
            }
        }

        // تحديث العناصر - تم حذف بطاقات الموظفين النشطين ومستوى الأمان
        // const activeEmpElement = document.getElementById('active-employees');
        // const safetyLevelElement = document.getElementById('safety-level-summary');

        // if (activeEmpElement) activeEmpElement.textContent = activeEmployees;
        // if (safetyLevelElement) safetyLevelElement.textContent = safetyLevel;

        // تحديث رسالة الحالة
        const messageElement = document.getElementById('exposure-message');
        const statusElement = document.getElementById('exposure-status-message');

        if (messageElement && statusElement) {
            if (exposureRecords.length === 0) {
                messageElement.textContent = 'لا توجد بيانات تعرض حالياً. قم بتسجيل الحضور لبدء مراقبة التعرض.';
                statusElement.className = 'alert alert-warning mt-4 mb-0';
            } else {
                messageElement.textContent = `تم تحديث البيانات بنجاح. يوجد ${exposureRecords.length} سجل تعرض.`;
                statusElement.className = `alert alert-${safetyColor} mt-4 mb-0`;
            }
        }

        console.log(`✅ تم تحديث ملخص التعرض: ${exposureRecords.length} سجل`);
    }

RadiationMonitor.prototype.displayExposureError = function() {
        // عرض رسالة خطأ - تم حذف بطاقات الموظفين النشطين ومستوى الأمان
        // const elements = [
        //     'active-employees', 'safety-level-summary'
        // ];

        // elements.forEach(id => {
        //     const element = document.getElementById(id);
        //     if (element) element.textContent = '--';
        // });

        const messageElement = document.getElementById('exposure-message');
        const statusElement = document.getElementById('exposure-status-message');

        if (messageElement && statusElement) {
            messageElement.textContent = 'خطأ في تحميل بيانات التعرض. تحقق من اتصال الخادم.';
            statusElement.className = 'alert alert-danger mt-4 mb-0';
        }
    }
}

// دالة لإعادة تحميل البيانات يدوياً
function refreshRadiationData() {
    if (window.radiationMonitor) {
        window.radiationMonitor.updateData();
        window.radiationMonitor.updateExposureSummary();
    }
}

// إنشاء كائن مراقب الإشعاع عند تحميل الصفحة (تم إزالة التكرار)
// window.radiationMonitor يتم إنشاؤه في المستمع الأول أعلاه

// دالة اختبار بسيطة
function simpleTest() {
    console.log('🧪 اختبار بسيط...');

    fetch('/api/radiation_data')
        .then(response => {
            console.log('Response status:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Response data:', data);

            if (data.success) {
                const radiationData = data.data;

                // تحديث العناصر مباشرة
                const cpmElement = document.getElementById('cpm-value');
                const sourcePowerElement = document.getElementById('source-power-value');
                const absorbedDoseElement = document.getElementById('absorbed-dose-value');
                const totalDoseElement = document.getElementById('total-dose-value');

                if (cpmElement) {
                    cpmElement.textContent = radiationData.cpm;
                    cpmElement.style.backgroundColor = '#4CAF50';
                    cpmElement.style.color = 'white';
                    console.log('✅ تم تحديث CPM');
                }

                if (sourcePowerElement) {
                    sourcePowerElement.textContent = radiationData.sourcePower.toFixed(5);
                    sourcePowerElement.style.backgroundColor = '#2196F3';
                    sourcePowerElement.style.color = 'white';
                    console.log('✅ تم تحديث Source Power');
                }

                if (absorbedDoseElement) {
                    absorbedDoseElement.textContent = radiationData.absorbedDose.toFixed(5);
                    absorbedDoseElement.style.backgroundColor = '#FF9800';
                    absorbedDoseElement.style.color = 'white';
                    console.log('✅ تم تحديث Absorbed Dose');
                }

                if (totalDoseElement) {
                    totalDoseElement.textContent = radiationData.totalDose.toFixed(5);
                    totalDoseElement.style.backgroundColor = '#F44336';
                    totalDoseElement.style.color = 'white';
                    console.log('✅ تم تحديث Total Dose');
                }
            }
        })
        .catch(error => {
            console.error('❌ خطأ في الاختبار:', error);
        });
}

// تشغيل الاختبار البسيط بعد 2 ثانية
setTimeout(simpleTest, 2000);

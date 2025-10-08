// نظام إدارة الحضور مع مراقبة التعرض للإشعاع

// دالة تسجيل الحضور مع بدء/إنهاء مراقبة التعرض
async function takeAttendanceWithExposure(checkType) {
    console.log(`🎯 بدء تسجيل ${checkType === 'check_in' ? 'الحضور' : 'الانصراف'}`);
    
    // استخدام الدالة الأصلية لتسجيل الحضور
    const attendanceResult = await takeAttendance(checkType);
    
    if (attendanceResult && attendanceResult.success) {
        const employeeId = attendanceResult.employee_id;
        
        if (checkType === 'check_in') {
            // بدء مراقبة التعرض
            await startExposureMonitoring(employeeId);
        } else if (checkType === 'check_out') {
            // إنهاء مراقبة التعرض
            await endExposureMonitoring(employeeId);
        }
    }
    
    return attendanceResult;
}

// بدء مراقبة التعرض للموظف
async function startExposureMonitoring(employeeId) {
    try {
        console.log(`🔄 بدء مراقبة التعرض للموظف: ${employeeId}`);
        
        const response = await fetch('/api/employee_exposure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'start',
                employee_id: employeeId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            // تحديد نوع العملية (جديدة أم مستأنفة)
            const isResumed = result.resumed || false;
            const actionText = isResumed ? 'استئناف' : 'بدء';
            const sessionText = isResumed ? 'الموجودة' : 'جديدة';

            console.log(`✅ تم ${actionText} مراقبة التعرض بنجاح`);

            // عرض معلومات التعرض
            showExposureInfo({
                startTime: isResumed ? result.check_in_time : new Date().toLocaleString('ar-SA'),
                initialDose: result.initial_dose,
                sessionId: result.session_id,
                resumed: isResumed
            });

            // إضافة رسالة نجاح مع توضيح نوع العملية
            const resultDiv = document.getElementById('result');
            if (resultDiv) {
                const statusIcon = isResumed ? 'fas fa-play-circle' : 'fas fa-radiation';
                const statusColor = isResumed ? 'alert-info' : 'alert-success';

                resultDiv.innerHTML += `
                    <div class="${statusColor} mt-3">
                        <i class="${statusIcon} me-2"></i>
                        تم ${actionText} مراقبة التعرض ${sessionText}
                        <br><small>الجرعة الأولية: ${result.initial_dose.toFixed(5)} μSv</small>
                        ${isResumed ? `<br><small>بدأت في: ${new Date(result.check_in_time).toLocaleString('ar-SA')}</small>` : ''}
                    </div>
                `;
            }
            
        } else {
            console.error('❌ فشل في بدء مراقبة التعرض:', result.error);
            showExposureError('فشل في بدء مراقبة التعرض: ' + result.error);
        }
        
    } catch (error) {
        console.error('❌ خطأ في بدء مراقبة التعرض:', error);
        showExposureError('خطأ في الاتصال بالخادم');
    }
}

// إنهاء مراقبة التعرض للموظف
async function endExposureMonitoring(employeeId) {
    try {
        console.log(`🔄 إنهاء مراقبة التعرض للموظف: ${employeeId}`);
        
        const response = await fetch('/api/employee_exposure', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                action: 'end',
                employee_id: employeeId
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            console.log('✅ تم إنهاء مراقبة التعرض بنجاح');
            
            // إخفاء معلومات التعرض
            hideExposureInfo();
            
            // عرض تقرير التعرض
            showExposureReport(result);

            // تحديث بيانات الداشبورد فوراً
            updateDashboardData();
            
        } else {
            console.error('❌ فشل في إنهاء مراقبة التعرض:', result.error);
            showExposureError('فشل في إنهاء مراقبة التعرض: ' + result.error);
        }
        
    } catch (error) {
        console.error('❌ خطأ في إنهاء مراقبة التعرض:', error);
        showExposureError('خطأ في الاتصال بالخادم');
    }
}

// عرض معلومات التعرض الحالي
function showExposureInfo(info) {
    const exposureInfoDiv = document.getElementById('exposure-info');
    const startTimeSpan = document.getElementById('exposure-start-time');
    const initialDoseSpan = document.getElementById('initial-dose');

    if (exposureInfoDiv && startTimeSpan && initialDoseSpan) {
        // تحديد النص المناسب حسب نوع الجلسة
        const timeLabel = info.resumed ? 'وقت البدء الأصلي' : 'وقت البدء';
        const startTimeText = info.resumed ?
            new Date(info.startTime).toLocaleString('ar-SA') :
            info.startTime;

        startTimeSpan.textContent = startTimeText;
        initialDoseSpan.textContent = info.initialDose.toFixed(5);

        // إضافة مؤشر للجلسة المستأنفة
        if (info.resumed) {
            exposureInfoDiv.classList.add('resumed-session');
            // إضافة نص توضيحي للجلسة المستأنفة
            const statusIndicator = exposureInfoDiv.querySelector('.session-status') ||
                document.createElement('small');
            statusIndicator.className = 'session-status text-info d-block mt-1';
            statusIndicator.innerHTML = '<i class="fas fa-play-circle me-1"></i>جلسة مستأنفة';

            if (!exposureInfoDiv.querySelector('.session-status')) {
                exposureInfoDiv.appendChild(statusIndicator);
            }
        } else {
            exposureInfoDiv.classList.remove('resumed-session');
            const statusIndicator = exposureInfoDiv.querySelector('.session-status');
            if (statusIndicator) {
                statusIndicator.remove();
            }
        }

        exposureInfoDiv.style.display = 'block';

        // إضافة تأثير بصري
        exposureInfoDiv.classList.add('animate__animated', 'animate__fadeIn');
    }
}

// إخفاء معلومات التعرض
function hideExposureInfo() {
    const exposureInfoDiv = document.getElementById('exposure-info');
    if (exposureInfoDiv) {
        exposureInfoDiv.style.display = 'none';
    }
}

// عرض تقرير التعرض
function showExposureReport(result) {
    const resultDiv = document.getElementById('result');
    if (resultDiv) {
        // استخدام البيانات المنسقة إذا كانت متاحة
        const durationDisplay = result.duration_formatted || `${result.duration_minutes} دقيقة`;
        const exposureDisplay = result.total_exposure ? result.total_exposure.toFixed(3) : '0.000';
        const doseRateDisplay = result.average_dose_rate ? result.average_dose_rate.toFixed(3) : '0.000';
        const safetyStatus = result.safety_status || 'غير محدد';
        const safetyPercentage = result.safety_percentage ? result.safety_percentage.toFixed(1) : '0.0';

        resultDiv.innerHTML += `
            <div class="alert alert-info mt-3">
                <h6><i class="fas fa-chart-bar me-2"></i>تقرير التعرض</h6>
                <div class="row">
                    <div class="col-md-6">
                        <small><strong>مدة التعرض:</strong> ${durationDisplay}</small><br>
                        <small><strong>إجمالي التعرض:</strong> ${exposureDisplay} μSv</small><br>
                        <small><strong>حالة الأمان:</strong> <span class="badge bg-${getSafetyBadgeColor(safetyStatus)}">${safetyStatus}</span></small>
                    </div>
                    <div class="col-md-6">
                        <small><strong>متوسط معدل الجرعة:</strong> ${doseRateDisplay} μSv/h</small><br>
                        <small><strong>نسبة الأمان:</strong> ${safetyPercentage}%</small><br>
                        <small><strong>رقم الجلسة:</strong> ${result.session_id}</small>
                        ${result.is_pregnant ? '<br><small class="text-warning"><i class="fas fa-baby me-1"></i><strong>موظفة حامل - حدود خاصة</strong></small>' : ''}
                    </div>
                </div>
                ${getSafetyAssessment(result.total_exposure, result.average_dose_rate, result.is_pregnant)}
            </div>
        `;

        console.log('📊 عرض تقرير التعرض:', {
            duration: durationDisplay,
            exposure: exposureDisplay,
            doseRate: doseRateDisplay,
            safety: safetyStatus
        });
    }
}

// تحديد لون شارة الأمان
function getSafetyBadgeColor(safetyStatus) {
    switch(safetyStatus) {
        case 'آمن': return 'success';
        case 'تحذير': return 'warning';
        case 'خطر': return 'danger';
        default: return 'secondary';
    }
}

// تقييم مستوى الأمان (محدث وفقاً للمعايير الدولية)
function getSafetyAssessment(totalExposure, averageDoseRate, isPregnant = false) {
    let safetyClass = 'success';
    let safetyIcon = 'shield-alt';
    let safetyMessage = 'مستوى آمن';

    if (isPregnant) {
        // معايير خاصة للحوامل
        if (totalExposure > 3.7 || averageDoseRate > 0.46) {
            safetyClass = 'danger';
            safetyIcon = 'exclamation-triangle';
            safetyMessage = 'خطر - تجاوز حد الحامل';
        } else if (totalExposure > 2.8 || averageDoseRate > 0.35) {
            safetyClass = 'warning';
            safetyIcon = 'exclamation-circle';
            safetyMessage = 'تحذير - اقتراب من حد الحامل';
        } else if (totalExposure > 1.8 || averageDoseRate > 0.25) {
            safetyClass = 'info';
            safetyIcon = 'info-circle';
            safetyMessage = 'مراقبة - نصف الحد للحامل';
        }
    } else {
        // معايير العاملين العاديين (محدثة)
        if (totalExposure > 54.8 || averageDoseRate > 6.8) {
            safetyClass = 'danger';
            safetyIcon = 'exclamation-triangle';
            safetyMessage = 'خطر - تجاوز الحد اليومي';
        } else if (totalExposure > 41.1 || averageDoseRate > 5.1) {
            safetyClass = 'warning';
            safetyIcon = 'exclamation-circle';
            safetyMessage = 'تحذير - اقتراب من الحد اليومي';
        } else if (totalExposure > 27.4 || averageDoseRate > 3.4) {
            safetyClass = 'info';
            safetyIcon = 'info-circle';
            safetyMessage = 'مراقبة - نصف الحد اليومي';
        }
    }
    
    return `
        <div class="mt-2 p-2 rounded" style="background-color: var(--bs-${safetyClass}-bg-subtle);">
            <small class="text-${safetyClass}">
                <i class="fas fa-${safetyIcon} me-1"></i>
                <strong>تقييم الأمان:</strong> ${safetyMessage}
            </small>
        </div>
    `;
}

// عرض خطأ في التعرض
function showExposureError(message) {
    const resultDiv = document.getElementById('result');
    if (resultDiv) {
        resultDiv.innerHTML += `
            <div class="alert alert-danger mt-3">
                <i class="fas fa-exclamation-triangle me-2"></i>
                خطأ في مراقبة التعرض: ${message}
            </div>
        `;
    }
}

// تحديث بيانات الداشبورد
function updateDashboardData() {
    try {
        // تحديث بيانات الإشعاع
        if (window.radiationMonitor) {
            console.log('🔄 تحديث بيانات الإشعاع...');
            window.radiationMonitor.updateData();

            // تحديث ملخص التعرض إذا كان متاحاً
            if (typeof window.radiationMonitor.updateExposureSummary === 'function') {
                window.radiationMonitor.updateExposureSummary();
            }
        }

        // تحديث التقارير الموحدة إذا كانت الصفحة مفتوحة
        if (window.unifiedReports) {
            console.log('🔄 تحديث الجرعات التراكمية ...');
            if (typeof window.unifiedReports.loadCumulativeDoses === 'function') {
                window.unifiedReports.loadCumulativeDoses();
            }
        }

        // بث إشعار تحديث للصفحات الأخرى (مثل التقارير الموحدة)
        try {
            localStorage.setItem('radmeter:attendance_update', Date.now().toString());
        } catch (e) {
            console.warn('تعذر بث إشعار التحديث عبر localStorage:', e);
        }

        console.log('✅ تم تحديث بيانات الداشبورد');

    } catch (error) {
        console.error('❌ خطأ في تحديث الداشبورد:', error);
    }
}

// تحديث الدالة الأصلية لتسجيل الحضور لتتضمن معرف الموظف في النتيجة
const originalTakeAttendance = window.takeAttendance;
window.takeAttendance = async function(checkType) {
    try {
        // استدعاء الدالة الأصلية
        const result = await originalTakeAttendance(checkType);
        
        // إضافة معرف الموظف إلى النتيجة إذا لم يكن موجوداً
        if (result && result.success && !result.employee_id) {
            // محاولة استخراج معرف الموظف من الرسالة أو البيانات المتاحة
            // هذا يحتاج إلى تعديل حسب بنية البيانات الفعلية
            result.employee_id = extractEmployeeIdFromResult(result);
        }
        
        return result;
        
    } catch (error) {
        console.error('❌ خطأ في تسجيل الحضور:', error);
        return { success: false, error: error.message };
    }
};

// دالة مساعدة لاستخراج معرف الموظف من النتيجة
function extractEmployeeIdFromResult(result) {
    // هذه دالة مؤقتة - يجب تعديلها حسب بنية البيانات الفعلية
    if (result.message && result.message.includes('ID:')) {
        const match = result.message.match(/ID:\s*(\w+)/);
        if (match) {
            return match[1];
        }
    }
    
    // إرجاع معرف افتراضي إذا لم يتم العثور على المعرف
    return 'unknown_employee';
}

// تحميل معلومات التعرض عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    console.log('📋 تحميل نظام إدارة الحضور مع مراقبة التعرض');
    
    // فحص وجود فترة تعرض نشطة
    checkActiveExposureSession();
});

// فحص وجود فترة تعرض نشطة
async function checkActiveExposureSession() {
    try {
        // هذه دالة للتحقق من وجود فترة تعرض نشطة
        // يمكن تطويرها لاحقاً حسب الحاجة
        console.log('🔍 فحص فترات التعرض النشطة...');
        
    } catch (error) {
        console.error('❌ خطأ في فحص فترات التعرض النشطة:', error);
    }
}

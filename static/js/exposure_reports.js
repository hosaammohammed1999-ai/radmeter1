// نظام إدارة تقارير التعرض للإشعاع

class ExposureReportsManager {
    constructor() {
        this.currentData = [];
        this.employees = [];
        this.init();
    }

    init() {
        console.log('📊 تحميل نظام تقارير التعرض...');
        
        // تحميل قائمة الموظفين
        this.loadEmployees();
        
        // تحميل التقارير الافتراضية
        this.loadExposureReports();
        
        // تحميل الإحصائيات
        this.loadStatistics();
        
        // تعيين التواريخ الافتراضية
        this.setDefaultDates();
    }

    async loadEmployees() {
        try {
            const response = await fetch('/api/employees');
            if (response.ok) {
                const data = await response.json();
                this.employees = data.employees || [];
                this.populateEmployeeSelect();
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل قائمة الموظفين:', error);
        }
    }

    populateEmployeeSelect() {
        const select = document.getElementById('employee-select');
        if (select) {
            // مسح الخيارات الحالية (عدا الخيار الأول)
            while (select.children.length > 1) {
                select.removeChild(select.lastChild);
            }
            
            // إضافة الموظفين
            this.employees.forEach(employee => {
                const option = document.createElement('option');
                option.value = employee.employee_id;
                option.textContent = `${employee.name} (${employee.employee_id})`;
                select.appendChild(option);
            });
        }
    }

    setDefaultDates() {
        const today = new Date();
        const oneWeekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        
        const dateFrom = document.getElementById('date-from');
        const dateTo = document.getElementById('date-to');
        
        if (dateFrom) {
            dateFrom.value = oneWeekAgo.toISOString().split('T')[0];
        }
        
        if (dateTo) {
            dateTo.value = today.toISOString().split('T')[0];
        }
    }

    async loadExposureReports() {
        try {
            console.log('📋 تحميل تقارير التعرض...');
            
            const employeeId = document.getElementById('employee-select')?.value || '';
            const dateFrom = document.getElementById('date-from')?.value || '';
            const dateTo = document.getElementById('date-to')?.value || '';
            
            const params = new URLSearchParams();
            if (employeeId) params.append('employee_id', employeeId);
            if (dateFrom) params.append('date_from', dateFrom);
            if (dateTo) params.append('date_to', dateTo);
            
            const response = await fetch(`/api/exposure_reports?${params}`);
            
            if (response.ok) {
                const data = await response.json();
                this.currentData = data.reports || [];
                this.displayReports();
            } else {
                throw new Error('فشل في تحميل التقارير');
            }
            
        } catch (error) {
            console.error('❌ خطأ في تحميل التقارير:', error);
            this.showError('فشل في تحميل تقارير التعرض');
        }
    }

    displayReports() {
        const tbody = document.getElementById('exposure-table-body');
        if (!tbody) return;
        
        if (this.currentData.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center text-muted">
                        <i class="fas fa-info-circle me-2"></i>
                        لا توجد بيانات للعرض
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = '';
        
        this.currentData.forEach((report, index) => {
            const row = this.createReportRow(report, index);
            tbody.appendChild(row);
        });
    }

    createReportRow(report, index) {
        const row = document.createElement('tr');
        
        const checkInDate = new Date(report.check_in_time);
        const checkOutDate = report.check_out_time ? new Date(report.check_out_time) : null;
        
        const safetyLevel = this.getSafetyLevel(report.total_exposure, report.average_dose_rate);
        const safetyBadge = this.getSafetyBadge(safetyLevel);
        
        // تنسيق مدة التعرض
        const durationDisplay = report.exposure_duration_minutes != null
            ? `${report.exposure_duration_minutes} دقيقة`
            : '<span class="text-muted">جارٍ العمل...</span>';

        row.innerHTML = `
            <td>${report.employee_name || 'غير محدد'}</td>
            <td>${checkInDate.toLocaleDateString('ar-SA')}</td>
            <td>${checkInDate.toLocaleTimeString('ar-SA')}</td>
            <td>${checkOutDate ? checkOutDate.toLocaleTimeString('ar-SA') : 'لم ينته'}</td>
            <td>${durationDisplay}</td>
            <td>${(report.total_exposure || 0).toFixed(5)}</td>
            <td>${(report.average_dose_rate || 0).toFixed(5)}</td>
            <td>${(report.max_dose_rate || 0).toFixed(5)}</td>
            <td>${safetyBadge}</td>
            <td>
                <button class="btn btn-sm btn-info" onclick="exposureReports.showDetails(${index})">
                    <i class="fas fa-eye"></i>
                </button>
            </td>
        `;
        
        return row;
    }

    getSafetyLevel(totalExposure, averageDoseRate) {
        if (totalExposure > 100 || averageDoseRate > 1.0) return 'danger';
        if (totalExposure > 50 || averageDoseRate > 0.5) return 'warning';
        if (totalExposure > 20 || averageDoseRate > 0.2) return 'caution';
        return 'safe';
    }

    getSafetyBadge(level) {
        const badges = {
            safe: '<span class="badge bg-success">آمن</span>',
            caution: '<span class="badge bg-info">انتباه</span>',
            warning: '<span class="badge bg-warning">تحذير</span>',
            danger: '<span class="badge bg-danger">خطر</span>'
        };
        return badges[level] || badges.safe;
    }

    showDetails(index) {
        const report = this.currentData[index];
        if (!report) return;
        
        const modal = new bootstrap.Modal(document.getElementById('exposureDetailModal'));
        const content = document.getElementById('exposure-detail-content');
        
        if (content) {
            content.innerHTML = this.generateDetailContent(report);
            modal.show();
        }
    }

    generateDetailContent(report) {
        const checkInDate = new Date(report.check_in_time);
        const checkOutDate = report.check_out_time ? new Date(report.check_out_time) : null;
        
        return `
            <div class="row">
                <div class="col-md-6">
                    <h6><i class="fas fa-user me-2"></i>معلومات الموظف</h6>
                    <p><strong>الاسم:</strong> ${report.employee_name || 'غير محدد'}</p>
                    <p><strong>رقم الموظف:</strong> ${report.employee_id}</p>
                    
                    <h6 class="mt-3"><i class="fas fa-clock me-2"></i>معلومات الوقت</h6>
                    <p><strong>وقت الدخول:</strong> ${checkInDate.toLocaleString('ar-SA')}</p>
                    <p><strong>وقت الخروج:</strong> ${checkOutDate ? checkOutDate.toLocaleString('ar-SA') : '<span class="text-warning">لم ينته بعد</span>'}</p>
                    <p><strong>مدة التعرض:</strong> ${report.exposure_duration_minutes != null ? report.exposure_duration_minutes + ' دقيقة' : '<span class="text-muted">جارٍ العمل...</span>'}</p>
                </div>
                <div class="col-md-6">
                    <h6><i class="fas fa-radiation me-2"></i>بيانات التعرض</h6>
                    <p><strong>الجرعة الأولية:</strong> ${(report.initial_total_dose || 0).toFixed(5)} μSv</p>
                    <p><strong>الجرعة النهائية:</strong> ${(report.final_total_dose || 0).toFixed(5)} μSv</p>
                    <p><strong>إجمالي التعرض:</strong> ${(report.total_exposure || 0).toFixed(5)} μSv</p>
                    <p><strong>متوسط معدل الجرعة:</strong> ${(report.average_dose_rate || 0).toFixed(5)} μSv/h</p>
                    <p><strong>أقصى معدل جرعة:</strong> ${(report.max_dose_rate || 0).toFixed(5)} μSv/h</p>
                    <p><strong>أقل معدل جرعة:</strong> ${(report.min_dose_rate || 0).toFixed(5)} μSv/h</p>
                </div>
            </div>
            
            <div class="row mt-3">
                <div class="col-12">
                    <h6><i class="fas fa-shield-alt me-2"></i>تقييم الأمان</h6>
                    <div class="alert alert-${this.getSafetyLevel(report.total_exposure, report.average_dose_rate) === 'safe' ? 'success' : 
                        this.getSafetyLevel(report.total_exposure, report.average_dose_rate) === 'caution' ? 'info' :
                        this.getSafetyLevel(report.total_exposure, report.average_dose_rate) === 'warning' ? 'warning' : 'danger'}">
                        ${this.getSafetyAssessmentText(report.total_exposure, report.average_dose_rate)}
                    </div>
                    
                    ${report.safety_alerts > 0 ? `
                        <div class="alert alert-warning">
                            <i class="fas fa-exclamation-triangle me-2"></i>
                            تم إصدار ${report.safety_alerts} تنبيه أمان خلال هذه الفترة
                        </div>
                    ` : ''}
                    
                    ${report.notes ? `
                        <h6 class="mt-3"><i class="fas fa-sticky-note me-2"></i>ملاحظات</h6>
                        <p>${report.notes}</p>
                    ` : ''}
                </div>
            </div>
        `;
    }

    getSafetyAssessmentText(totalExposure, averageDoseRate) {
        const level = this.getSafetyLevel(totalExposure, averageDoseRate);
        
        const assessments = {
            safe: 'مستوى التعرض ضمن الحدود الآمنة المقبولة',
            caution: 'مستوى التعرض يتطلب انتباه ومراقبة مستمرة',
            warning: 'مستوى التعرض مرتفع ويتطلب اتخاذ إجراءات وقائية',
            danger: 'مستوى التعرض خطير ويتطلب تدخل فوري ومراجعة طبية'
        };
        
        return assessments[level] || assessments.safe;
    }

    async loadStatistics() {
        try {
            const response = await fetch('/api/exposure_statistics');
            if (response.ok) {
                const data = await response.json();
                this.updateStatistics(data.statistics);
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل الإحصائيات:', error);
        }
    }

    updateStatistics(stats) {
        const elements = {
            'total-employees': stats.total_employees || 0,
            'total-sessions': stats.total_sessions || 0,
            'average-exposure': (stats.average_exposure || 0).toFixed(3),
            'safety-alerts': stats.safety_alerts || 0
        };
        
        Object.entries(elements).forEach(([id, value]) => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = value;
            }
        });
    }

    showError(message) {
        const tbody = document.getElementById('exposure-table-body');
        if (tbody) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        ${message}
                    </td>
                </tr>
            `;
        }
    }

    exportToExcel() {
        console.log('📊 تصدير البيانات إلى Excel...');
        // TODO: تنفيذ تصدير Excel
        alert('ميزة التصدير قيد التطوير');
    }

    printReport() {
        console.log('🖨️ طباعة التقرير...');
        window.print();
    }
}

// إنشاء مثيل من مدير التقارير
let exposureReports;

document.addEventListener('DOMContentLoaded', function() {
    exposureReports = new ExposureReportsManager();
});

// دوال عامة
function loadExposureReports() {
    if (exposureReports) {
        exposureReports.loadExposureReports();
    }
}

function exportToExcel() {
    if (exposureReports) {
        exposureReports.exportToExcel();
    }
}

function printReport() {
    if (exposureReports) {
        exposureReports.printReport();
    }
}

// التقارير الموحدة - JavaScript
class UnifiedReports {
    constructor() {
        this.currentData = null;
        this.filteredData = null;
        this.exposureData = null;
        this.cumulativeData = null;
        this.alertsData = null;
        this.currentAlertFilter = 'all';
        this.init();
    }

    init() {
        console.log('🚀 تهيئة التقارير الموحدة...');
        this.loadEmployees();
        this.loadReports();
        this.loadCumulativeDoses();
        this.loadAlerts();
        this.setupEventListeners();
    }

    setupEventListeners() {
        // إعداد مستمعي الأحداث
        document.getElementById('employeeFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        document.getElementById('dateFromFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        document.getElementById('dateToFilter').addEventListener('change', () => {
            this.applyFilters();
        });

        // تحديث الجرعات التراكمية عند تغيير التبويب
        const cumulativeTab = document.getElementById('cumulative-tab');
        if (cumulativeTab) {
            cumulativeTab.addEventListener('shown.bs.tab', () => {
                this.loadCumulativeDoses();
            });
        }

        // تحديث دوري احتياطي كل 30 ثانية عندما يكون التبويب مرئياً
        try {
            setInterval(() => {
                const pane = document.getElementById('cumulative-content');
                const isVisible = document.visibilityState === 'visible' && pane && pane.classList.contains('show');
                if (isVisible) {
                    this.loadCumulativeDoses();
                }
            }, 30000);
        } catch (e) { /* تجاهل أي أخطاء بسيطة */ }

        // تحديث الجرعات التراكمية فور وصول إشعار من صفحة الحضور
        window.addEventListener('storage', (e) => {
            if (e.key === 'radmeter:attendance_update') {
                console.log('🔔 إشعار حضور/انصراف: إعادة تحميل الجرعات التراكمية');
                this.loadCumulativeDoses();
            }
        });

        // تحديث التنبيهات عند تغيير التبويب
        const alertsTab = document.getElementById('alerts-tab');
        if (alertsTab) {
            alertsTab.addEventListener('shown.bs.tab', () => {
                this.loadAlerts();
            });
        }
    }

    async loadEmployees() {
        try {
            console.log('📋 تحميل قائمة الموظفين...');
            const response = await fetch('/api/unified_reports');
            const data = await response.json();

            if (data.success) {
                const employeeSelect = document.getElementById('employeeFilter');
                employeeSelect.innerHTML = '<option value="">All employees</option>';

                data.employees.forEach(employee => {
                    const option = document.createElement('option');
                    option.value = employee.employee_id;
                    option.textContent = `${employee.name} (${employee.employee_id})`;
                    employeeSelect.appendChild(option);
                });

                console.log(`✅ تم تحميل ${data.employees.length} موظف`);
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل الموظفين:', error);
            this.showError('فشل في تحميل قائمة الموظفين');
        }
    }

    async loadReports(filters = {}) {
        try {
            console.log('📊 تحميل التقارير...', filters);
            
            // بناء URL مع الفلاتر
            const params = new URLSearchParams();
            if (filters.employee_id) params.append('employee_id', filters.employee_id);
            if (filters.date_from) params.append('date_from', filters.date_from);
            if (filters.date_to) params.append('date_to', filters.date_to);

            const response = await fetch(`/api/unified_reports?${params}`);
            const data = await response.json();

            if (data.success) {
                this.currentData = data;
                this.filteredData = data.attendance_records;
                this.exposureData = data.exposure_records || [];
                this.updateStats();
                this.updateAttendanceTable();
                this.updateExposureTable();
                console.log(`✅ تم تحميل ${data.attendance_records.length} سجل حضور و ${this.exposureData.length} سجل تعرض`);
            } else {
                throw new Error(data.error || 'خطأ في تحميل البيانات');
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل التقارير:', error);
            this.showError('فشل في تحميل التقارير');
        }
    }

    updateStats() {
        if (!this.filteredData) return;

        const totalRecords = this.filteredData.length;
        const checkInRecords = this.filteredData.filter(r => r.check_type === 'check_in').length;
        const checkOutRecords = this.filteredData.filter(r => r.check_type === 'check_out').length;
        const activeEmployees = new Set(this.filteredData.map(r => r.employee_id)).size;

        // تحديث الإحصائيات
        document.getElementById('totalRecords').textContent = totalRecords;
        document.getElementById('checkInRecords').textContent = checkInRecords;
        document.getElementById('checkOutRecords').textContent = checkOutRecords;
        document.getElementById('activeEmployees').textContent = activeEmployees;

        console.log(`📊 الإحصائيات: ${totalRecords} سجل، ${activeEmployees} موظف نشط`);
    }

    updateAttendanceTable() {
        const tbody = document.getElementById('attendanceTableBody');
        
        if (!this.filteredData || this.filteredData.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4">
                        <i class="fas fa-inbox me-2"></i>
                        No records to display
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';

        this.filteredData.forEach(record => {
            const row = document.createElement('tr');
            
            // تحديد لون الشارة حسب نوع العملية
            const badgeClass = record.check_type === 'check_in' ? 'bg-success' : 'bg-danger';
            const badgeIcon = record.check_type === 'check_in' ? 'sign-in-alt' : 'sign-out-alt';
            const badgeText = record.check_type === 'check_in' ? 'Check-in' : 'Check-out';

            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <i class="fas fa-user me-2 text-primary"></i>
                        <strong>${record.name || 'N/A'}</strong>
                    </div>
                </td>
                <td>
                    <span class="badge bg-secondary">${record.employee_id || 'N/A'}</span>
                </td>
                <td>
                    <small class="text-muted">${record.job_title || 'N/A'}</small>
                </td>
                <td>
                    <span class="badge ${badgeClass} badge-status">
                        <i class="fas fa-${badgeIcon} me-1"></i>
                        ${badgeText}
                    </span>
                </td>
                <td>
                    <i class="fas fa-calendar me-1 text-muted"></i>
                    ${record.date || 'N/A'}
                </td>
                <td>
                    <i class="fas fa-clock me-1 text-muted"></i>
                    ${record.time || 'N/A'}
                </td>
            `;

            tbody.appendChild(row);
        });

        console.log(`📋 تم عرض ${this.filteredData.length} سجل في الجدول`);
    }

    updateExposureTable() {
        const tbody = document.getElementById('exposureTableBody');

        // إذا كان تبويب التعرض محذوفاً من الواجهة، لا تفعل شيئاً
        if (!tbody) {
            return;
        }

        if (!this.exposureData || this.exposureData.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4">
                        <i class="fas fa-radiation me-2"></i>
                        No exposure data to display
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';

        this.exposureData.forEach(record => {
            const row = document.createElement('tr');

            // Helper: translate Arabic terms to English
            const translateSafety = (status) => {
                if (!status) return 'N/A';
                if (status.includes('طبيعي')) return 'Normal';
                if (status.includes('آمن')) return 'Safe';
                if (status.includes('ضمن الحد المسموح')) return 'Within limit';
                if (status.includes('مراقبة')) return 'Monitor';
                if (status.includes('تحذير')) return 'Warning';
                if (status.includes('خطر')) return 'Danger';
                return status;
            };
            const translateRisk = (risk) => {
                if (!risk) return 'N/A';
                if (risk.includes('منخفض جداً')) return 'Very Low';
                if (risk.includes('منخفض-متوسط')) return 'Low-Medium';
                if (risk.includes('منخفض')) return 'Low';
                if (risk.includes('مقبول')) return 'Acceptable';
                if (risk.includes('متوسط')) return 'Medium';
                if (risk.includes('عالي')) return 'High';
                return risk;
            };

            // تحديد لون حالة الأمان بناءً على المعايير الدولية
            let safetyBadge = '';
            let riskBadge = '';

            // تصنيف حالة الأمان للعاملين
            if (record.safety_status === 'طبيعي') {
                safetyBadge = `<span class="badge bg-success"><i class="fas fa-leaf me-1"></i> Normal</span>`;
            } else if (record.safety_status === 'آمن') {
                safetyBadge = `<span class="badge bg-success"><i class="fas fa-shield-alt me-1"></i> Safe</span>`;
            } else if (record.safety_status === 'ضمن الحد المسموح') {
                safetyBadge = `<span class="badge bg-info"><i class="fas fa-check-circle me-1"></i> Within limit</span>`;
            } else if (record.safety_status && record.safety_status.includes('مراقبة')) {
                safetyBadge = `<span class="badge bg-warning"><i class="fas fa-eye me-1"></i> ${translateSafety(record.safety_status)}</span>`;
            } else if (record.safety_status && record.safety_status.includes('تحذير')) {
                safetyBadge = `<span class="badge bg-warning"><i class="fas fa-exclamation-triangle me-1"></i> ${translateSafety(record.safety_status)}</span>`;
            } else if (record.safety_status && record.safety_status.includes('خطر')) {
                safetyBadge = `<span class="badge bg-danger"><i class="fas fa-radiation me-1"></i> ${translateSafety(record.safety_status)}</span>`;
            }

            // تصنيف مستوى الخطر للعاملين
            if (record.risk_level === 'منخفض جداً' || record.risk_level === 'منخفض') {
                riskBadge = `<span class="badge bg-success">${translateRisk(record.risk_level)}</span>`;
            } else if (record.risk_level === 'منخفض-متوسط' || record.risk_level === 'مقبول') {
                riskBadge = `<span class="badge bg-info">${translateRisk(record.risk_level)}</span>`;
            } else if (record.risk_level === 'متوسط') {
                riskBadge = `<span class="badge bg-warning">${translateRisk(record.risk_level)}</span>`;
            } else if (record.risk_level === 'عالي') {
                riskBadge = `<span class="badge bg-danger">${translateRisk(record.risk_level)}</span>`;
            } else {
                riskBadge = `<span class="badge bg-dark">${translateRisk(record.risk_level)}</span>`;
            }

            // تنسيق مدة الجلسة
            const sessionDurationDisplay = record.session_duration != null
                ? `<span class="badge bg-info">${record.session_duration} min</span>`
                : `<span class="badge bg-secondary"><i class="fas fa-clock me-1"></i>In progress...</span>`;

            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <i class="fas fa-user me-2 text-primary"></i>
                        <strong>${record.name || 'غير محدد'}</strong>
                        <br><small class="text-muted">${record.employee_id}</small>
                    </div>
                </td>
                <td>
                    <i class="fas fa-calendar me-1 text-muted"></i>
                    ${record.date || 'غير محدد'}
                    <br><small class="text-muted">${record.start_time || ''}</small>
                </td>
                <td>
                    ${sessionDurationDisplay}
                </td>
                <td>
                    <strong class="text-warning">${record.total_dose} μSv</strong>
                </td>
                <td>
                    ${safetyBadge}
                    <br><small class="text-muted">Safety: ${record.safety_percentage}%</small>
                </td>
                <td>
                    ${riskBadge}
                </td>
            `;

            tbody.appendChild(row);
        });

        console.log(`☢️ تم عرض ${this.exposureData.length} سجل تعرض في الجدول`);
    }

    async loadCumulativeDoses(employeeId = '') {
        try {
            console.log('📊 تحميل الجرعات التراكمية...');

            // ✨ تحديث فوري لبيانات الموظف (أو الجميع) لضمان الاتساق بين الجرعات والمدد
            try {
                await fetch('/api/scheduler/force_update', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(employeeId ? { employee_id: employeeId } : {})
                });
            } catch (e) {
                console.warn('⚠️ فشل التحديث الفوري للمُجدول، سنكمل بجلب البيانات كما هي.', e);
            }
            
            const params = new URLSearchParams();
            if (employeeId) params.append('employee_id', employeeId);

            // ✅ استخدام الواجهة السريعة المتزامنة مع جدول البيانات التراكمية
            const response = await fetch(`/api/cumulative_doses_fast?${params}`);
            const data = await response.json();

            if (data.success) {
                // الواجهة السريعة تُرجع حقلي employees و cumulative_data - نستخدم cumulative_data
                this.cumulativeData = data.cumulative_data || data.employees || [];
                console.log('📦 بيانات الجرعات التراكمية (Raw):', this.cumulativeData);
                this.updateCumulativeTable();
                console.log(`✅ تم تحميل ${this.cumulativeData.length} موظف مع البيانات التراكمية (سريع)`);
            } else {
                throw new Error(data.error || 'خطأ في تحميل البيانات التراكمية');
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل الجرعات التراكمية:', error);
            this.showCumulativeError('فشل في تحميل الجرعات التراكمية');
        }
    }

    updateCumulativeTable() {
        const tbody = document.getElementById('cumulativeTableBody');

        if (!this.cumulativeData || this.cumulativeData.length === 0) {
        tbody.innerHTML = `
                <tr>
                    <td colspan="9" class="text-center py-4">
                        <i class="fas fa-inbox me-2"></i>
                        No cumulative data to display
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';

        this.cumulativeData.forEach(record => {
            const row = document.createElement('tr');

            // تحديد لون badge بناءً على حالة الأمان
            let statusBadge = '';
            const mapSafety = (s) => {
                if (!s) return 'N/A';
                if (s.includes('طبيعي')) return 'Normal';
                if (s.includes('آمن')) return 'Safe';
                if (s.includes('ضمن الحد المسموح')) return 'Within limit';
                if (s.includes('مراقبة')) return 'Monitor';
                if (s.includes('تحذير')) return 'Warning';
                if (s.includes('خطر')) return 'Danger';
                return s;
            };
            const safetyText = mapSafety(record.safety_status);
            if (record.status_class === 'success') {
                statusBadge = `<span class=\"badge bg-success\"><i class=\"fas fa-check-circle me-1\"></i> ${safetyText}</span>`;
            } else if (record.status_class === 'info') {
                statusBadge = `<span class=\"badge bg-info\"><i class=\"fas fa-eye me-1\"></i> ${safetyText}</span>`;
            } else if (record.status_class === 'warning') {
                statusBadge = `<span class=\"badge bg-warning\"><i class=\"fas fa-exclamation-triangle me-1\"></i> ${safetyText}</span>`;
            } else if (record.status_class === 'danger') {
                statusBadge = `<span class=\"badge bg-danger\"><i class=\"fas fa-radiation me-1\"></i> ${safetyText}</span>`;
            }

            // شريط تقدم نسبة الجرعة السنوية
            const progressColor = record.annual_percentage >= 80 ? 'bg-danger' : 
                                  record.annual_percentage >= 50 ? 'bg-warning' : 'bg-success';

            // ضمان كون القيم رقمية قبل التنسيق
            const daily = Number(record.daily_dose || 0);
            const dailyPct = Number(record.daily_percentage || 0);
            const weekly = Number(record.weekly_dose || 0);
            const weeklyPct = Number(record.weekly_percentage || 0);
            const monthly = Number(record.monthly_dose || 0);
            const monthlyPct = Number(record.monthly_percentage || 0);
            const annual = Number(record.annual_dose || 0);
            const annualPct = Number(record.annual_percentage || 0);
            const totalDose = Number(record.total_cumulative_dose || 0);
            const totalSessions = Number(record.total_sessions || 0);
            const totalReadings = Number(record.total_readings || 0);

            // ✨ حساب المدة ومعدل الجرعة
            const durationHours = Number(record.total_duration_hours || 0);
            const durationMinutes = Number(record.total_duration_minutes || 0);
            const doseRatePerHour = Number(record.dose_rate_per_hour || 0);
            
            row.innerHTML = `
                <td>
                    <div class="d-flex align-items-center">
                        <i class="fas fa-user-tie me-2 text-primary"></i>
                        <div>
                            <strong>${record.name || 'غير محدد'}</strong>
                            <br><small class="text-muted">${record.employee_id}</small>
                        </div>
                    </div>
                </td>
                <td>
                    <strong>${daily.toFixed(3)}</strong>
                </td>
                <td>
                    <strong>${weekly.toFixed(3)}</strong>
                </td>
                <td>
                    <strong>${monthly.toFixed(3)}</strong>
                </td>
                <td>
                    <strong class="text-primary">${annual.toFixed(3)}</strong>
                    <br>
                    <div class="progress" style="height: 8px; width: 100px;">
                        <div class="progress-bar ${progressColor}" role="progressbar" 
                             style="width: ${Math.min(annualPct, 100)}%">
                        </div>
                    </div>
                </td>
                <td>
                    <strong class="text-success">${totalDose.toFixed(3)}</strong>
                    <br><small class="text-muted">${totalSessions} sessions</small>
                    <br><small class="text-info"><i class="fas fa-wave-square me-1"></i>${totalReadings} readings</small>
                </td>
                <td>
                    <i class="fas fa-clock text-info me-1"></i>
                    <strong>${durationHours.toFixed(2)}</strong> h
                    <br><small class="text-muted">${durationMinutes.toFixed(0)} min</small>
                </td>
                <td>
                    <i class="fas fa-tachometer-alt text-warning me-1"></i>
                    <strong>${doseRatePerHour.toFixed(3)}</strong> μSv/h
                </td>
                <td>
                    ${statusBadge}
                    <br><button class="btn btn-sm btn-outline-primary mt-1" onclick="unifiedReports.showSessionDetails('${record.employee_id}')">
                        <i class="fas fa-info-circle me-1"></i>Details
                    </button>
                </td>
            `;

            tbody.appendChild(row);
        });

        console.log(`📊 تم عرض ${this.cumulativeData.length} موظف في جدول الجرعات التراكمية`);
    }

    applyFilters() {
        const filters = {
            employee_id: document.getElementById('employeeFilter').value,
            date_from: document.getElementById('dateFromFilter').value,
            date_to: document.getElementById('dateToFilter').value
        };

        console.log('🔍 تطبيق الفلاتر:', filters);
        this.loadReports(filters);
        
        // تحديث الجرعات التراكمية أيضاً عند تطبيق الفلاتر
        if (filters.employee_id) {
            this.loadCumulativeDoses(filters.employee_id);
        } else {
            this.loadCumulativeDoses();
        }
    }

    async showSessionDetails(employeeId) {
        try {
            console.log(`🔍 طلب تفاصيل الجلسات للموظف: ${employeeId}`);
            
            const response = await fetch(`/api/employee_sessions/${employeeId}`);
            const data = await response.json();
            
            if (!data.success) {
                alert('فشل في تحميل تفاصيل الجلسات: ' + data.error);
                return;
            }
            
            const empInfo = data.employee_info;
            const sessions = data.sessions;
            
            // إنشاء محتوى HTML للنافذة المنبثقة
            let modalContent = `
                <div class="modal fade" id="sessionDetailsModal" tabindex="-1">
                    <div class="modal-dialog modal-xl">
                        <div class="modal-content">
                            <div class="modal-header bg-primary text-white">
                                <h5 class="modal-title">
                                    <i class="fas fa-history me-2"></i>
                                    Exposure Sessions - ${empInfo.name}
                                </h5>
                                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body">
                                <div class="row mb-3">
                                    <div class="col-md-4">
                                        <strong><i class="fas fa-id-badge me-1"></i>Employee ID:</strong> ${empInfo.employee_id}
                                    </div>
                                    <div class="col-md-4">
                                        <strong><i class="fas fa-building me-1"></i>Department:</strong> ${empInfo.department}
                                    </div>
                                    <div class="col-md-4">
                                        <strong><i class="fas fa-briefcase me-1"></i>Position:</strong> ${empInfo.position}
                                    </div>
                                </div>
                                <hr>
                                <div class="table-responsive">
                                    <table class="table table-striped table-hover">
                                        <thead class="table-dark">
                                            <tr>
                                                <th>Date</th>
                                                <th>Check-in</th>
                                                <th>Check-out</th>
                                                <th>Duration</th>
                                                <th>Dose (μSv)</th>
                                                <th>Dose rate (μSv/h)</th>
                                                <th>Readings</th>
                                                <th>Status</th>
                                            </tr>
                                        </thead>
                                        <tbody>
            `;
            
            if (sessions.length === 0) {
                modalContent += `
                    <tr>
                        <td colspan="8" class="text-center py-4">
                            <i class="fas fa-inbox me-2"></i>
                            No sessions found
                        </td>
                    </tr>
                `;
            } else {
                sessions.forEach(session => {
                    const statusBadge = session.is_active 
                        ? '<span class="badge bg-success"><i class="fas fa-circle-notch fa-spin me-1"></i>Active</span>'
                        : '<span class="badge bg-secondary">Closed</span>';
                    
                    const checkOut = session.check_out_time 
                        ? new Date(session.check_out_time).toLocaleString('en-US', {hour: '2-digit', minute: '2-digit'})
                        : '-';
                    
                    const duration = session.duration_hours 
                        ? `${session.duration_hours.toFixed(2)} h (${session.duration_minutes.toFixed(0)} min)`
                        : '-';
                    
                    modalContent += `
                        <tr>
                            <td>${session.session_date}</td>
                            <td>${new Date(session.check_in_time).toLocaleString('en-US', {hour: '2-digit', minute: '2-digit'})}</td>
                            <td>${checkOut}</td>
                            <td>${duration}</td>
                            <td><strong class="text-warning">${session.total_exposure.toFixed(3)}</strong></td>
                            <td><strong class="text-info">${session.dose_rate_per_hour.toFixed(3)}</strong></td>
                            <td><span class="badge bg-primary">${session.readings_count}</span></td>
                            <td>${statusBadge}</td>
                        </tr>
                    `;
                });
            }
            
            modalContent += `
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    <i class="fas fa-times me-1"></i>Close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            // إزالة أي نافذة موجودة سابقاً
            const existingModal = document.getElementById('sessionDetailsModal');
            if (existingModal) {
                existingModal.remove();
            }
            
            // إضافة النافذة إلى الصفحة
            document.body.insertAdjacentHTML('beforeend', modalContent);
            
            // عرض النافذة
            const modal = new bootstrap.Modal(document.getElementById('sessionDetailsModal'));
            modal.show();
            
            // حذف النافذة بعد الإغلاق
            document.getElementById('sessionDetailsModal').addEventListener('hidden.bs.modal', function () {
                this.remove();
            });
            
        } catch (error) {
            console.error('❌ خطأ في عرض تفاصيل الجلسات:', error);
            alert('فشل في عرض تفاصيل الجلسات');
        }
    }

    showError(message) {
        const tbody = document.getElementById('attendanceTableBody');
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${message}
                </td>
            </tr>
        `;
    }

    showCumulativeError(message) {
        const tbody = document.getElementById('cumulativeTableBody');
        tbody.innerHTML = `
            <tr>
                <td colspan="9" class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${message}
                </td>
            </tr>
        `;
    }

    async loadAlerts() {
        try {
            console.log('🔔 تحميل التنبيهات...');
            
            const unreadParam = this.currentAlertFilter === 'unread' ? '&unread_only=true' : '';
            const response = await fetch(`/api/alerts?limit=100${unreadParam}`);
            const data = await response.json();

            if (data.success) {
                this.alertsData = data.alerts;
                this.updateAlertsTable();
                this.updateAlertsBadge(data.unread_count);
                console.log(`✅ تم تحميل ${data.alerts.length} تنبيه`);
            } else {
                throw new Error(data.error || 'خطأ في تحميل التنبيهات');
            }
        } catch (error) {
            console.error('❌ خطأ في تحميل التنبيهات:', error);
            this.showAlertsError('فشل في تحميل التنبيهات');
        }
    }

    updateAlertsTable() {
        const tbody = document.getElementById('alertsTableBody');

        if (!this.alertsData || this.alertsData.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center py-4">
                        <i class="fas fa-inbox me-2"></i>
                        No alerts to display
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = '';

        this.alertsData.forEach(alert => {
            const row = document.createElement('tr');
            row.style.cursor = 'pointer';
            if (!alert.acknowledged) {
                row.style.background = '#fff3cd';
            }

            // تحديد لون المستوى
            let levelBadge = '';
            if (alert.alert_level === 'critical') {
                levelBadge = '<span class="badge bg-danger">Critical</span>';
            } else if (alert.alert_level === 'danger') {
                levelBadge = '<span class="badge bg-danger">Danger</span>';
            } else if (alert.alert_level === 'warning') {
                levelBadge = '<span class="badge bg-warning">Warning</span>';
            } else {
                levelBadge = '<span class="badge bg-info">Info</span>';
            }

            // أيقونة القراءة
            const readIcon = alert.acknowledged 
                ? '<i class="fas fa-check-circle text-success"></i>' 
                : '<i class="fas fa-circle text-danger"></i>';

            // تنسيق الوقت
            const timeAgo = this.getTimeAgo(alert.timestamp);

            row.innerHTML = `
                <td class="text-center">${readIcon}</td>
                <td>
                    <strong>${alert.employee_name}</strong>
                    <br><small class="text-muted">${alert.employee_id}</small>
                </td>
                <td>${levelBadge}</td>
                <td>${alert.message}</td>
                <td>
                    <strong>${alert.dose_value ? alert.dose_value.toFixed(2) : '-'}</strong>
                    <br><small class="text-muted">Limit: ${alert.threshold_value ? alert.threshold_value.toFixed(2) : '-'}</small>
                </td>
                <td>
                    <small>${timeAgo}</small>
                    <br><small class="text-muted">${this.formatDateTime(alert.timestamp)}</small>
                </td>
            `;

            // عند الضغط على السطر، حدده كمقروء
            row.addEventListener('click', () => this.acknowledgeAlert(alert.id));

            tbody.appendChild(row);
        });

        console.log(`🔔 تم عرض ${this.alertsData.length} تنبيه في الجدول`);
    }

    updateAlertsBadge(count) {
        const badge = document.getElementById('alertsTabBadge');
        if (badge) {
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    }

    async acknowledgeAlert(alertId) {
        try {
            const response = await fetch(`/api/alerts/${alertId}/acknowledge`, {
                method: 'POST'
            });

            if (response.ok) {
                await this.loadAlerts();
            }
        } catch (error) {
            console.error('❌ خطأ في تحديث التنبيه:', error);
        }
    }

    getTimeAgo(timestamp) {
        const now = new Date();
        const alertTime = new Date(timestamp);
        const diffMs = now - alertTime;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'now';
        if (diffMins < 60) return `${diffMins} minutes ago`;
        if (diffHours < 24) return `${diffHours} hours ago`;
        return `${diffDays} days ago`;
    }

    formatDateTime(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    showAlertsError(message) {
        const tbody = document.getElementById('alertsTableBody');
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4 text-danger">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${message}
                </td>
            </tr>
        `;
    }

    showLoading() {
        const tbody = document.getElementById('attendanceTableBody');
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center py-4">
                    <i class="fas fa-spinner fa-spin me-2"></i>
                    Loading data...
                </td>
            </tr>
        `;
    }
}

// دالة عامة لفلترة التنبيهات
function filterAlerts(filter) {
    if (window.unifiedReports) {
        window.unifiedReports.currentAlertFilter = filter;
        window.unifiedReports.loadAlerts();
    }
}

// دالة عامة لتطبيق الفلاتر (يمكن استدعاؤها من HTML)
function applyFilters() {
    if (window.unifiedReports) {
        window.unifiedReports.applyFilters();
    }
}

// تهيئة التطبيق عند تحميل الصفحة
document.addEventListener('DOMContentLoaded', function() {
    console.log('🌟 بدء تحميل التقارير الموحدة...');
    window.unifiedReports = new UnifiedReports();
});

// دالة مساعدة لتنسيق التاريخ
function formatDate(dateString) {
    if (!dateString) return 'غير محدد';
    
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('ar-SA', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    } catch (error) {
        return dateString;
    }
}

// دالة مساعدة لتنسيق الوقت
function formatTime(timeString) {
    if (!timeString) return 'غير محدد';
    
    try {
        const time = new Date(`2000-01-01 ${timeString}`);
        return time.toLocaleTimeString('ar-SA', {
            hour: '2-digit',
            minute: '2-digit'
        });
    } catch (error) {
        return timeString;
    }
}

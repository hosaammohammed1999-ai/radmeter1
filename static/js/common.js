/**
 * ملف JavaScript موحد للوظائف المشتركة
 * RadMeter - نظام مراقبة الإشعاع
 */

// ===================================
// وظائف الساعة والوقت
// ===================================

function updateTime() {
    const now = new Date();
    const timeString = now.toLocaleString('en-US', {
        timeZone: 'Asia/Baghdad',
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        timeElement.textContent = timeString;
    }
}

// تحديث الساعة كل ثانية
function initializeClock() {
    setInterval(updateTime, 1000);
    updateTime(); // تحديث فوري عند تحميل الصفحة
}

// ===================================
// وظائف التحميل والتفاعل
// ===================================

function showLoading(element, text = 'Loading...') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }
    
    if (element) {
        element.innerHTML = `
            <div class="d-flex align-items-center justify-content-center">
                <div class="loading-spinner me-2"></div>
                <span>${text}</span>
            </div>
        `;
        element.classList.add('status-indicator');
    }
}

function showSuccess(element, text, icon = 'fas fa-check-circle') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }
    
    if (element) {
        element.innerHTML = `
            <div class="status-success slide-up">
                <i class="${icon} me-2"></i>
                ${text}
            </div>
        `;
    }
}

function showError(element, text, icon = 'fas fa-exclamation-triangle') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }
    
    if (element) {
        element.innerHTML = `
            <div class="status-error slide-up">
                <i class="${icon} me-2"></i>
                ${text}
            </div>
        `;
    }
}

function showWarning(element, text, icon = 'fas fa-exclamation-triangle') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }
    
    if (element) {
        element.innerHTML = `
            <div class="status-warning slide-up">
                <i class="${icon} me-2"></i>
                ${text}
            </div>
        `;
    }
}

// ===================================
// وظائف التحقق من صحة البيانات
// ===================================

function validateEmployeeId(employeeId) {
    // Validate employee id contains digits only
    const regex = /^[0-9]+$/;
    return employeeId && employeeId.trim() !== '' && regex.test(employeeId.trim());
}

function validateEmployeeName(name) {
    // Validate name contains Arabic or English letters
    const regex = /^[\u0600-\u06FFa-zA-Z\s]+$/;
    return name && name.trim() !== '' && name.trim().length >= 2 && regex.test(name.trim());
}

function validateForm(formData) {
    const errors = [];
    
    if (!validateEmployeeId(formData.employeeId)) {
        errors.push('رقم الموظف غير صحيح - يجب أن يحتوي على أرقام فقط');
    }
    
    if (!validateEmployeeName(formData.name)) {
        errors.push('اسم الموظف غير صحيح - يجب أن يحتوي على حروف عربية أو إنجليزية فقط');
    }
    
    return {
        isValid: errors.length === 0,
        errors: errors
    };
}

// ===================================
// وظائف التفاعل مع الخادم
// ===================================

async function makeRequest(url, options = {}) {
    try {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        const finalOptions = { ...defaultOptions, ...options };
        
        const response = await fetch(url, finalOptions);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('خطأ في الطلب:', error);
        throw error;
    }
}

// ===================================
// وظائف التحكم في الواجهة
// ===================================

function addInteractiveEffects() {
    // إضافة تأثيرات تفاعلية للعناصر
    const interactiveElements = document.querySelectorAll('.interactive-element');
    
    interactiveElements.forEach(element => {
        element.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
        });
        
        element.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
}

function initializeTooltips() {
    // تفعيل tooltips في Bootstrap
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

function smoothScrollTo(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
}

// ===================================
// وظائف التهيئة العامة
// ===================================

function initializeCommonFeatures() {
    // تهيئة الساعة
    initializeClock();
    
    // تهيئة التأثيرات التفاعلية
    addInteractiveEffects();
    
    // تهيئة tooltips
    if (typeof bootstrap !== 'undefined') {
        initializeTooltips();
    }
    
    // إضافة تأثيرات fade-in للعناصر
    const fadeElements = document.querySelectorAll('.fade-in');
    fadeElements.forEach((element, index) => {
        setTimeout(() => {
            element.style.opacity = '1';
            element.style.transform = 'translateY(0)';
        }, index * 100);
    });
}

// ===================================
// وظائف مساعدة للتنسيق
// ===================================

function formatDateTime(date) {
    return new Date(date).toLocaleString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
}

function formatTime(date) {
    return new Date(date).toLocaleString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
}

function formatDate(date) {
    return new Date(date).toLocaleString('en-US', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
}

// ===================================
// تهيئة تلقائية عند تحميل الصفحة
// ===================================

document.addEventListener('DOMContentLoaded', function() {
    initializeCommonFeatures();
    
    // إضافة مستمع للنقر على الروابط للتأثيرات السلسة
    const navLinks = document.querySelectorAll('.modern-nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            // إضافة تأثير loading قصير
            this.style.opacity = '0.7';
            setTimeout(() => {
                this.style.opacity = '1';
            }, 200);
        });
    });
});

// تصدير الوظائف للاستخدام في ملفات أخرى
window.RadMeterCommon = {
    updateTime,
    initializeClock,
    showLoading,
    showSuccess,
    showError,
    showWarning,
    validateEmployeeId,
    validateEmployeeName,
    validateForm,
    makeRequest,
    formatDateTime,
    formatTime,
    formatDate,
    smoothScrollTo
};

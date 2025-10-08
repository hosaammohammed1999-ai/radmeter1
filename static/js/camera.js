let video = document.getElementById('video');
let canvas = document.getElementById('canvas');
let context = canvas.getContext('2d');
let currentStream = null;
let availableCameras = [];
let currentCameraIndex = 0;

// تهيئة الكاميرا - محاولة استخدام الكاميرا الخارجية أولاً
async function initializeCamera() {
    try {
        // الحصول على قائمة الكاميرات المتاحة
        const devices = await navigator.mediaDevices.enumerateDevices();
        availableCameras = devices.filter(device => device.kind === 'videoinput');

        console.log('Available cameras:', availableCameras);
        updateCameraInfo();

        let selectedDeviceId = null;

        // البحث عن الكاميرا الخارجية (عادة تكون الثانية في القائمة)
        if (availableCameras.length > 1) {
            // استخدام الكاميرا الثانية (الخارجية)
            currentCameraIndex = 1;
            selectedDeviceId = availableCameras[1].deviceId;
            console.log('Selected external camera:', availableCameras[1].label);
        } else if (availableCameras.length === 1) {
            // استخدام الكاميرا الوحيدة المتاحة
            currentCameraIndex = 0;
            selectedDeviceId = availableCameras[0].deviceId;
            console.log('Selected the only available camera:', availableCameras[0].label);
        }

        // إعدادات الكاميرا
        const constraints = {
            video: {
                deviceId: selectedDeviceId ? { exact: selectedDeviceId } : undefined,
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            }
        };

        // تشغيل الكاميرا
        currentStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentStream;
        video.play();

        console.log('Camera started successfully');
        updateCameraInfo();

    } catch (err) {
        console.error("Error starting camera:", err);

        // في حالة فشل الكاميرا المحددة، جرب الكاميرا الافتراضية
        try {
            console.log('Trying default camera...');
            const fallbackStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 }
                }
            });
            video.srcObject = fallbackStream;
            video.play();
            console.log('Default camera started');
        } catch (fallbackErr) {
            console.error("Failed to start any camera:", fallbackErr);
            alert('Cannot access the camera. Please ensure it is connected and permissions are granted.');
        }
    }
}

// تشغيل الكاميرا عند تحميل الصفحة
initializeCamera();

function takeAttendance(checkType) {
    // التقاط صورة من الكاميرا
    context.drawImage(video, 0, 0, 640, 480);

    // تحويل الصورة إلى blob
    canvas.toBlob(function(blob) {
        const formData = new FormData();
        formData.append('image', blob, 'capture.jpg');
        formData.append('check_type', checkType);

        // إرسال الصورة إلى الخادم
        fetch('/api/register_attendance', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            // التحقق من حالة الاستجابة أولاً
            if (response.status === 409) {
                // حالة منع التكرار (Conflict)
                return response.json().then(data => {
                    handleAttendanceConflict(data, checkType);
                    return { handled: true };
                });
            }
            return response.json();
        })
        .then(data => {
            // إذا تم التعامل مع التعارض، لا نفعل شيء
            if (data && data.handled) {
                return;
            }
            
            if (data.success) {
                // تأثير صوتي للنجاح
                playSuccessSound();

                // إعداد محتوى الرسالة الأساسية
                let resultHTML = `
                    <div class="alert alert-success border-0 shadow-sm" style="border-radius: 15px;">
                        <div class="d-flex align-items-center">
                            <i class="fas fa-check-circle fa-2x text-success me-3"></i>
                            <div>
                                <h5 class="mb-1">
                                    <i class="fas fa-${checkType === 'check_in' ? 'sign-in-alt' : 'sign-out-alt'} me-2"></i>
                                    ${checkType === 'check_in' ? 'Check-in' : 'Check-out'} recorded successfully!
                                </h5>
                                <p class="mb-1">
                                    <i class="fas fa-user me-2"></i>
                                    <strong>Employee name:</strong> ${data.employee_name}
                                </p>
                                <p class="mb-1">
                                    <i class="fas fa-id-card me-2"></i>
                                    <strong>Employee ID:</strong> ${data.employee_id}
                                </p>
                                <p class="mb-1">
                                    <i class="fas fa-clock me-2"></i>
                                    <strong>Time:</strong> ${data.timestamp}
                                </p>`

                // إضافة معلومات التعرض إذا كانت متوفرة
                if (data.exposure) {
                    if (data.exposure.success) {
                        const exposureData = data.exposure.data;
                        if (checkType === 'check_in') {
                            resultHTML += `
                                <div class="mt-2 p-2 bg-light rounded">
                                    <p class="mb-1 text-success">
                                        <i class="fas fa-radiation me-2"></i>
                                        <strong>Exposure monitoring started</strong>
                                    </p>
                                    <small class="text-muted">
                                        Initial dose: ${exposureData.initial_dose ? exposureData.initial_dose.toFixed(5) : '0.00000'} μSv
                                    </small>
                                </div>`
                        } else if (checkType === 'check_out') {
                            resultHTML += `
                                <div class="mt-2 p-2 bg-light rounded">
                                    <p class="mb-1 text-success">
                                        <i class="fas fa-radiation me-2"></i>
                                        <strong>Exposure monitoring stopped</strong>
                                    </p>
                                    <small class="text-muted">
                                        Duration: ${exposureData.duration_formatted || 'N/A'}<br>
                                        Total exposure: ${exposureData.total_exposure ? exposureData.total_exposure.toFixed(6) : '0.000000'} μSv
                                    </small>
                                </div>`
                        }
                    } else {
                        resultHTML += `
                            <div class="mt-2 p-2 bg-warning bg-opacity-25 rounded">
                                <p class="mb-0 text-warning">
                                    <i class="fas fa-exclamation-triangle me-2"></i>
                                    <small>تحذير: ${data.exposure.message || 'فشل في مراقبة التعرض'}</small>
                                </p>
                            </div>`;
                    }
                }

                resultHTML += `
                            </div>
                        </div>
                    </div>`;

                document.getElementById('result').innerHTML = resultHTML;

                // إضافة تأثير الاهتزاز للنجاح
                if (navigator.vibrate) {
                    navigator.vibrate([200, 100, 200]);
                }

                // إخفاء الرسالة بعد 7 ثوان
                setTimeout(() => {
                    document.getElementById('result').innerHTML = '';
                }, 7000);

            } else {
                // تأثير صوتي للخطأ
                playErrorSound();

                document.getElementById('result').innerHTML =
                    `<div class="alert alert-danger border-0 shadow-sm" style="border-radius: 15px;">
                        <div class="d-flex align-items-center">
                            <i class="fas fa-exclamation-triangle fa-2x text-danger me-3"></i>
                            <div>
                                <h5 class="mb-1">
                                    <i class="fas fa-times me-2"></i>
                                    Failed to record attendance
                                </h5>
                                <p class="mb-0">${data.error}</p>
                            </div>
                        </div>
                    </div>`;

                // إضافة تأثير الاهتزاز للخطأ
                if (navigator.vibrate) {
                    navigator.vibrate([500]);
                }

                // إخفاء رسالة الخطأ بعد 5 ثوان
                setTimeout(() => {
                    document.getElementById('result').innerHTML = '';
                }, 5000);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            playErrorSound();
            document.getElementById('result').innerHTML =
                `<div class="alert alert-danger border-0 shadow-sm" style="border-radius: 15px;">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-wifi fa-2x text-danger me-3"></i>
                        <div>
                            <h5 class="mb-1">Connection error</h5>
                            <p class="mb-0">An error occurred while processing the request</p>
                        </div>
                    </div>
                </div>`
        });
    }, 'image/jpeg');
}

// دالة معالجة حالات منع التكرار (تسجيل مكرر)
function handleAttendanceConflict(data, requestedCheckType) {
    console.log('🚫 تعارض في تسجيل الحضور:', data);
    
    // تأثير صوتي للتحذير
    playWarningSound();
    
    let iconClass = '';
    let titleText = '';
    let buttonText = '';
    let buttonAction = '';
    let buttonClass = 'btn-warning';
    
    if (data.error_code === 'DUPLICATE_CHECK_IN') {
        iconClass = 'fas fa-user-check';
        titleText = 'Employee already checked in';
        buttonText = '📝 Record check-out instead';
        buttonAction = "takeAttendance('check_out')";
        buttonClass = 'btn-danger';
    } else if (data.error_code === 'NO_CHECK_IN_TODAY') {
        iconClass = 'fas fa-user-times';
        titleText = 'No check-in recorded today';
        buttonText = '📝 Record check-in instead';
        buttonAction = "takeAttendance('check_in')";
        buttonClass = 'btn-success';
    }
    
    // تنسيق وقت آخر عملية إذا كان متاحاً
    let lastCheckInfo = '';
    if (data.last_check_time) {
        try {
            const lastTime = new Date(data.last_check_time).toLocaleString('en-US', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
            lastCheckInfo = `<small class="text-muted d-block mt-1">
                <i class="fas fa-history me-1"></i>
                Last action: ${lastTime}
            </small>`;
        } catch (e) {
            console.warn('خطأ في تنسيق الوقت:', e);
        }
    }
    
    const resultHTML = `
        <div class="alert alert-warning border-0 shadow-sm animate__animated animate__shakeX" style="border-radius: 15px; border-left: 5px solid #ffc107;">
            <div class="d-flex align-items-start">
                <i class="${iconClass} fa-2x text-warning me-3 mt-1"></i>
                <div class="flex-grow-1">
                    <h5 class="mb-2 text-warning">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        ${titleText}
                    </h5>
                    
                    <div class="mb-2">
                        <p class="mb-1 fw-bold text-dark">${data.message}</p>
                        <p class="mb-1 text-muted small">${data.detailed_message}</p>
                    </div>
                    
                    <div class="employee-info bg-light p-2 rounded mb-2">
                        <small class="text-dark">
                            <i class="fas fa-user me-1"></i>
                            <strong>Employee name:</strong> ${data.employee_name}
                        </small>
                        <small class="text-muted d-block">
                            <i class="fas fa-id-badge me-1"></i>
                            <strong>Employee ID:</strong> ${data.employee_id}
                        </small>
                        ${lastCheckInfo}
                    </div>
                    
                    <div class="suggestion-box p-2 bg-info bg-opacity-10 rounded mb-3">
                        <small class="text-info">
                            <i class="fas fa-lightbulb me-1"></i>
                            <strong>Suggestion:</strong> ${data.suggestion}
                        </small>
                    </div>
                    
                    <div class="action-buttons d-flex gap-2">
                        <button class="btn ${buttonClass} btn-sm px-3" onclick="${buttonAction}">
                            ${buttonText}
                        </button>
                        <button class="btn btn-outline-secondary btn-sm px-3" onclick="clearResult()">
                            <i class="fas fa-times me-1"></i>
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>`;
    
    document.getElementById('result').innerHTML = resultHTML;
    
    // تأثير اهتزاز للتحذير
    if (navigator.vibrate) {
        navigator.vibrate([200, 100, 200, 100, 200]);
    }
    
    // إخفاء الرسالة بعد 15 ثانية (وقت أطول لإتاحة القراءة)
    setTimeout(() => {
        const resultDiv = document.getElementById('result');
        if (resultDiv && resultDiv.innerHTML.includes('تعارض')) {
            resultDiv.innerHTML = '';
        }
    }, 15000);
}

// دالة مسح نتائج الرسائل
function clearResult() {
    document.getElementById('result').innerHTML = '';
}

// تأثير صوتي للتحذير
function playWarningSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        // نغمة تحذير (تردد متوسط)
        oscillator.frequency.setValueAtTime(600, audioContext.currentTime);
        oscillator.frequency.setValueAtTime(400, audioContext.currentTime + 0.2);
        oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.4);
        
        gainNode.gain.setValueAtTime(0.2, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.6);
        
        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.6);
    } catch (error) {
        console.warn('خطأ في تشغيل الصوت:', error);
    }
}

// وظائف التأثيرات الصوتية
function playSuccessSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
        oscillator.frequency.setValueAtTime(1000, audioContext.currentTime + 0.1);

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.3);
    } catch (error) {
        console.log('Audio not supported');
    }
}

function playErrorSound() {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.setValueAtTime(400, audioContext.currentTime);
        oscillator.frequency.setValueAtTime(200, audioContext.currentTime + 0.1);

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + 0.5);
    } catch (error) {
        console.log('Audio not supported');
    }
}

// تحسين تحديث معلومات الكاميرا
function updateCameraInfo() {
    const cameraInfoElement = document.getElementById('camera-info');
    if (availableCameras.length > 0 && currentCameraIndex < availableCameras.length) {
        const currentCamera = availableCameras[currentCameraIndex];
        const cameraName = currentCamera.label || `Camera ${currentCameraIndex + 1}`;
        cameraInfoElement.innerHTML = `
            <i class="fas fa-video me-2"></i>
            <strong>Current camera:</strong> ${cameraName}
            <span class="badge bg-primary ms-2">${currentCameraIndex + 1}/${availableCameras.length}</span>
        `;
    } else {
        cameraInfoElement.innerHTML = `
            <i class="fas fa-exclamation-triangle me-2"></i>
            No camera information
        `;
    }
}

// تبديل الكاميرا
async function switchCamera() {
    if (availableCameras.length <= 1) {
        alert('No other cameras available to switch');
        return;
    }

    // إيقاف الكاميرا الحالية
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
    }

    // الانتقال للكاميرا التالية
    currentCameraIndex = (currentCameraIndex + 1) % availableCameras.length;

    try {
        const selectedCamera = availableCameras[currentCameraIndex];
        const constraints = {
            video: {
                deviceId: { exact: selectedCamera.deviceId },
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            }
        };

        currentStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentStream;
        video.play();

        updateCameraInfo();
        console.log('Switched camera to:', selectedCamera.label);

        // إظهار رسالة نجاح مؤقتة
        const cameraInfoElement = document.getElementById('camera-info');
        const originalText = cameraInfoElement.innerHTML;
        cameraInfoElement.innerHTML = '✅ Camera switched successfully';
        cameraInfoElement.style.backgroundColor = '#d4edda';
        cameraInfoElement.style.color = '#155724';

        setTimeout(() => {
            cameraInfoElement.innerHTML = originalText;
            cameraInfoElement.style.backgroundColor = '';
            cameraInfoElement.style.color = '';
        }, 2000);

    } catch (err) {
        console.error('Error switching camera:', err);
        alert('Failed to switch camera');
        // العودة للكاميرا السابقة
        currentCameraIndex = (currentCameraIndex - 1 + availableCameras.length) % availableCameras.length;
        initializeCamera();
    }
}

// تحديث الكاميرا
function refreshCamera() {
    initializeCamera();
}

// تحسين إعادة تحميل الوجوه
function reloadFaces(event) {
    const facesInfoElement = document.getElementById('faces-info');
    const button = event ? event.target : document.querySelector('button[onclick="reloadFaces(event)"]');

    // تعطيل الزر وإظهار تحميل
    if (button) {
        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Loading...';
    }

    facesInfoElement.innerHTML = `
        <div class="d-flex align-items-center justify-content-center">
            <i class="fas fa-spinner fa-spin me-2"></i>
            Reloading known faces...
        </div>
    `;
    facesInfoElement.style.color = '#007bff';

    fetch('/api/reload_faces', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            facesInfoElement.innerHTML = `
                <div class="alert alert-success d-inline-block border-0 py-2 px-3" style="border-radius: 15px;">
                    <i class="fas fa-check-circle me-2"></i>
                    ${data.message}
                    <span class="badge bg-success ms-2">${data.faces_count}</span>
                </div>
            `;

            // تأثير صوتي للنجاح
            playSuccessSound();

            // إخفاء الرسالة بعد 5 ثوان
            setTimeout(() => {
                facesInfoElement.innerHTML = `
                    <i class="fas fa-brain me-2"></i>
                    Loaded ${data.faces_count} known face(s)
                    <span class="badge bg-info ms-2">${data.faces_count}</span>
                `;
                facesInfoElement.style.color = '#6c757d';
            }, 5000);
        } else {
            facesInfoElement.innerHTML = `
                <div class="alert alert-danger d-inline-block border-0 py-2 px-3" style="border-radius: 15px;">
                    <i class="fas fa-exclamation-triangle me-2"></i>
                    ${data.error}
                </div>
            `;
            playErrorSound();
        }
    })
    .catch(error => {
        console.error('Error:', error);
        facesInfoElement.innerHTML = `
            <div class="alert alert-danger d-inline-block border-0 py-2 px-3" style="border-radius: 15px;">
                <i class="fas fa-wifi me-2"></i>
                Server connection error
            </div>
        `;
        playErrorSound();
    })
    .finally(() => {
        // إعادة تفعيل الزر
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="fas fa-brain me-2"></i>Reload faces';
        }
    });
}

// تحميل معلومات الوجوه عند تحميل الصفحة
window.addEventListener('load', function() {
    fetch('/api/reload_faces', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('faces-info').innerHTML = `
                <i class="fas fa-brain me-2"></i>
                Loaded ${data.faces_count} known face(s)
                <span class="badge bg-info ms-2">${data.faces_count}</span>
            `;
            document.getElementById('faces-info').style.color = '#6c757d';
        }
    })
    .catch(error => console.log('Error loading faces info:', error));
});

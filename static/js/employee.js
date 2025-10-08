let video = document.getElementById('video');
let canvas = document.getElementById('canvas');
let context = canvas.getContext('2d');
let capturedImage = null;
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
            currentCameraIndex = 1;
            selectedDeviceId = availableCameras[1].deviceId;
        } else if (availableCameras.length === 1) {
            currentCameraIndex = 0;
            selectedDeviceId = availableCameras[0].deviceId;
        }

        const constraints = {
            video: {
                deviceId: selectedDeviceId ? { exact: selectedDeviceId } : undefined,
                width: { ideal: 640 },
                height: { ideal: 480 },
                frameRate: { ideal: 30 }
            }
        };

        currentStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentStream;
        video.play();
        updateCameraInfo();

    } catch (err) {
        console.error("Error starting camera:", err);
        try {
            const fallbackStream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = fallbackStream;
            video.play();
        } catch (fallbackErr) {
            console.error("Failed to start any camera:", fallbackErr);
            alert('Cannot access the camera. Please ensure it is connected and permissions are granted.');
        }
    }
}

// تشغيل الكاميرا عند تحميل الصفحة
initializeCamera();

function captureImage() {
    context.drawImage(video, 0, 0, 640, 480);
    capturedImage = canvas.toDataURL('image/jpeg');

    const statusElement = document.getElementById('capture-status');
    statusElement.innerHTML = `
        <div class="alert alert-success d-inline-block border-0 py-2 px-3" style="border-radius: 15px;">
            <i class="fas fa-check-circle me-2"></i>
            Image captured successfully!
        </div>
    `;
    playSuccessSound();
}

// منطق إظهار/إخفاء قائمة الحمل
document.getElementById('gender').addEventListener('change', function() {
    const pregnantRow = document.getElementById('pregnantRow');
    if (this.value === 'Female') {
        pregnantRow.style.display = '';
    } else {
        pregnantRow.style.display = 'none';
        document.getElementById('pregnant').value = '';
    }
});

document.getElementById('employeeForm').addEventListener('submit', function(e) {
    e.preventDefault();
    const resultElement = document.getElementById('result');

    if (!capturedImage) {
        resultElement.innerHTML = `
            <div class="alert alert-warning border-0 shadow-sm" style="border-radius: 15px;">
                <i class="fas fa-exclamation-triangle me-3"></i> Please capture a photo first
            </div>
        `;
        return;
    }

    resultElement.innerHTML = `
        <div class="alert alert-info border-0 shadow-sm" style="border-radius: 15px;">
            <i class="fas fa-spinner fa-spin me-3"></i> Saving...
        </div>
    `;

    const formData = new FormData();
    formData.append('employee_id', document.getElementById('employeeId').value);
    formData.append('name', document.getElementById('name').value);
    formData.append('job_title', document.getElementById('jobTitle').value);
    formData.append('gender', document.getElementById('gender').value);
    formData.append('pregnant', document.getElementById('pregnant').value);

    fetch(capturedImage)
        .then(res => res.blob())
        .then(blob => {
            formData.append('image', blob, 'employee.jpg');
            return fetch('/api/add_employee', {
                method: 'POST',
                body: formData
            });
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                resultElement.innerHTML = `
                    <div class="alert alert-success border-0 shadow-sm" style="border-radius: 15px;">
                        <i class="fas fa-check-circle me-3"></i> ${data.message}
                    </div>
                `;
                playSuccessSound();
                setTimeout(() => {
                    window.location.href = '/';
                }, 3000);
            } else {
                resultElement.innerHTML = `
                    <div class="alert alert-danger border-0 shadow-sm" style="border-radius: 15px;">
                        <i class="fas fa-exclamation-triangle me-3"></i> ${data.error}
                    </div>
                `;
                playErrorSound();
            }
        })
        .catch(error => {
            console.error('Error:', error);
            resultElement.innerHTML = `
                <div class="alert alert-danger border-0 shadow-sm" style="border-radius: 15px;">
                        <i class="fas fa-wifi me-3"></i> Server connection error
                </div>
            `;
            playErrorSound();
        });
});

// --- دوال التحكم بالكاميرا ---

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
        cameraInfoElement.innerHTML = `<i class="fas fa-exclamation-triangle me-2"></i> No cameras available`;
    }
}

async function switchCamera() {
    if (availableCameras.length <= 1) {
        alert('No other cameras available to switch');
        return;
    }
    if (currentStream) {
        currentStream.getTracks().forEach(track => track.stop());
    }
    currentCameraIndex = (currentCameraIndex + 1) % availableCameras.length;
    try {
        const selectedCamera = availableCameras[currentCameraIndex];
        const constraints = {
            video: {
                deviceId: { exact: selectedCamera.deviceId },
                width: { ideal: 640 },
                height: { ideal: 480 }
            }
        };
        currentStream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = currentStream;
        video.play();
        updateCameraInfo();
    } catch (err) {
        console.error('Error switching camera:', err);
        alert('Failed to switch camera');
        alert('فشل في تبديل الكاميرا');
        currentCameraIndex = (currentCameraIndex - 1 + availableCameras.length) % availableCameras.length;
        initializeCamera();
    }
}

function refreshCamera() {
    initializeCamera();
}

// --- دوال التأثيرات الصوتية ---

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

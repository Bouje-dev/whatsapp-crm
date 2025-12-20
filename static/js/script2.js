


// update order from server
$(document).ready(function () {

    flatpickr("#start-date-filter", {
    dateFormat: "Y-m-d", // هذا التنسيق (سنة-شهر-يوم) يسهل التعامل معه في Django
    altInput: true, // لإظهار تنسيق سهل القراءة للمستخدم
    altFormat: "F j, Y", // مثال: "June 7, 2025"
    onClose: function(selectedDates, dateStr, instance) {
        // عند اختيار تاريخ، قم بتشغيل البحث تلقائياً
        // performSearch();
    }
});
flatpickr("#end-date-filter", {
    dateFormat: "Y-m-d",
    altInput: true,
    altFormat: "F j, Y",
    onClose: function(selectedDates, dateStr, instance) {
        // عند اختيار تاريخ، قم بتشغيل البحث تلقائياً
        // performSearch();
    }
});

// معالج حدث لتغيير قيمة فلتر المدة (period-filter)
$('#period-filter').on('change', function() {
    const selectedPeriod = $(this).val();
    if (selectedPeriod === 'custom') {
        $('#custom-date-range').removeClass('d-none'); // إظهار حقول التاريخ
    } else {
        $('#custom-date-range').addClass('d-none'); // إخفاء حقول التاريخ
        // مسح قيم التواريخ المخصصة عند التبديل بعيداً عن "custom"
        $('#start-date-filter').val('');
        $('#end-date-filter').val('');
    }
    // تشغيل البحث بعد تغيير فلتر المدة
    // performSearch();
});

        // Placeholder for Django's static files if this was a standalone HTML
        // function getStaticUrl(path) {
        //     return '/static/' + path; // Adjust if your static URL is different
        // }
        function updateResultsCount(count) {
    $('#orders-count').text(count); // تغيير من #results-count إلى #orders-count
}


{/* <input id="trackInput" placeholder="أدخل رقم التتبع">
<button onclick="track()">تتبع</button>
<div id="result"></div> */}

// show tracking result  injaz compny
function track( number) {
    if (number === 'None' || number === '' || number === null) {
        document.querySelector(".showInjazresult").classList.add('d-none')
        return;
    }
    // else {
    //     document.querySelector(".showInjazresult").classList.remove('d-none')
    //     document.querySelector(".showInjazresult").innerHTML = ''; 
    //      document.querySelector(".showInjazresult").classList.add('d-flex')
    //   }
    const container = document.getElementById("tracking_info");
     
    container.innerHTML=`<div id="settings_loader" class="loading-overlay">
    <div class="text-center">
        <div class="spinner-border text-primary mb-3" style="width: 3rem; height: 3rem;" role="status"></div>
        <h6 class="text-white mt-2">Loading Configurations...</h6>
    </div>
</div>`

const loader = document.getElementById("settings_loader");
const continer = document.getElementById("showInjazresult");


  console.log("Tracking number:", number);
  const data = new URLSearchParams()
  data.append("order", number)

  fetch("/track-order", {
    method: "POST",
    body: data
  })
//   .then(r => r.text())
   
  .then(response => response.json()).then(respo => {
 
    //  = JSON.parse(res);
    res = respo.data
    
    
    if (res.tracking_company == 'Naqel') {
        
         
        const status = res.order_status; 
        // لنفترض أننا استخرجنا التاريخ من الجدول في الصورة ووضعناه في مصفوفة
// مثال للبيانات القادمة من الـ Scraper بناءً على صورتك
const historyLog = res.timeline;

// 1. حساب عدد المحاولات الفاشلة
// نبحث عن كلمة "attempted" أو "Refused"
const failedAttempts = historyLog.filter(status => 
    status.toLowerCase().includes("attempted") || 
    status.toLowerCase().includes("refused") ||
    status.toLowerCase().includes("customer not available")
).length;

// 2. تحديد "نبرة الحديث" (Script Tone) بناءً على العدد
let urgencyConfig = {};

if (failedAttempts === 0) {
    urgencyConfig = {
        level: 'low',
        badge: 'First Attempt',
        color: 'success',
        script: "مرحباً، معك [اسم الشركة]. نود تأكيد عنوانك وموعد التوصيل المناسب لضمان وصول طلبك."
    };
} else if (failedAttempts >= 1 && failedAttempts < 3) {
    urgencyConfig = {
        level: 'medium',
        badge: `${failedAttempts} Failed Attempts`,
        color: 'warning',
        script: `مرحباً، لقد حاول المندوب توصيل طلبك ${failedAttempts} مرات ولم يتمكن من الوصول إليك. نرجو الرد لتفادي استرجاع الطلب.`
    };
} else {
    // 3 محاولات أو أكثر (حالة حرجة)
    urgencyConfig = {
        level: 'high',
        badge: `CRITICAL: ${failedAttempts} Attempts!`,
        color: 'danger',
        script: "مرحباً، هذه المحاولة الأخيرة قبل إلغاء طلبك واسترجاعه للمستودع. يرجى تأكيد الاستلام فوراً."
    };
}

// 3. تصميم البطاقة الذكية (تضاف قبل بطاقة الحالة)
const insightsCard = `
<div class="card border-${urgencyConfig.color} mb-3 shadow-sm" style="height:auto;">
    <div class="card-body">
        <div class="d-flex justify-content-between align-items-center mb-2">
            <h6 class="fw-bold text-secondary m-0"><i class="fas fa-chart-line me-2"></i> Delivery Insights</h6>
            <span class="badge bg-${urgencyConfig.color} rounded-pill">${urgencyConfig.badge}</span>
        </div>
        
        <div class="progress mb-3" style="height: 10px;">
            <div class="progress-bar bg-${urgencyConfig.color} progress-bar-striped progress-bar-animated" 
                 role="progressbar" 
                 style="width: ${Math.min(failedAttempts * 33, 100)}%">
            </div>
        </div>

        <div class="bg-light p-2 rounded border border-${urgencyConfig.color} border-opacity-25">
            <small class="text-uppercase text-muted fw-bold" style="font-size: 10px;">Suggested Script (Agent):</small>
            <p class="mb-0 mt-1 fst-italic text-dark small">
                <i class="fas fa-comment-alt me-2 text-${urgencyConfig.color}"></i> "${urgencyConfig.script}"
            </p>
        </div>

        <div class="mt-2 small text-muted">
            Most recent issue: <span class="fw-bold text-danger">${historyLog[1] || 'None'}</span>
        </div>
    </div>
</div>
`;

// إدراج البطاقة في الصفحة
// document.getElementById("tracking_info").insertAdjacentHTML('afterbegin', insightsCard);






        // =============================================
        // 🔥 خريطة الإعدادات لكل حالة (Configuration Map) 🔥
        // =============================================
        const statusConfig = {
            'delivered': {
                color: 'success', // أخضر
                text_color: 'text-white',
                icon: 'fa-check-circle',
                title: 'Delivered Successfully',
                desc: 'Great news! The shipment has been successfully delivered to the customer.',
                action: '<i class="fas fa-check me-1"></i> Order Completed. No further action needed.'
            },
            'out_for_delivery': {
                color: 'info', // أزرق فاتح
                text_color: 'text-white',
                icon: 'fa-shipping-fast',
                title: 'Out for Delivery',
                desc: 'The shipment is currently with the driver and on its way to the customer.',
                action: '<strong>Monitor:</strong> Ensure the customer answers the phone. Follow up if not delivered by evening.'
            },
            'shipped': {
                color: 'primary', // أزرق غامق
                text_color: 'text-white',
                icon: 'fa-truck-moving',
                title: 'In Transit',
                desc: 'Shipment has been picked up and is moving through Naqel network.',
                action: 'Tracking is active. Check estimated delivery date.'
            },
            'exception': {
                color: 'warning', // أصفر
                text_color: 'text-dark',
                icon: 'fa-exclamation-triangle',
                title: 'Delivery Attempt Failed',
                desc: 'The driver tried to deliver but failed. The item is currently stored at the facility.',
                action: '<strong>Action Required:</strong> Contact customer immediately to confirm location or reschedule before it returns!'
            },
            'returned': {
                color: 'danger', // أحمر
                text_color: 'text-white',
                icon: 'fa-undo-alt',
                title: 'Returned to Merchant',
                desc: 'The shipment could not be delivered and has been returned to your warehouse.',
                action: 'Check the reason for return and process the refund or re-shipment if necessary.'
            },
            'canceled': {
                color: 'secondary', // رمادي
                text_color: 'text-white',
                icon: 'fa-ban',
                title: 'Canceled Shipment',
                desc: 'This shipment has been canceled.',
                action: 'No actions available for canceled shipments.'
            },
            'pending': {
                color: 'light', // فاتح جداً
                text_color: 'text-dark',
                icon: 'fa-clock',
                title: 'Pending / Created',
                desc: 'Shipment info received, waiting for pickup.',
                action: 'Ensure the package is ready for the courier.'
            }
        };

        // 3. اختيار الإعدادات المناسبة
        // إذا جاءت حالة غير معروفة، نستخدم 'pending' كاحتياط
        const config = statusConfig[status] || statusConfig['pending'];
        
        // النص الخام من الشركة (أو نضع نصاً افتراضياً من الإعدادات)
        const rawStatusText = res.raw_status || res.order_status;

        // 4. بناء الـ HTML الديناميكي
        container.innerHTML = `
        <div class="card border-${config.color} mb-3 shadow-sm">
            <div class="card-header bg-${config.color} ${config.text_color} fw-bold">
                <i class="fas ${config.icon} me-2"></i> ${config.title}
            </div>
            
            <div class="card-body" style="height: 300px;overflow: auto;">
 <div class="d-flex justify-content-between text-center mb-3 bg-light rounded-3 p-2 border">
    
    <div class="px-2 border-end">
        <div class="text-muted small text-uppercase" style="font-size: 10px;">Shipment No</div>
        <div class="fw-bold text-dark font-monospace mt-1" style="font-size: 0.9rem;">${res.order_number}</div>
    </div>

    <div class="px-2 border-end">
        <div class="text-muted small text-uppercase" style="font-size: 10px;">Destination</div>
        <div class="fw-bold text-dark mt-1" style="font-size: 0.9rem;">${res.destination}</div>
    </div>

    <div class="px-2">
        <div class="text-muted small text-uppercase" style="font-size: 10px;">Expected</div>
        <div class="fw-bold text-primary mt-1" style="font-size: 0.9rem;">
            ${res.expected_delivery ? res.expected_delivery : '--'}
        </div>
    </div>
</div>

${insightsCard}
                <div class="mt-3">
                    <h6 class="card-title fw-bold text-${config.color === 'light' ? 'dark' : config.color}">
                        ${config.desc}
                    </h6>
                    
                    <div class="alert alert-${config.color === 'light' ? 'secondary' : config.color} bg-opacity-10 border-${config.color} small mt-2">
                        ${config.action}
                    </div>

                    <div class="text-end text-muted fst-italic small mt-2 border-top pt-1">
                        Status from Naqel: "${rawStatusText}"
                    </div>
                </div>
            </div>
        </div>
        `;
    }

    // 5. تنظيف واجهة إنجاز (كما طلبت)
    const injazContainer = document.querySelector(".showInjazresult");
    if (injazContainer) {
        // استخدام Optional Chaining (?.) لتجنب الأخطاء إذا لم يوجد العنصر
        injazContainer.querySelector('.footer')?.remove();
        injazContainer.querySelector('.img')?.remove();
        
        const wrap = injazContainer.querySelector('.wrap');
        if (wrap) {
            wrap.style.borderRadius = '6px';
            wrap.style.boxShadow = 'none'; // تحسين إضافي اختياري
        }
    }
})
.catch(error => {
    console.error('Tracking Error:', error);
    document.getElementById("tracking_info").innerHTML = `
        <div class="alert alert-danger small">
            <i class="fas fa-times-circle me-1"></i> Failed to load tracking info.
        </div>`;
});

  
}







let currentIframeLoadedUrl = '';

        let currentTrackingNumber = '';
        let currentCompany = '';

        // Function to show specific section
        function showSection(sectionId) {
            $('.section-content').removeClass('active'); // Hide all sections
            $('#' + sectionId).addClass('active'); // Show target section

            $('.page-tabs-nav .nav-link').removeClass('active'); // Deactivate all nav links
            $(`.page-tabs-nav .nav-link[data-section="${sectionId}"]`).addClass('active'); // Activate current nav link
        }

        // Function to update the tracking iframe
    // افتراض: المتغيرات التالية معرفة في مكان أعلى كمتغيرات عالمية:
// let currentCompany = null;
// let currentTrackingNumber = null;
// let currentIframeLoadedUrl = null;

function updateTrackingFrame(trackingNumber, company) {
    try {
        // تنظيف القيمة الواردة
        if (trackingNumber === undefined || trackingNumber === null) trackingNumber = "";
        trackingNumber = String(trackingNumber).trim();

        // العناصر الأساسية
        const iframe = document.getElementById('tracking-iframe');
        const container = iframe ? iframe.closest('.iframe-container') : document.querySelector('.iframe-container');
        const initialMsgEl = document.getElementById('initial-iframe-message');
        const currentTrackingNumberDisplay = document.getElementById('current-tracking-number');

        // مساعدة: عرض رسالة ابتدائية / خطأ
        const showInitialMessage = (html) => {
            if (initialMsgEl) {
                initialMsgEl.innerHTML = html;
                initialMsgEl.classList.remove('d-none');
            } else if (container) {
                // كاحتياط، عرض داخل الحاوية
                container.innerHTML = html;
            }
        };

        const hideInitialMessage = () => {
            if (initialMsgEl) initialMsgEl.classList.add('d-none');
        };

        const showContainerMessage = (html) => {
            if (container) {
                container.classList.remove('iframe-loading');
                // لا نُبدّل الحاوية كاملة إن كانت تحتوي iframe — لكن إذا لا يوجد iframe نعرض الرسالة
                if (!iframe) container.innerHTML = html;
                else {
                    // إن أردنا الإبقاء على الiframe في DOM، نعرض الرسالة بعد فحص
                    const msgWrapper = container.querySelector('.tracking-message-wrapper');
                    if (msgWrapper) msgWrapper.innerHTML = html;
                    else {
                        const div = document.createElement('div');
                        div.className = 'tracking-message-wrapper';
                        div.innerHTML = html;
                        container.appendChild(div);
                    }
                }
            } else {
                console.warn('No container to show message');
            }
        };

        // حالة عدم وجود رقم تتبع
        if (!trackingNumber || trackingNumber.toLowerCase() === 'none') {
            showInitialMessage(`
                <div class="no-tracking-selected text-center">
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Tracking for this number is not supported or order in progress.</p>
                    <p style="color: var(--accent-color); font-weight: 600; font-size: var(--font-size-sm);">${trackingNumber || '—'}</p>
                </div>
            `);
            // إخفاء iframe إن وُجد
            if (iframe) iframe.classList.add('d-none');
            if (currentTrackingNumberDisplay) currentTrackingNumberDisplay.textContent = 'Not Selected';
            currentCompany = null;
            currentTrackingNumber = null;
            currentIframeLoadedUrl = null;
            return;
        }

        // التأكد من وجود الحاوية
        if (!container) {
            console.error('iframe container not found');
            return;
        }

        // تحديد الشركة إن لم تُمرّر
        if (!company || company === 'unknown') {
            console.log('imile' , trackingNumber);
            if (/^6/.test(trackingNumber)) {
                
                company = 'imile';
            } else if (/^INJAZ/.test(trackingNumber) || /^INJAZ/.test(trackingNumber.toUpperCase())) {
                company = 'injaz';
            } else if (/^ALSASAF/.test(trackingNumber.toUpperCase())) {
                company = 'ALSASAF';
            } else if (/^3/.test(trackingNumber)) {
                company = 'naqelksa';
            } else {
                // تنبيه للمستخدم أن التنسيق غير معروف
                showContainerMessage(`
                    <div class="no-tracking-selected text-center">
                        <i class="fas fa-exclamation-circle"></i>
                        <p>Tracking for this number is not supported or format is unknown.</p>
                        <p style="color: var(--accent-color); font-weight: 600; font-size: var(--font-size-sm);">${trackingNumber}</p>
                    </div>
                `);
                if (currentTrackingNumberDisplay) currentTrackingNumberDisplay.textContent = 'Error';
                return;
            }
        }

        // إذا لم يتغير شيء، لا نعيد التحميل
        if (company === currentCompany && trackingNumber === currentTrackingNumber) {
            // إعادة إظهار iframe إذا كان مخفيًا فقط
            if (iframe && iframe.classList.contains('d-none')) {
                iframe.classList.remove('d-none');
            }
            return;
        }

        // تحديث الواجهة: إظهار التحميل
        hideInitialMessage();
        if (iframe) {
            iframe.classList.remove('d-none');
        }
        container.classList.add('iframe-loading');

        // تحديث القيم الحالية
        currentCompany = company;
        currentTrackingNumber = trackingNumber;
        if (currentTrackingNumberDisplay) currentTrackingNumberDisplay.textContent = trackingNumber;

        // بناء الرابط أو تنفيذ track() بحسب الشركة
        let newUrl = "";
        let useIframe = true; // هل نستخدم iframe أم نستخدم دالة track()
        if (company === 'imile') {
            // رابط تتبع مع باراميتر
            newUrl = `https://www.imile.com/AE-en/track?waybillNo=${encodeURIComponent(trackingNumber)}`;
            // نريد تحميل الصفحة وملء النموذج بعد التحميل
            useIframe = true;
        } else if (company === 'naqelksa') {
            // نستخدم دالة داخلية 'track' (كما في كودك) بدلاً من iframe
            useIframe = false;
           
            try { track(trackingNumber); } catch (e) { console.error('track() failed', e); }
            // newUrl='https://new.naqelksa.com/en/sa/tracking/'
            // useIframe = true;
            
            if (iframe) iframe.classList.add('d-none');
            container.classList.remove('iframe-loading');
            currentIframeLoadedUrl = null;
            return;
        } else if (company === 'injaz') {
            // نفترض أن injaz يتم عبر track() أيضاً
            useIframe = false;
            try { track(trackingNumber); } catch (e) { console.error('track() failed', e); }
            if (iframe) iframe.classList.add('d-none');
            container.classList.remove('iframe-loading');
            currentIframeLoadedUrl = null;
            return;
        } else if (company === 'ALSASAF') {
            newUrl = `https://gecko.logistiq.io/#/order/tracking?awb=${encodeURIComponent(trackingNumber)}`;
            useIframe = true;
        } else {
            // افتراضي: إخفاء iframe والعرض رسالة
            useIframe = false;
            showContainerMessage(`
                <div class="no-tracking-selected text-center">
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Tracking for this company is not supported.</p>
                    <p>${company}</p>
                </div>
            `);
            if (iframe) iframe.classList.add('d-none');
            container.classList.remove('iframe-loading');
            return;
        }

        // تحميل الرابط داخل iframe إن لزم
        if (useIframe) {
            if (!iframe) {
                // لو لا يوجد iframe، نصنع واحد مؤقت داخل الحاوية
                const newIframe = document.createElement('iframe');
                newIframe.id = 'tracking-iframe';
                newIframe.style.width = '100%';
                newIframe.style.height = '600px';
                newIframe.setAttribute('frameborder', '0');
                container.appendChild(newIframe);
            }

            // لا نعيد تحميل نفس الرابط
            if (newUrl && newUrl !== currentIframeLoadedUrl) {
                const frame = document.getElementById('tracking-iframe');
                // راقب حدث التحميل
                let loadTimer = null;
                const onLoaded = () => {
                    container.classList.remove('iframe-loading');
                    // تنفيذ أي اكتمال مخصص
                    if (company === 'imile' && typeof fillImileForm === 'function') {
                        try { fillImileForm(trackingNumber); } catch (e) { console.error('fillImileForm error', e); }
                    }
                    if (loadTimer) { clearTimeout(loadTimer); loadTimer = null; }
                    frame.removeEventListener('load', onLoaded);
                };
                const onError = () => {
                    container.classList.remove('iframe-loading');
                    showContainerMessage(`
                        <div class="no-tracking-selected">
                            <i class="fas fa-times-circle"></i>
                            <p>Failed to load tracking page for ${company}. Please try again later.</p>
                        </div>
                    `);
                    if (loadTimer) { clearTimeout(loadTimer); loadTimer = null; }
                    frame.removeEventListener('load', onLoaded);
                };

                // const frame = document.getElementById('tracking-iframe');
                frame.addEventListener('load', onLoaded, { once: true });

                // fallback: إن لم يحمل الإطار خلال X ثانية نعرض خطأ
                loadTimer = setTimeout(() => {
                    // إزالة listener واظهار رسالة خطأ
                    frame.removeEventListener('load', onLoaded);
                    onError();
                }, 15000); // 15s timeout

                // تغيير المصدر أخيراً
                try {
                    frame.src = newUrl;
                    currentIframeLoadedUrl = newUrl;
                } catch (e) {
                    console.error('Failed to set iframe src', e);
                    onError();
                }
            } else {
                // نفس الرابط — فقط أزل حالة التحميل
                container.classList.remove('iframe-loading');
            }
        }

    } catch (err) {
        console.error('updateTrackingFrame error:', err);
        // عرض رسالة عامة
        const container = document.querySelector('.iframe-container');
        if (container) {
            container.classList.remove('iframe-loading');
            const html = `
                <div class="no-tracking-selected text-center">
                    <i class="fas fa-exclamation-circle"></i>
                    <p>Unexpected error occurred while updating tracking frame.</p>
                    <p>${err.message || err}</p>
                </div>
            `;
            container.innerHTML = html;
        }
    }
}


        // Function to attempt filling iMile form (cross-origin issues apply)
        function fillImileForm(trackingNumber) {
            setTimeout(function() {
                try {
                    var iframe = document.getElementById('tracking-iframe');
                    if (iframe.contentDocument && iframe.contentDocument.readyState === 'complete' && iframe.contentWindow.location.href.includes("imile.com")) {
                        var iframeDoc = iframe.contentDocument || iframe.contentWindow.document;

                        var inputField = iframeDoc.querySelector('input[placeholder="Enter your tracking number"], input[name="q"], input[type="text"][class*="track-input"]');
                        var trackButton = iframeDoc.querySelector('button[type="submit"], button[aria-label="Track"]');

                        if (inputField) {
                            inputField.value = trackingNumber;
                            var event = new Event('input', { bubbles: true }); // Trigger input event
                            inputField.dispatchEvent(event);
                            console.log("iMile input field filled.");
                        } else {
                            console.warn("iMile tracking input field not found.");
                        }

                        if (trackButton) {
                            trackButton.click();
                            console.log("iMile track button clicked.");
                        } else {
                            console.warn("iMile track button not found.");
                        }

                        if (!inputField && !trackButton) {
                            console.log("Could not find any iMile form elements within the iframe.");
                            displayManualTrackingMessage(trackingNumber);
                        }
                    } else {
                        displayManualTrackingMessage(trackingNumber);
                    }
                } catch (e) {
                    console.warn("Error accessing iframe content (likely due to cross-origin policy):", e);
                    displayManualTrackingMessage(trackingNumber);
                }
            }, 3000); // Increased timeout for better stability
        }

        // Helper to display message for manual tracking
        function displayManualTrackingMessage(trackingNumber) {
            const container = document.getElementById('tracking-iframe').closest('.iframe-container');
            if (container && !container.querySelector('.no-tracking-selected')) {
                container.innerHTML = `
                    <div class="no-tracking-selected">
                        <i class="fas fa-shield-alt"></i>
                        <p>Due to security policies, we cannot directly interact with this tracking site.</p>
                        <p>Please visit the tracking website and enter the number manually:</p>
                        <p style="color: var(--accent-color); font-weight: 600; font-size: var(--font-size-sm);">${trackingNumber}</p>
                    </div>
                `;
            }
        }


        // Function to copy text to clipboard
        function copyToClipboard(text, iconElement) {
            navigator.clipboard.writeText(text).then(() => {
                if (iconElement) {
                    iconElement.removeClass('fa-copy').addClass('fa-check');
                    setTimeout(() => {
                        iconElement.removeClass('fa-check').addClass('fa-copy');
                    }, 1500);
                }
                Swal.fire({
                    icon: 'success',
                    title: 'Copied!',
                    toast: true,
                    position: 'top-end',
                    showConfirmButton: false,
                    timer: 1500,
                    background: 'var(--accent-color)',
                    color: 'var(--background-primary)',
                    iconColor: 'var(--background-primary)',
                    customClass: {
                        popup: 'swal2-custom-popup',
                        title: 'swal2-custom-title'
                    },
                    didOpen: (toast) => {
                        toast.addEventListener('mouseenter', Swal.stopTimer)
                        toast.addEventListener('mouseleave', Swal.resumeTimer)
                    }
                });
            }).catch(err => {
                console.error('Failed to copy text: ', err);
                Swal.fire({
                    icon: 'error',
                    title: 'Copy Failed!',
                    text: 'Could not copy tracking number. Please try again or copy manually.',
                    background: 'var(--background-primary)',
                    color: 'var(--text-light)',
                    confirmButtonColor: 'var(--accent-color)'
                });
            });
        }


        $(document).ready(function() {
            // Initial load: show order tracking section
            // showSection('order-tracking-section');

            // Page Tabs navigation link handler
            $('.page-tabs-nav .nav-link').on('click', function(e) {
                e.preventDefault();
                const targetSectionId = $(this).data('section');
                showSection(targetSectionId);
            });

            // Handle initial order item selection on page load if orders exist
            // const firstOrderItem = document.querySelector('.order-row');
            // if (firstOrderItem) {
            //     $('#initial-orders-message').addClass('d-none'); // Hide initial message if orders exist
            //     $('.custom-table').removeClass('d-none'); // Show table
            //     firstOrderItem.classList.add('active'); // Highlight first item
            //     updateTrackingFrame(firstOrderItem.getAttribute('data-tracking'), firstOrderItem.getAttribute('data-company'));
            // } else {
            //     // If no orders (Django context), show the no-orders message
            //     $('#search-results-container').html(`
            //         <div class="no-orders-message" id="initial-orders-message">
            //             <i class="fas fa-info-circle"></i>
            //             <h5>No Orders Found</h5>
            //             <p>Start by searching or click an item to view details.</p>
            //         </div>
            //     `);
            // }
// Handle initial order item selection on page load if orders exist
            const firstOrderItem = document.querySelector('.order-row');
            if (firstOrderItem) {
                $('#initial-orders-message').addClass('d-none'); // Hide initial message if orders exist
                // No need to show table, as it's always there within its card
                firstOrderItem.classList.add('active'); // Highlight first item

                // Set initial customer info display
                $('#customer-name-display').text(firstOrderItem.getAttribute('data-customer-name') || 'N/A');
                $('#customer-phone-display').text(firstOrderItem.getAttribute('data-customer-phone') || 'N/A');
                $('#product-name-display').text(firstOrderItem.getAttribute('data-product-name') || 'N/A');
  function saveWhatsappActivity(phoneNumber) {
                    $.ajax({
                        url: '/tracking/save_activity_tracking/', // استبدل هذا بالرابط الصحيح في Django
                        type: 'POST',
                        data: {
                            phone: phoneNumber,
                            csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').val()
                        },
                        success: function(response) {
                            // يمكنك عرض رسالة نجاح أو تنفيذ أي إجراء آخر هنا
                            console.log('تم حفظ نشاط الواتساب بنجاح');
                        },
                        error: function(xhr) {
                            // يمكنك عرض رسالة خطأ هنا
                            console.error('فشل حفظ نشاط الواتساب');
                        }
                    });

                }  
                const initialPhone = firstOrderItem.getAttribute('data-customer-phone');
                const whatsappLink = $('#whatsapp-link');
                if (initialPhone && initialPhone !== 'N/A') {
                     whatsappLink.on('click', function () {
        saveWhatsappActivity(initialPhone);
    });
                     whatsappLink.attr('href', `https://web.whatsapp.com/send/?phone=${initialPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0`);
                    // whatsappLink.attr('target', 'whatsapp_web_window'); // هذا هو التعديل

                    whatsappLink.removeClass('d-none');
                } else {
                    whatsappLink.addClass('d-none');
                }

                // updateTrackingFrame(firstOrderItem.getAttribute('data-tracking') , firstOrderItem.getAttribute('data-company'));
            } else {
                // If no orders (Django context), show the no-orders message inside the table card
                $('#search-results-container .card-body').html(`
                    <div class="no-orders-message" id="initial-orders-message">
                        <i class="fas fa-info-circle"></i>
                        <h5>No Orders Found</h5>
                        <p>Start by searching or click an item to view details.</p>
                    </div>
                `);
                // Reset customer info to "Not Selected" if no orders
                $('#customer-name-display').text('Not Selected');
                $('#customer-phone-display').text('Not Selected');
                $('#product-name-display').text('Not Selected');
                $('#current-tracking-number').text('Not Selected');
                $('#whatsapp-link').addClass('d-none'); // Hide WhatsApp button
            }

            // Event listener for clicking on order items
            // $(document).on('click', '.order-row', function() {
            //     $('.order-row').removeClass('active'); // Remove active from all
            //     $(this).addClass('active'); // Add active to clicked item

            //     const trackingNumber = $(this).data('tracking');
            //     const company = $(this).data('company');
            //     updateTrackingFrame(trackingNumber, company); // Update iframe
            // });
            $(document).on('click', '.order-row', function() {
                $('.order-row').removeClass('active'); // Remove active from all
                $(this).addClass('active'); // Add active to clicked item

                const trackingNumber = $(this).data('tracking');
                const company = $(this).data('company');
                const customerName = $(this).data('customer-name') || 'N/A'; // Get customer name
                const customerPhone = $(this).data('customer-phone') || 'N/A'; // Get customer phone
                const productName = $(this).data('product-name') || 'N/A'; // Get product name

                // Update customer info display
                $('#customer-name-display').text(customerName);
                $('#customer-phone-display').text(customerPhone);
                $('#product-name-display').text(productName);

                // Update WhatsApp link
                const whatsappLink = $('#whatsapp-link');
                if (customerPhone && customerPhone !== 'N/A') {
  whatsappLink.on('click', function () {
        saveWhatsappActivity(initialPhone);
    });                    // https://web.whatsapp.com/send/?phone=${customerPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0
                    //  whatsappLink.attr('href', `https://web.whatsapp.com/send/?phone=${customerPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0`); // Remove spaces from phone number
                    // // whatsappLink.attr('target', 'whatsapp_web_window'); // Set target to open in WhatsApp Web
                    whatsappLink.removeClass('d-none'); // Show button
                } else {
                    whatsappLink.addClass('d-none'); // Hide button if no phone
                }


                updateTrackingFrame(trackingNumber, company); // Update iframe
            });


            // Copy button click handler
            $(document).on('click', '.copy-btn', function(e) {
                e.stopPropagation(); // Prevent order-row click from firing
                const trackingNum = $(this).data('tracking');
                copyToClipboard(trackingNum, $(this).find('i'));
            });

            let currentPage = 1;



            // Live search functionality
            function performSearch(pageNumber = 1) {
                const searchTerm = $('#live-search-input').val().trim();
                const csrfToken = $('input[name="csrfmiddlewaretoken"]').val(); // Get CSRF token
                const statusFilter = $('#status-filter').val(); // استخراج قيمة فلتر الحالة
                const companyFilter = $('#company-filter').val(); // استخراج قيمة فلتر الشركة
                const productFilter = $('#product-filter').val(); // استخراج قيمة فلتر المنتج (إذا كان موجوداً)
                const periodFilter = $('#period-filter').val(); // الحصول على قيمة فلتر المدة

                let startDate = '';
                let endDate = '';

    // إذا تم اختيار "custom"، احصل على قيم التواريخ من الحقول
                if (periodFilter === 'custom') {startDate = $('#start-date-filter').val();endDate = $('#end-date-filter').val();}


                console.log('data' + statusFilter + companyFilter + productFilter )
                if (!csrfToken) {
                    console.error("CSRF token not found. AJAX requests may fail.");
                    Swal.fire({
                        icon: 'error',
                        title: 'Configuration Error',
                        text: 'CSRF token is missing. Please ensure your Django setup is correct.',
                        background: 'var(--background-primary)',
                        color: 'var(--text-light)',
                        confirmButtonColor: 'var(--accent-color)'
                    });
                    return;
                }

                // Show loading spinner
                $('#settablehere').html(`
                    <div class="text-center py-5">
                        <div class="spinner-border text-primary" role="status" style="color: var(--accent-color);">
                            <span class="visually-hidden">Searching...</span>
                        </div>
                        <p class="text-muted mt-3" style="font-size: var(--font-size-sm);">Searching orders...</p>
                    </div>
                `);
                     currentPage = pageNumber;

                $.ajax({
                    url: '/tracking/orders/', // You MUST replace this with your actual Django URL for order search!
                    type: 'POST',
                    data: {

                        'search_term': searchTerm,
                        'status': statusFilter,
                        'company': companyFilter,
                        'product': productFilter,
                        'page': currentPage, // إرسال رقم الصفحة
                        'csrfmiddlewaretoken': csrfToken,
                        'period': periodFilter,    // إرسال فلتر المدة
                        'start_date': startDate,   // إرسال تاريخ البداية
                        'end_date': endDate,
                    },
                          headers: {
            'X-Requested-With': 'XMLHttpRequest'
                      },

                    success:
                    function(response) {
                        // if(response.success){
                        if (response.success && response.html.trim() !== '') {
                             $('#settablehere').html(`
     <div class="table-responsive">
                <table class="table custom-table mb-0">
                    <thead>
                        <tr>
                            <th width="18%" class="ps-3">
                                <i class="fas fa-barcode me-1"></i>
                                Tracking Number
                            </th>
                            <th width="22%">
                                <i class="fas fa-user me-1"></i>
                                Customer
                            </th>
                            <th width="18%">
                                <i class="fas fa-phone me-1"></i>
                                Phone
                            </th>
                            <th width="25%">
                                <i class="fas fa-cube me-1"></i>
                                Product
                            </th>
                            <th width="10%" class="text-center">
                                <i class="fas fa-info-circle me-1"></i>
                                Status
                            </th>
                               <th width="17%" class="text-center  {% if request.user.is_is_team_admin %}d-none{% endif %}">
                                                        <i class="fas fa-info-circle me-1"></i>
                                                        Price
                                                    </th>
                        </tr>
                                        </thead>
                                        <tbody>
                                            ${response.html}
                                        </tbody>
                                    </table>
                                                ${response.pagination_html}

                                </div>

                             `);
                                            //  $('#p').html(combinedHtmlContent);

                        } else {
                            $('#settablehere').html(`
                                <div class="no-orders-message">
                                    <i class="fas fa-exclamation-triangle"></i>
                                    <h5>No Orders Found</h5>
                                    <p>Your search did not match any orders.</p>
                                </div>

                            `);
                                            $('#pagination-controls-container').empty();

                        }

                        // Re-apply active state if the currently tracked item is in the new results
                        if (currentTrackingNumber) {
                            $(`.order-row[data-tracking="${currentTrackingNumber}"]`).addClass('active');
                        }
                                    updateResultsCount(response.count);

                    },
                    error: function(xhr)  {
            $('#loading-spinner').addClass('d-none');
            $('#search-results-container').removeClass('d-none'); // إظهار الحاوية لإظهار رسالة الخطأ
            $('#search-results-container').html(`
                <div class="alert alert-danger" role="alert" style="background-color: var(--status-danger); color: white; border-color: var(--status-danger); padding: 1.5rem; border-radius: var(--border-radius-md); font-size: var(--font-size-sm);">
                    <i class="fas fa-exclamation-triangle me-2"></i> An error occurred during search: ${xhr.statusText || 'Unknown error'}. Please check your network and try again.
                </div>
            `);
            $('#pagination-controls-container').empty(); // إزالة الـ pagination عند الخطأ
            console.error("AJAX error:", xhr);
        }
                });
            }

            let searchTimeout;
            $('#live-search-input').on('input', function() {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(performSearch, 500);
            });

            $('#search-btn').on('click', function(e) {
                e.preventDefault();
                performSearch();
            });
            $('#apply-filters-btn').on('click', function(e) {
                e.preventDefault();
                performSearch();
            });


            $('#live-search-input').keypress(function(e) {
                if (e.which === 13) {
                    e.preventDefault();
                    performSearch();
                }
            });

            $(document).on('click', '#search-results-container .page-link', function(e) {
    e.preventDefault(); // منع السلوك الافتراضي للرابط (عدم إعادة تحميل الصفحة)
    const newPage = $(this).data('order-page'); // الحصول على رقم الصفحة من data-page
    if (newPage) { // التأكد من وجود رقم الصفحة
        performSearch(newPage); // استدعاء دالة البحث بالصفحة الجديدة
    }
});


            // SKU Update form submission (example - replace with your actual Django URL)
            $('#update-sku-form').on('submit', function(e) {
                e.preventDefault();
                const form = $(this);
                const formData = form.serialize();
                const submitBtn = form.find('button[type="submit"]');

                submitBtn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...');

                $.ajax({
                    url: '/update-product-data/', // You MUST replace this with your actual Django URL for product update!
                    type: 'POST',
                    data: formData,
                    success: function(response) {
                        if (response.success) {
                            Swal.fire({
                                icon: 'success',
                                title: 'Success!',
                                text: 'Product data updated successfully.',
                                background: 'var(--accent-color)',
                                color: 'var(--background-primary)',
                                confirmButtonColor: 'var(--accent-color)'
                            });
                            $('#last-update-date').text(response.last_update_date || new Date().toLocaleString());
                        } else {
                            Swal.fire({
                                icon: 'error',
                                title: 'Error!',
                                text: response.message || 'Failed to update product data.',
                                background: 'var(--background-primary)',
                                color: 'var(--text-light)',
                                confirmButtonColor: 'var(--accent-color)'
                            });
                        }
                    },
                    error: function(xhr) {
                        Swal.fire({
                            icon: 'error',
                            title: 'Error!',
                            text: 'An error occurred: ' + (xhr.responseJSON ? xhr.responseJSON.message : xhr.statusText),
                            background: 'var(--background-primary)',
                            color: 'var(--text-light)',
                            confirmButtonColor: 'var(--accent-color)'
                        });
                    },
                    complete: function() {
                        submitBtn.prop('disabled', false).html('<i class="fas fa-sync-alt me-2"></i> Update Data');
                    }
                });
            });

        });


























// <!-- product update script  -->

$('#proupdate').click(function() {
    var $btn = $(this);
    $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...');
    $.ajax({
        url: '/tracking/update_product/', // ضع هنا رابط Django الصحيح لتحديث المنتجات
        type: 'POST',
        data: {
            csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').val()
        },
        success: function(response) {
            $btn.html('<i class="fas fa-check"></i> Updated!');
            setTimeout(function() {
                location.reload();
            }, 1200);
        },
        error: function() {
            $btn.html('<i class="fas fa-times"></i> Error');
            setTimeout(function() {
                $btn.prop('disabled', false).html('<i class="fas fa-plus me-1"></i> Add Product');
            }, 2000);
        }
    });
});











// I do not know why this code here but we need it

        document.addEventListener('DOMContentLoaded', function() {
    // تحديد الروابط الحالية
    const currentPath = window.location.pathname;

    // تحديث حالة النشطة بناء على المسار الحالي
    document.querySelectorAll('.nav_link[href]').forEach(link => {
        // إزالة الفئة النشطة من جميع الروابط
        link.classList.remove('active');

        // التحقق إذا كان رابط التنقل يطابق المسار الحالي
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }

        // إضافة معالج الحدث للنقر
        link.addEventListener('click', function(e) {
            // منع السلوك الافتراضي إذا كان رابطًا حقيقيًا
            if (this.getAttribute('href').startsWith('http')) {
                e.preventDefault();
            }

            // تحديث الحالة النشطة
            document.querySelectorAll('.nav_link').forEach(l => l.classList.remove('active'));
            this.classList.add('active');

            // إذا كان رابطًا داخليًا، يمكنك إضافة تنقل هنا
        });
    });
});









// update codDrop products in our server


     let currentProductId = null;
    // فتح النافذة مع بيانات المنتج
    function openEditModal(productId, productName ,productimg) {
        currentProductId = productId;
        document.getElementById('modal-product-id').value = productId;
        document.getElementById('modal-product-name').value = productName;
        document.getElementById('modal-product-img').src = productimg;

        new bootstrap.Modal(document.getElementById('editProductModal')).show();
    }

    // حفظ التعديلات
    function saveProductChanges() {
        const newName = document.getElementById('modal-product-name').value.trim();
        const imageInput = document.getElementById('modal-product-image');
        const productId = document.getElementById('modal-product-id').value;

        const formData = new FormData();
        formData.append("product_id", productId);

        if (newName) {
            formData.append("name", newName);
        }

        if (imageInput.files[0]) {
            formData.append("image", imageInput.files[0]);
        }

        // إرسال البيانات للسيرفر
        fetch("/api/update-product/", {
            method: "POST",
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("تم تحديث المنتج بنجاح!");
                location.reload(); // إعادة تحميل الصفحة لتحديث العرض
            } else {
                alert("فشل في تحديث المنتج.");
            }
        })
        .catch(err => {
            console.error(err);
            alert("حدث خطأ أثناء الحفظ.");
        });
    }




// $ready(function() {



// تنسيق الوقت و عرضه ك اخر تحديث

    document.addEventListener('DOMContentLoaded', function () {
        const el = document.getElementById('last-update');
        if (el && el.dataset.datetime) {
            try {
                const isoString = el.dataset.datetime;
                const date = new Date(isoString);

                // استخراج اليوم والشهر والساعة والدقيقة
                const day = date.getDate().toString().padStart(2, '0');
                const month = (date.getMonth() + 1).toString().padStart(2, '0');
                const hours = date.getHours().toString().padStart(2, '0');
                const minutes = date.getMinutes().toString().padStart(2, '0');

                // التنسيق النهائي
                const formatted = `${day}/${month} ${hours}:${minutes}`;
                el.textContent = formatted;
            } catch (e) {
                el.textContent = '';
            }
        }
    });



// })





});








      


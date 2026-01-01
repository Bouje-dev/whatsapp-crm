/* --- Inline script #1 extracted from tracking.html --- */

document.addEventListener('DOMContentLoaded', function() {

     const comp_btn = document.querySelectorAll('.comp-btn');
    const trackingBtn = document.getElementById('tracking-comp-btn');
    const analyticsBtn = document.getElementById('comp-analytics-btn');
    const trackingInfo = document.getElementById('tracking-info-section');
    const analyticsCard = document.getElementById('analytics-card-section');

    trackingBtn.addEventListener('click', function() {
        trackingBtn.classList.add('active');
        analyticsBtn.classList.remove('active');
        trackingInfo.classList.remove('d-none');
        analyticsCard.classList.add('d-none');
    });

    analyticsBtn.addEventListener('click', function() {
        analyticsBtn.classList.add('active');
        trackingBtn.classList.remove('active');
        trackingInfo.classList.add('d-none');
        analyticsCard.classList.remove('d-none');
    });
    
comp_btn.forEach(function(btn) {
    btn.addEventListener('click', function() {
        comp_btn.forEach(function(b) {
            b.classList.remove('activecard');
            // إخفاء جميع البطاقات
            const comp_cards = document.querySelectorAll('.comp-card');
            comp_cards.forEach(function(card) {
                card.classList.add('d-none');
            });
        });
        this.classList.add('activecard');
        // إظهار البطاقة المرتبطة بالزر
        if (this.id === 'tracking-comp-btn') {
            document.querySelector('.analytics_sesty').classList.remove('d-none');

        } else if (this.id === 'comp-analytics-btn') {
            document.querySelector('.analyticscomp').classList.remove('d-none');
        }
    });
});

});



/* --- Inline script #2 extracted from tracking.html --- */

document.addEventListener('DOMContentLoaded', function () { 



    function trackCompanyData(period , product  , country) {
    console.log('Selected Period:', period , 'Product:', product, 'Country:', country);

    var table;
    let startDate = '';
    let endDate = '';

    if (period === 'custom') {
    startDate = document.getElementById('start-date-filter').value;
    endDate = document.getElementById('end-date-filter').value;
    }


    fetch('{% url "get_tracking_company_data" %}', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({period : period ,startDate:startDate , endDate:endDate , product : product , country : country})
    })
    .then(response => response.json())
    .then(data => {
        table = document.querySelector('.shipping_table');
        const orders = data.orders || [];

        function getCompany(tracking_number) {
            if (!tracking_number) return { company: 'Progress', site: '' };
            if (tracking_number.startsWith('60')) return { company: 'imile', site: 'https://www.imile.com/track/' };
            if (tracking_number.startsWith('INJAZ')) return { company: 'injaz', site: 'https://injaz-express.com/' };
            if (/^\d{7}$/.test(tracking_number)) return { company: 'bosta', site: 'https://bosta.co/tracking-shipments' };
            if (tracking_number.startsWith('JTE')) return { company: 'jtexpress', site: 'https://www.jtexpress-sa.com/' };
            if (tracking_number.startsWith('IQFTMM')) return { company: 'iqfulfillment', site: 'https://track.iqfulfillment.com/' };
            if (tracking_number.startsWith('EDCO')) return { company: 'chronodiali', site: 'https://www.chronodiali.ma/' };
            if (/^\d{11}$/.test(tracking_number)) return { company: 'aramex', site: 'https://www.aramex.com/' };
            if (tracking_number.startsWith('YCST')) return { company: 'youcan', site: 'https://ship.youcan.shop/en/' };
            if (tracking_number.startsWith('S')) return { company: 'starlinks', site: 'https://www.starlinks-me.com/' };
            if (tracking_number.startsWith('CRDSAL')) return { company: 'spl', site: 'https://splonline.com.sa/en/' };
            if (tracking_number.startsWith('SD')) return { company: 'shipa', site: 'https://shipa.com/track/' };
            if (tracking_number.startsWith('ALSASAF')) return { company: 'logistiq', site: 'https://logistiq.io/delivery-services/' };
            if (tracking_number.startsWith('FXP')) return { company: 'flowpl', site: 'https://www.flowpl.com/ship-portal/' };
            if (tracking_number.startsWith('812')) return { company: 'tawssil', site: 'https://tracking.tawssil.ma/' };
            if (tracking_number.startsWith('3')) return { company: 'naqel', site: 'https://new.naqelksa.com/en/sa/tracking/' };
            return { company: 'unknown', site: '' };
        }

        const companyNames = {
            imile: 'Imile',
            injaz: 'Injaz Express',
            bosta: 'Bosta',
            jtexpress: 'J&T Express',
            iqfulfillment: 'IQ Fulfillment',
            chronodiali: 'Chrono Diali',
            aramex: 'Aramex',
            youcan: 'YouCan Ship',
            starlinks: 'Starlinks',
            spl: 'Saudi Post SPL',
            shipa: 'Shipa Delivery',
            logistiq: 'Logistiq',
            flowpl: 'Flow PL',
            tawssil: 'Tawssil',
            naqel: 'Naqel Express' ,
            Progress:'Progress'
        };

        const stats = {};
        orders.forEach(order => {
            const compData = getCompany(order.tracking_number);
            if (!stats[compData.company]) {
                stats[compData.company] = { name: compData.company, total: 0, delivered: 0, site: compData.site };
            }
            stats[compData.company].total += 1;
            if (order.status && order.status.toLowerCase() === 'delivered') {
                stats[compData.company].delivered += 1;
            }
        });

        const companies = Object.values(stats).sort((a, b) => b.total - a.total);

        
     
// Header
let html = `<div class="shipping-stats-list" style="width:100%;margin-top:1rem;">`;

// Header
html += `
    <div class="shipping-stat-header d-flex align-items-center justify-content-between py-2 px-3" style="
        border-bottom: 2px solid var(--border-card);
        background: rgba(255,255,255,0.04);
        font-size: var(--font-size-sm);
        color: #9d9d9d;
        font-weight: 600;">
        <div style="min-width: 110px;">Company</div>
        <div style="min-width: 80px;">Total Orders</div>
        <div style="min-width: 80px;">Delivery Rate</div>
    </div>
`;

// Rows per company
companies.forEach(comp => {
    const rate = comp.total > 0 ? Math.round((comp.delivered / comp.total) * 100) : 0;
    html += `
        <div class="shipping-stat-row d-flex align-items-center justify-content-between py-3 px-3" style="
            border-bottom: 1.5px solid var(--border-card);
            background: rgba(255,255,255,0.02);
            border-radius: 0;
            font-size: var(--font-size-sm);
            color: var(--text-light);
            transition: background 0.2s;">
            <div class="fw-bold" style="color: #e0e0e0; min-width: 110px;">
                <a style="color: ${companyNames[comp.name] == 'Progress' ? '#00E676':'#e0e0e0'}; text-decoration:none;" href="${comp.site}" target="_blank">
                    ${companyNames[comp.name] || comp.name}
                </a>
            </div>
            <div style="font-weight: 500; color: var(--text-light); min-width: 80px;">
                ${comp.total}
            </div>
            <div style="font-weight: 600; color: ${rate > 70 ? '#00E676' : '#ffc107'}; min-width: 80px;">
                ${rate}%
            </div>
        </div>
    `;
});

// إجمالي الكل
let grandTotal = 0;
let grandDelivered = 0;
companies.forEach(comp => {
    grandTotal += comp.total;
    grandDelivered += comp.delivered;
});
const grandRate = grandTotal > 0 ? Math.round((grandDelivered / grandTotal) * 100) : 0;

// صف الإجمالي
html += `
    <div class="shipping-stat-footer d-flex align-items-center justify-content-between py-3 px-3" style="
        border-top: 2px solid var(--border-card);
        background: rgba(255,255,255,0.08);
        font-size: var(--font-size-sm);
        font-weight: 700;
        color: #ffffff;">
        <div style="min-width: 110px;">Total</div>
        <div style="min-width: 80px;">${grandTotal}</div>
        <div style="min-width: 80px; color: ${grandRate > 70 ? '#00E676' : '#ffc107'};">${grandRate}%</div>
    </div>
`;

html += `</div>`;
table.innerHTML = html;

    });
 



// عند تحميل الصفحة
  };
   // ربط زر التحديث
    document.getElementById('apply-filters-btn').addEventListener('click', function () {
        // قراءة قيمة الفلتر الخاص بالفترة
        const period = document.getElementById('period-filter').value || 'all';
        
        // قراءة المنتج المحدد
const productSelect = document.getElementById('product-filter');
const selectedOption = productSelect.options[productSelect.selectedIndex];
const productId = selectedOption.getAttribute('data-product-id') || 'all';
if(productId == ''){
    productId = 'all';
}
        
        // قراءة الدولة إذا كان عندك فلتر دولة
const country = document.getElementById('country-filter').value || 'all';
        // const country = countrySelect ? (countrySelect.value || 'all') : 'all';
         // استدعاء الدالة مع القيم التي حددها المستخدم
        trackCompanyData(period, productId, country);
    });
   
        trackCompanyData(period = 'all', productId='all', country = 'all');
});



/* --- Inline script #3 extracted from tracking.html --- */

let mainProductProject = "";  // سنخزن هنا project المنتج الرئيسي

// عند اختيار المنتج الرئيسي:
document.getElementById("select-product-dropdown").addEventListener("change", function() {
  const selectedOption = this.selectedOptions[0];
  mainProductProject = selectedOption.getAttribute("data-project") || "";
  console.log("mainProductProject:", mainProductProject);
});

document.addEventListener("input", function(e) {
  if (e.target.classList.contains("sku-input")) {
    const skuInput = e.target;
    const sku = skuInput.value.trim();

    if (sku.length >= 7) {  // مثلاً لا نرسل إذا كان قصير جداً
      fetch(`/get-product-info/?sku=${encodeURIComponent(sku)}`)
        .then(response => response.json())
        .then(data => {
          const nameInput = skuInput.closest(".row").querySelector(".product-name-input");
          if (data.success) {

            nameInput.value = data.name;
            const giftProject = data.project || "";
            console.log( giftProject , mainProductProject);

          // مقارنة موقع التخزين
          if (giftProject !== mainProductProject) {
            console.log( giftProject , mainProductProject);
            document.getElementById("notsame").classList.remove("d-none");
            document.getElementById("notsame").textContent = "⚠️ الهدية من مخزن مختلف عن المنتج الأساسي. يُفضل اختيار هدية من نفس المخزن.";
          }
          else {
            document.getElementById("notsame").classList.add("d-none");
          }

          } else {
            document.getElementById("notsame").classList.remove("d-none");
            document.getElementById("notsame").textContent="⚠️ المنتج غير موجود.";
            nameInput.value = "";

            
          }
        })
        .catch(error => {
          console.error("خطأ في الجلب:", error);
        });
    }
  }
});



/* --- Inline script #4 extracted from tracking.html --- */

document.addEventListener('DOMContentLoaded', function() {
                // عند اختيار منتج من القائمة المنسدلة
                document.getElementById('select-product-dropdown').addEventListener('change', function() {
                    const selectedOption = this.options[this.selectedIndex];
                    const sku = selectedOption.value;
                    const name = selectedOption.getAttribute('data-name');
                    if (sku) {
                        // إظهار رسالة المنتج المحدد
                        document.getElementById('selected-product-info').classList.remove('d-none');
                        document.getElementById('selected-product-name').textContent = name;
                        document.getElementById('selected-product-sku').textContent = 'SKU: ' + sku;
                        // تعبئة النموذج المخفي بقيم المنتج
                        document.getElementById('form-product-name').textContent = name;
                        document.getElementById('form-product-sku').textContent = 'SKU: ' + sku;
                        document.getElementById('hidden-selected-sku').value = sku;
                        // إظهار النموذج
                        document.getElementById('order-form-section').classList.remove('d-none');
                        // إخفاء اختيار المنتج
                        document.getElementById('product-select-section').classList.add('d-none');
                    }
                });

                // زر تغيير المنتج
                document.getElementById('change-product-btn').addEventListener('click', function() {
                    document.getElementById('selected-product-info').classList.add('d-none');
                    // document.getElementById('order-form-section').classList.add('d-none');
                    document.getElementById('form-product-name').textContent = "Select a product"
                    document.getElementById('form-product-sku').textContent = "";
                    document.getElementById('product-select-section').classList.remove('d-none');
                    // إعادة تعيين النموذج
                    document.getElementById('order-form').reset();
                    document.getElementById("select-product-dropdown").value = "";

                     
                    document.getElementById('items-container').innerHTML = '';
                    addItem();
                });
            });



/* --- Inline script #5 extracted from tracking.html --- */

function showOrderSubmitAlert(success, message) {
                    console.log("📣 عرض الرسالة:", message, "نجاح؟", success);

                        const alertBox = document.getElementById('order-submit-alert');
                        const icon = document.getElementById('order-submit-icon');
                        const msg = document.getElementById('order-submit-message');
                        if (success) {
                            alertBox.className = "alert alert-success";
                            icon.innerHTML = '<i class="fas fa-check-circle" style="color:var(--accent-color);"></i>';
                        } else {
                            alertBox.className = "alert alert-danger";
                            icon.innerHTML = '<i class="fas fa-times-circle" style="color:#dc3545;"></i>';
                        }
                        msg.textContent = message;
                        alertBox.classList.remove('d-none');
                        setTimeout(() => { alertBox.classList.add('d-none'); }, 3500);
                    }

document.getElementById("order-form").addEventListener("submit", function(e) {
    e.preventDefault(); // منع الإرسال العادي
    
    $('#submit-order-btn').prop('disabled', true); // تعطيل الزر
$('#order-submit-btn-spinner').removeClass('d-none'); // إظهار اللودينغ


    const form = e.target;
    const formData = new FormData(form);

    fetch("/submit-order/", {
        method: "POST",
        headers: {
            "X-Requested-With": "XMLHttpRequest"
        },
        body: formData
    })
    .then(response => response.json())

    .then(data => {
            $('#submit-order-btn').prop('disabled', false); // إعادة تفعيل الزر
$('#order-submit-btn-spinner').addClass('d-none'); // إخفاء اللودينغ



        if (data.success) {
            // console.log("✅ الطلبية أُرسلت بنجاح:", data);
            showOrderSubmitAlert(true , data.message);
            form.reset(); 
            document.getElementById("items-container").innerHTML = ""; // حذف العناصر المضافة
        } else {
                        showOrderSubmitAlert(false , data.message);

            // alert("⚠️ هناك مشكلة في إرسال الطلب. يرجى التحقق من البيانات.");
        }
    })
    .catch(error => {
        console.error("❌ فشل الاتصال:", error);
        alert("حدث خطأ أثناء الإرسال، يرجى المحاولة لاحقًا.");
    });
});



/* --- Inline script #6 extracted from tracking.html --- */

function addItem() {
    const template = document.getElementById("item-template").content.cloneNode(true);
    document.getElementById("items-container").appendChild(template);
  }

  function removeItem(button) {
    button.closest('.item').remove();
  }

  // عنصر افتراضي عند تحميل الصفحة
  window.addEventListener('DOMContentLoaded', () => {
    addItem();
  });



/* --- Inline script #7 extracted from tracking.html --- */

(function(){
  const debug = false;
  const log = (...args) => { if (debug) console.log(...args); };

  // تحقق إن المودال مفتوح
  function isModalOpen(modal) {
    if (!modal) return false;
    return getComputedStyle(modal).display !== 'none';
  }

  // افتح مودال (يمكن تمرير العنصر مباشرة)
  function openModal(modal) {
    if (!modal) return console.error('❌ modal not found');
    if (isModalOpen(modal)) return;
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
    log('modal opened', modal);
  }

  // اغلق مودال
  function closeModal(modal) {
    if (!modal) return;
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
    log('modal closed', modal);
  }

  // المعالج الرئيسي للأحداث
  function delegatedHandler(e) {
    try {
      // 1) زر فتح المودال داخل الجدول
      const openBtn = e.target.closest('.show-order-btn');
      if (openBtn) {
        // البحث عن المودال في نفس الصف
        const row = openBtn.closest('tr');
        const modal = row ? row.querySelector('.order-Modal') : null;
        openModal(modal);
        return;
      }

      // 2) زر إغلاق المودال
      const closeBtn = e.target.closest('.close2, .close, [data-modal-close]');
      if (closeBtn) {
        const modalParent = closeBtn.closest('.order-Modal');
        closeModal(modalParent);
        return;
      }

      // 3) الضغط على الخلفية (المنطقة الخارجية داخل المودال)
      if (e.target.classList.contains('order-Modal')) {
        closeModal(e.target);
        return;
      }
    } catch(err) {
      console.error(err);
    }
  }

  // إضافة المستمع على document
  document.addEventListener('click', delegatedHandler, true);

  // غلق بالمفتاح ESC
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' || e.key === 'Esc') {
      document.querySelectorAll('.order-modal').forEach(modal => {
        if (isModalOpen(modal)) closeModal(modal);
      });
    }
  });

  log('delegatedHandler initialized');
})();



/* --- Inline script #8 extracted from tracking.html --- */

document.addEventListener("DOMContentLoaded", function() { 
 

function initLeads() {
    
 
    
  const container = document.getElementById("leads-container");

  // ✅ ميثود عامة تجلب البيانات من السيرفر
  function fetchLeads(url) {
    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then((res) => res.json())
      .then((data) => {
        container.innerHTML = data.html;
        attachPaginationEvents(); // إعادة تفعيل pagination بعد تحميل جديد
      })
      .catch((err) => console.error("Error fetching leads:", err));
  }

  // ✅ جمع كل قيم الفلاتر
  function getFilterParams() {
    const statusEl = document.getElementById("status-leads-filter");
    const periodEl = document.getElementById("period-leads-filter");
    const startDateEl = document.getElementById("start-date-filter");
    const endDateEl = document.getElementById("end-date-filter");
    const productEl = document.getElementById("product-leads-filter");
    const countryEl = document.getElementById("country-leads-filter");
    const searchEl = document.getElementById("live-search-leads");

    const params = new URLSearchParams();

    if (statusEl?.value) params.append("status", statusEl.value);
    if (periodEl?.value && periodEl.value !== "All") {
      params.append("period", periodEl.value);
      if (periodEl.value === "custom") {
        if (startDateEl?.value) params.append("start_date", startDateEl.value);
        if (endDateEl?.value) params.append("end_date", endDateEl.value);
      }
    }
    if (productEl?.value) params.append("product_sku", productEl.value);
    if (countryEl?.value) params.append("country", countryEl.value);
    if (searchEl?.value) params.append("search", searchEl.value);

    return params;
  }

  // ✅ تشغيل الفلاتر
  function attachFilters() {
    const applyBtn = document.getElementById("apply-leads-filters-btn");
    const periodEl = document.getElementById("period-leads-filter");

    if (!applyBtn) return;

    // toggle custom date inputs
    periodEl?.addEventListener("change", () => {
      const customRange = document.getElementById("custom-date-range");
      if (customRange) {
        customRange.classList.toggle("d-none", periodEl.value !== "custom");
      }
    });

    applyBtn.addEventListener("click", () => {
      const params = getFilterParams();
      params.append("page", 1); // ابدأ من الصفحة الأولى
      fetchLeads(`{% url 'filter_leads_api' %}?${params.toString()}`);
    });
  }
 
  // ✅ pagination
  function attachPaginationEvents() {
    document.querySelectorAll(".leads-page-link").forEach((link) => {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        const page = this.getAttribute("data-page");
        const params = getFilterParams();
        params.append("page", page);
        fetchLeads(`{% url 'filter_leads_api' %}?${params.toString()}`);
      });
    });
  }

  // ✅ تشغيل أول مرة
  attachFilters();
  attachPaginationEvents();
  popup();
 
 
}

document.addEventListener("DOMContentLoaded", initLeads);


function inistail_popup() {
  const container = document.getElementById("leads-container");

  container.addEventListener("click", function(event) {
    const btn = event.target.closest(".openPopupBtn");
    const closeBtn = event.target.closest(".close");

    if (btn) {
      const item = btn.closest(".lead-item");
      const popup = item.querySelector(".popup");
      popup.style.display = "block";
    }

    if (closeBtn) {
      const popup = closeBtn.closest(".popup");
      popup.style.display = "none";
    }

    // اغلاق عند الضغط خارج البوب أب
    if (!event.target.closest(".popup") && !event.target.closest(".openPopupBtn")) {
      document.querySelectorAll(".popup").forEach(p => p.style.display = "none");
    }
  });
}

document.addEventListener("DOMContentLoaded", inistail_popup);
 });



/* --- Inline script #9 extracted from tracking.html --- */

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



/* --- Inline script #10 extracted from tracking.html --- */

document.addEventListener('click', async (e) => {
  const btn = e.target.closest('#Codproduct');
  if (!btn) return;

  // المكان الذي سيظهر فيه partial
  const setproductlisther = document.getElementById('setproductlisther');
  if (!setproductlisther) return;

  try {
    const response = await fetch("{% url 'load_products' %} "); 
    if (!response.ok) throw new Error('خطأ في التحميل');
    const html = await response.text();

    setproductlisther.innerHTML = html; // إدخال partial في الصفحة
    console.log('don!' , html)
  } catch (err) {
    console.error(err);
  }
});



/* --- Inline script #11 extracted from tracking.html --- */

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



/* --- Inline script #12 extracted from tracking.html --- */

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



/* --- Inline script #13 extracted from tracking.html --- */

// document.addEventListener("DOMContentLoaded", function() { 

    // تبديل بين عرض الشبكة والقائمة
function toggleView(viewType) {
    const gridView = document.getElementById('grid-view');
    if (viewType === 'grid') {
        gridView.classList.remove('list-view');
        gridView.classList.add('row');
    } else {
        gridView.classList.remove('row');
        gridView.classList.add('list-view');
    }
}
 
// عرض تفاصيل المنتج في Modal
function showDetails(productId) {
    fetch(`/api/products/${productId}/`)  // تحتاج لإنشاء API endpoint لهذا
        .then(response => response.json())
        .then(data => {
            document.getElementById('modalTitle').textContent = data.name;
            document.getElementById('modalBody').innerHTML = `
                <div class="row">
                    <div class="col-md-6">
                        <img src="${data.image_url}" class="img-fluid">
                    </div>
                    <div class="col-md-6">
                        <p><strong>الكود:</strong> ${data.cod_id}</p>
                        <p><strong>السعر الأصلي:</strong> <s>${data.original_price} دولار</s></p>
                        <p><strong>الكمية المتاحة:</strong> ${data.stock}</p>
                        <p><strong>التكلفة:</strong> ${data.product_cost} دولار</p>
                        <p><strong>SKU:</strong> ${data.sku}</p>
                    </div>
                </div>
            `;
            new bootstrap.Modal(document.getElementById('productModal')).show();
        });
}



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
  
    const imageInput = document.getElementById('modal-product-image');
    const previewImage = document.getElementById('modal-product-img');

    imageInput.addEventListener('change', function () {
        const file = this.files[0];

        if (file) {
            const reader = new FileReader();

            reader.onload = function (e) {
                previewImage.src = e.target.result;
                previewImage.style.display = 'block';
            }

            reader.readAsDataURL(file);
        } else {
            previewImage.src = '';
            previewImage.style.display = 'none';
        }
    });


    // });



/* --- Inline script #14 extracted from tracking.html --- */

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



/* --- Inline script #15 extracted from tracking.html --- */

document.addEventListener('DOMContentLoaded', function() {
const refresh_leads = document.getElementById('refresh-leads-btn');
refresh_leads.addEventListener('click', function() {
   setprog = document.getElementById('update-lead-progr');
   setprog.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Updating...';

   setprog.classList.remove('d-none');
    document.getElementById('refresh-leads-icon').classList.add('fa-spin');
const productsku = document.getElementById('product-leads-filter').value;
fetch("{% url 'leadstracking' %}" , {
    method: 'POST',
    headers: {
        'Content-Type': 'application/x-www-form-urlencoded'
    } ,
    body: new URLSearchParams({
         'productsku': productsku
     })
})
.then(response => response.json())
.then(response => {
    setprog.classList.add('d-none');
    setprog.innerHTML = 'Data updated seccessfully !';
    document.getElementById('refresh-leads-icon').classList.remove('fa-spin');
    if (response.status === 'success') {
        // Update the UI with the new leads data
        document.getElementById('update-success-message').textContent = response.data;
        setprog.classList.remove('d-none');

        setInterval(function() {
            setprog.classList.add('d-none');

        }, 5000);

    } else {
        // Handle error case
        console.error('Error fetching leads:', response.message);
    }
}); 
}); 
});



/* --- Inline script #16 extracted from tracking.html --- */

// Refresh from server
$('#refresh-orders-btn').click(function () {
    var $icon = $('#refresh-orders-icon');
    $icon.addClass('fa-spin');

    // اجمع معلومات إضافية لإرسالها مع الطلب
    const productSku = $('#settablehere .order-row.active').find('small.text-muted').text().replace('SKU: ', '') || '';
    const prosku = document.getElementById('product-filter').value || 'all'; 
console.log( 'SKUs here' ,prosku);
    // الحصول على اسم المنتج المحدد من الفلتر
    const selectedProduct = $('#product-filter').val() || 'all'; // إذا كان فارغاً اعتبره "all"

    $.ajax({
        url: 'table_update/',
        type: 'GET',
        data: {
            sku: prosku,
            product: selectedProduct // أرسل اسم المنتج المحدد أو "all"
        },
        success: function (data) {
            console.log(data);
            const updateSuccessMessage = document.getElementById('update-success-message');
            if (data) {
                updateSuccessMessage.classList.remove('d-none');
                $icon.removeClass('fa-spin')
                setTimeout(function () {
                    //  updateSuccessMessage.classList.add('d-none');
                    location.reload();
                }, 5000);
            }
        }
    });
});



/* --- Inline script #17 extracted from tracking.html --- */

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
        function updateTrackingFrame(trackingNumber, company) {
            const iframe = document.getElementById('tracking-iframe');
            const container = iframe.closest('.iframe-container');
            const initialIframeMessage = document.getElementById('initial-iframe-message');
            const currentTrackingNumberDisplay = document.getElementById('current-tracking-number');

            if (!iframe || !trackingNumber) {
                if (iframe) iframe.classList.add('d-none');
                if (initialIframeMessage) initialIframeMessage.classList.remove('d-none');
                currentTrackingNumberDisplay.textContent = 'Not Selected';
                return;
            }

            // Determine company if not explicitly passed (or refine based on tracking number)
            if (!company || company === 'unknown') {
                if (trackingNumber.startsWith('60') && trackingNumber.length === 13) {
                    company = 'imile';
                } else if (trackingNumber.startsWith('INJAZ') && trackingNumber.length === 13) {
                    company = 'injaz';
                } else {
                    console.warn("Unknown tracking number format or company:", trackingNumber);
                    // Display error message directly in container instead of iframe
                    container.innerHTML = `
                        <div class="no-tracking-selected">
                            <i class="fas fa-exclamation-circle"></i>
                            <p>Tracking for this number is not supported or format is unknown.</p>
                            <p style="color: var(--accent-color); font-weight: 600; font-size: var(--font-size-sm);">${trackingNumber}</p>
                        </div>
                    `;
                    currentTrackingNumberDisplay.textContent = 'Error';
                    return;
                }
            }
            
            // If the company or tracking number hasn't changed, no need to update iframe unless it was hidden
            if (company === currentCompany && trackingNumber === currentTrackingNumber && !iframe.classList.contains('d-none')) {
                return;
            }

            // Hide "no tracking selected" message and show iframe
            if (initialIframeMessage) initialIframeMessage.classList.add('d-none');
            iframe.classList.remove('d-none');

            // Show loading indicator
            container.classList.add('iframe-loading');
            
            // Update current values
            currentCompany = company;
            currentTrackingNumber = trackingNumber;
            currentTrackingNumberDisplay.textContent = trackingNumber;

            // Set the appropriate URL for the iframe
            // let newUrl;
            // if (company === 'imile') {
            //     newUrl = "https://www.imile.com/AE-en/track";
            // } else if (company === 'injaz') {
            //     newUrl = "http://injaz-express.com"; // Placeholder URL, adjust if real one exists
            // } else {
            //     newUrl = "about:blank"; // Fallback for unknown
            // }

    let newUrl;
    if (company === 'imile') {
        newUrl = "https://www.imile.com/AE-en/track";
    } else if (company === 'injaz') {
        newUrl = "http://injaz-express.com"; // تأكد من تحديث هذا الرابط بالرابط الحقيقي لشركة Injaz
    } else {
        newUrl = "about:blank"; // رابط احتياطي للمعلومات غير المعروفة
    }

    // ****** الجزء الجديد هنا ******
    // تحقق مما إذا كان الرابط الجديد مختلفًا عن الرابط الحالي المحمل في الـ iframe
    if (newUrl !== currentIframeLoadedUrl) {
        iframe.src = newUrl; // استخدم .attr('src', ...) لتغيير الرابط باستخدام jQuery
        currentIframeLoadedUrl = newUrl; // قم بتحديث المتغير ليحتفظ بالرابط الجديد
        console.log('Iframe URL updated to:', newUrl); // للمراقبة في Console
    } else {
        console.log('Company is the same, not reloading iframe:', newUrl); // للمراقبة
    }
    // ***************************

    // ... (بقية الكود الخاص بك لتحديث معلومات العميل وزر الواتساب)

            // iframe.src = newUrl;

            iframe.onload = function() {
                container.classList.remove('iframe-loading');
                if (company === 'imile') {
                    fillImileForm(trackingNumber);
                }
            };

            iframe.onerror = function() {
                container.classList.remove('iframe-loading');
                container.innerHTML = `
                    <div class="no-tracking-selected">
                        <i class="fas fa-times-circle"></i>
                        <p>Failed to load tracking page for ${company}. Please try again later.</p>
                    </div>
                `;
                console.error("Error loading iframe for tracking company:", company);
            };
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
        window.copyToClipboard = function (text, iconElement) {
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
            showSection('whatssap_API_cloud');

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

                const initialPhone = firstOrderItem.getAttribute('data-customer-phone');
                const whatsappLink = $('#whatsapp-link');
                if (initialPhone && initialPhone !== 'N/A') {
                    whatsappLink.attr('href', `https://web.whatsapp.com/send/?phone=${initialPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0`); 
                        whatsappLink.attr('target', 'whatsapp_web_window'); // هذا هو التعديل

                    whatsappLink.removeClass('d-none');
                } else {
                    whatsappLink.addClass('d-none');
                }

                updateTrackingFrame(firstOrderItem.getAttribute('data-tracking'), firstOrderItem.getAttribute('data-company'));
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
                    // https://web.whatsapp.com/send/?phone=${customerPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0
                    whatsappLink.attr('href', `https://web.whatsapp.com/send/?phone=${customerPhone.replace(/\s/g, '')}&text&type=phone_number&app_absent=0`); // Remove spaces from phone number
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
                            <th width="17%" class="text-center">
                                <i class="fas fa-info-circle me-1"></i>
                                Status
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
    const newPage = $(this).data('page'); // الحصول على رقم الصفحة من data-page
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



/* --- Inline script #18 extracted from tracking.html --- */

$(document).ready(function () {
    $('#updatethis').on('click', function (e) {
      e.preventDefault();

      var $btn = $(this);
      $btn.prop('disabled', true).html(
        '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...'
      );

      $.ajax({
        url: 'update-cod-products/', // تأكد من أن هذا الرابط صحيح في جانب Django
        type: 'POST',
        data: {
          csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').val()
        },
        success: function (response) {
          // عرض الرد بعد الزر
          $('#update-response').remove();
          $('<div id="update-response" class="alert alert-success mt-3"></div>')
            .text(response.message || 'تم التحديث بنجاح!')
            
            .insertAfter($btn);
            setTimeout(function () {
            $('#update-response').fadeOut(500, function() { $(this).remove(); });
          }, 2500);
          $btn.html('<i class="fas fa-check"></i> Updated!');

          // تحديث محتوى المنتجات (إذا كان متاحاً في response)
          if (response.updated_html) {
            $('#setproductlisther').html(response.updated_html);
          }
        //   document.getElementById('settimer').textContent = response.last_update;
        },
        error: function (xhr) {
          $('#update-response').remove();
          $('<div id="update-response" class="alert alert-danger mt-3"></div>')
            .text('حدث خطأ أثناء التحديث.')
            .insertAfter($btn);

          $btn.html('<i class="fas fa-times"></i> Error');
        },
        complete: function () {
          setTimeout(function () {
            $btn.prop('disabled', false).html('<i class="fas fa-sync-alt"></i> Update list');
          }, 2000);
        }
      });
    });
  });



/* --- Inline script #19 extracted from tracking.html --- */

$(document).ready(function () {
    let selectedCountry = "";
    let selectedProject = "";

    function applyFilters() {
      $.ajax({
        url: 'filter_cod_products/',
        method: 'POST',
        data: {
          csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').val(),
          country: selectedCountry.trim(),
          project: selectedProject.trim(),
                search: searchQuery.trim()

        },
        beforeSend: function () {
          $('#products-view').html('<div class="text-center py-5"><div class="spinner-border" role="status"></div></div>');
        },
        success: function (response) {
          if (response.updated_html) {
            $('#products-view').html(response.updated_html);
          }
        },
        error: function () {
          $('#products-view').html('<div class="alert alert-danger">فشل في تحميل المنتجات.</div>');
        }
      });
    }

    $('.country-option').on('click', function (e) {
      e.preventDefault();
      selectedCountry = $(this).data('country');
      $('#selectedCountryText').html('<i class="fas fa-globe me-1"></i>' + (selectedCountry || 'كل الدول'));
      applyFilters();
    });

    $('.project-option').on('click', function (e) {
      e.preventDefault();
      selectedProject = $(this).data('project');
      $('#selectedProjectText').html('<i class="fas fa-boxes me-1"></i>' + (selectedProject || 'كل المشاريع'));
      applyFilters();
    });
    let searchQuery = "";

$('#searchBtnfilter').on('click', function (e) {
    e.preventDefault();
  searchQuery = $('#searchInput').val().trim();
  applyFilters(); // نفس الدالة التي تستعملها حالياً

});

  });

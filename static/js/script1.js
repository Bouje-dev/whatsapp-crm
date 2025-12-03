
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






    


document.addEventListener('DOMContentLoaded', function () {
const periodSelect = document.getElementById('period-filter');
const customDateRangeDiv = document.getElementById('custom-date-range');

if (periodSelect && customDateRangeDiv) {
    function toggleCustomDate() {
        if (periodSelect.value === 'custom') {
            customDateRangeDiv.classList.remove('d-none');
            customDateRangeDiv.classList.add('d-flex');
        } else {
            customDateRangeDiv.classList.remove('d-flex');
            customDateRangeDiv.classList.add('d-none');
        }
    }

    // عند تغيير القيمة
    periodSelect.addEventListener('change', toggleCustomDate);

    // تحقق عند تحميل الصفحة (مهم إذا كانت القيمة محفوظة)
    toggleCustomDate();
}
});




// updater and filter data from database
$(document).ready(function () {
$('#updatethis').on('click', function (e) {
e.preventDefault();

var $btn = $(this);
$btn.prop('disabled', true).html(
'<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Updating...'
);

$.ajax({
url: 'update-cod-products/', 
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








// <!-- update cod drop product filters  -->


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














$(document).ready(function () { 

// Refresh order list from server 
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
        performSearch();
        setTimeout(function () {
            //  updateSuccessMessage.classList.add('d-none');
            // location.reload();
            // performSearch();
        }, 5000);
    }
}
});
});



});

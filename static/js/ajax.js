
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




document.addEventListener('DOMContentLoaded', function () {
    const flipElements = document.querySelectorAll('.flipping');
    const stockElements = document.querySelectorAll('.stockElement');


    // أولياً نعرض الأول ونخفي الثاني (بدون استخدام display)
    flipElements.forEach(el => el.style.transform = 'translateX(0)');
    stockElements.forEach(el => el.style.transform = 'translateX(100%)');

    let isFlipped = false;

    setInterval(() => {
        if (!isFlipped) {
            // ننتقل للواجهة الثانية
            flipElements.forEach(el => {
                el.style.transform = 'translateX(-100%)';
            });

            stockElements.forEach(el => {
                el.style.transform = 'translateX(0)';
            });

        } else {
            // نعود للواجهة الأولى
            flipElements.forEach(el => {
                el.style.transform = 'translateX(0)';
            });

            stockElements.forEach(el => {
                el.style.transform = 'translateX(100%)';
            });
        }

        isFlipped = !isFlipped;

    }, 5000);
});

    document.addEventListener('DOMContentLoaded', function () {
        const productNames = document.querySelectorAll('.gift-product');
        const inputField = document.getElementById('cx-note');
        if (inputField) {
        inputField.type = 'hidden'; // تحويل النوع إلى مخفي
       }
        productNames.forEach(function (element) {
            element.addEventListener('click', function () {
                const sku = this.getAttribute('gift-sku');
                const name = this.getAttribute('gift-name');
                if (sku  && name){
                    inputField.value = `SKU: ${sku}, Name: ${name}`; // أو أي تنسيق آخر تريده

                // مثال: طباعة البيانات في الـ Console
                console.log("SKU:", sku);
                console.log("الاسم:", name);
                                 }


                // مثال: عرض رسالة للمستخدم
            });
        });
    });




    document.addEventListener('DOMContentLoaded', function () {
        const productsGrid = document.getElementById('productsGrid');

        const toggleBtn = document.getElementById('toggleBtn');
        const arrowIcon = document.getElementById('arrowIcon');

        toggleBtn.addEventListener('click', () => {
            toggleBtn.classList.toggle('active');
        });
        // إخفاء الشبكة في البداية
        productsGrid.style.display = 'none';

        toggleBtn.addEventListener('click', function () {
            this.classList.toggle('active');
            productsGrid.style.display = productsGrid.style.display === 'none' ? 'grid' : 'none';
        });





    const productCards = document.querySelectorAll('.gift-product');
const originalContents = new Map();

// حفظ المحتوى الأصلي لكل بطاقة
productCards.forEach(card => {
    const stockMessage = card.querySelector('.stockwarning');
    if (stockMessage) {
        originalContents.set(card, stockMessage.innerHTML);
    }

    // التأكد من أن جميع المنتجات تبدأ بحالة واضحة
    card.style.opacity = '1';
    card.style.filter = 'brightness(1)';
});

productCards.forEach(card => {
    card.addEventListener('click', function(event) {
        // const sku = this.getAttribute('gift-sku');
        //     const name = this.getAttribute('gift-name');

        //     // مثال: طباعة البيانات في الـ Console
        //     console.log("SKU:", sku);
        //     console.log("الاسم:", name);
        event.stopPropagation();

        const stockMessage = this.querySelector('.stockwarning');

        if (this.classList.contains('selected')) {
            // إلغاء التحديد
            resetAllCards();
            return;
        }
        // تحديد المنتج الجديد
        resetAllCards();

        this.classList.add('selected');
        this.style.opacity = '1';
        this.style.filter = 'brightness(1)';

        if (stockMessage) {
            stockMessage.innerHTML = 'تم التحديد بنجاح';
        }

        console.log('تم اختيار المنتج:', this.getAttribute('gift-name') || 'غير معرف');
    });
});

function resetAllCards() {
    productCards.forEach(c => {
        c.classList.remove('selected');
        c.style.opacity = '1'; // جميع المنتجات واضحة عند عدم التحديد
        c.style.filter = 'brightness(1)';

        // إعادة نص المخزون الأصلي
        const msg = c.querySelector('.stockwarning');
        if (msg && originalContents.has(c)) {
            msg.innerHTML = originalContents.get(c);
        }
    });
}

// تطبيق الضبابة على المنتجات غير المحددة عند وجود منتج محدد
function updateCardStates() {
    const hasSelected = document.querySelector('.gift-product.selected') !== null;

    productCards.forEach(card => {
        if (hasSelected && !card.classList.contains('selected')) {
            card.style.opacity = '0.6';
            card.style.filter = 'brightness(0.9)';
        } else {
            card.style.opacity = '1';
            card.style.filter = 'brightness(1)';
        }
    });
}

// تحديث الحالات عند أي تغيير
productCards.forEach(card => {
    card.addEventListener('click', updateCardStates);
});
});




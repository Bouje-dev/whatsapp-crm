# utils.py

import requests
from PIL import Image
from io import BytesIO
from django.core.files.base import ContentFile

def download_and_save_local_image(product, s3_url):
    try:
        print(f"🔗 جارٍ تنزيل الصورة من: {s3_url}")

        # تنزيل الصورة بدون stream (لضمان قراءة كل المحتوى)
        response = requests.get(s3_url)

        if response.status_code != 200:
            print(f"❌ فشل في الوصول للصورة - status code: {response.status_code}")
            return False

        # التحقق من نوع الملف
        content_type = response.headers.get('Content-Type', '')
        if 'image/' not in content_type:
            print(f"❌ الملف ليس صورة - Content-Type: {content_type}")
            return False

        # التحقق من أن المحتوى هو صورة
        image_data = BytesIO(response.content)
        img = Image.open(image_data)
        print(f"✅ الصورة تم فتحها بنجاح - نوعها: {img.format}, الأبعاد: {img.size}")

        # تحديد اسم الملف
        ext = img.format.lower()
        file_name = f"{product.cod_id}.{ext}"

        # حفظ الصورة في الحقل المحلي
        product.productImage.save(file_name, ContentFile(response.content), save=False)

        # ⚠️ هام جداً: يجب حفظ المنتج لكي يتم حفظ الصورة في قاعدة البيانات
        product.save(update_fields=['productImage'])  # ← هنا نحفظ الصورة فقط دون تحديث باقي الحقول
        print(f"✅ الصورة تم حفظها باسم: {file_name}")

        return True

    except Exception as e:
        print(f"❌ خطأ أثناء تنزيل أو حفظ الصورة: {str(e)}")
        return False
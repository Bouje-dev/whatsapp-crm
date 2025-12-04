FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg


# 2. منع بايثون من كتابة ملفات pyc وتفعيل السجلات
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 3. تحديد مجلد العمل داخل السيرفر
WORKDIR /app

# 4. 🔥 تثبيت ffmpeg ومكتبات النظام الضرورية 🔥
# هذا هو السطر الذي يحل مشكلتك
RUN apt-get update && \
    apt-get install -y ffmpeg libpq-dev gcc && \
    apt-get clean

# 5. نسخ ملف المتطلبات وتثبيتها
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 6. نسخ باقي ملفات المشروع
COPY . /app/

# 7. جمع الملفات الثابتة (CSS/JS)
RUN python manage.py collectstatic --noinput

# 8. أمر التشغيل (Daphne للسوكيت)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "disound.asgi:application"]
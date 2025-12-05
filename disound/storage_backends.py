from cloudinary_storage.storage import MediaCloudinaryStorage  # pyright: ignore[reportMissingImports]

class MixedMediaStorage(MediaCloudinaryStorage):
    """
    تخزين مخصص يسمح برفع الصور والفيديو والصوت معاً.
    يستخدم resource_type = 'auto' ليترك لـ Cloudinary حرية التصنيف.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TAG = 'mixed_media' # اختياري: وسم للملفات

    # إجبار النوع على 'auto'
    RESOURCE_TYPE = 'auto'
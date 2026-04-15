# Generated manually for voice–dialect coupling (TTS / LLM alignment).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("discount", "0133_voice_clone_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="voicegalleryentry",
            name="dialect",
            field=models.CharField(
                choices=[
                    ("MA_DARIJA", "Moroccan Darija"),
                    ("SA_ARABIC", "Saudi Arabic"),
                    ("EG_ARABIC", "Egyptian Arabic"),
                    ("MSA", "Modern Standard Arabic"),
                    ("LEV_ARABIC", "Levantine Arabic"),
                    ("GULF_ARABIC", "Gulf Arabic"),
                    ("OTHER", "Other / Multilingual"),
                ],
                db_index=True,
                default="MA_DARIJA",
                help_text="Primary spoken dialect for this voice; drives LLM output to match TTS pronunciation.",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="voiceclonerequest",
            name="dialect",
            field=models.CharField(
                choices=[
                    ("MA_DARIJA", "Moroccan Darija"),
                    ("SA_ARABIC", "Saudi Arabic"),
                    ("EG_ARABIC", "Egyptian Arabic"),
                    ("MSA", "Modern Standard Arabic"),
                    ("LEV_ARABIC", "Levantine Arabic"),
                    ("GULF_ARABIC", "Gulf Arabic"),
                    ("OTHER", "Other / Multilingual"),
                ],
                default="MA_DARIJA",
                help_text="Dialect the merchant declares for this sample (stored with the request and applied on approval).",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="whatsappchannel",
            name="voice_dialect",
            field=models.CharField(
                choices=[
                    ("MA_DARIJA", "Moroccan Darija"),
                    ("SA_ARABIC", "Saudi Arabic"),
                    ("EG_ARABIC", "Egyptian Arabic"),
                    ("MSA", "Modern Standard Arabic"),
                    ("LEV_ARABIC", "Levantine Arabic"),
                    ("GULF_ARABIC", "Gulf Arabic"),
                    ("OTHER", "Other / Multilingual"),
                ],
                default="MA_DARIJA",
                help_text="Dialect aligned with the current voice (gallery selection or approved clone).",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="voicepersona",
            name="dialect",
            field=models.CharField(
                choices=[
                    ("MA_DARIJA", "Moroccan Darija"),
                    ("SA_ARABIC", "Saudi Arabic"),
                    ("EG_ARABIC", "Egyptian Arabic"),
                    ("MSA", "Modern Standard Arabic"),
                    ("LEV_ARABIC", "Levantine Arabic"),
                    ("GULF_ARABIC", "Gulf Arabic"),
                    ("OTHER", "Other / Multilingual"),
                ],
                default="MA_DARIJA",
                help_text="Spoken dialect for this voice (especially user clones); drives LLM/TTS alignment.",
                max_length=32,
            ),
        ),
    ]

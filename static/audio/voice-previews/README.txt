Voice preview MP3s (static, zero API cost)
==========================================

Place one MP3 per catalog voice in this folder. Filenames must match the
`preview_file` field on each row in Django Admin → Voice Gallery entries
(discount.models.VoiceGalleryEntry):

  rachel.mp3
  adam.mp3
  bella.mp3
  antoni.mp3
  elli.mp3
  josh.mp3
  arnold.mp3
  daniel.mp3
  lily.mp3
  michael.mp3

Served at: /static/audio/voice-previews/<filename>

After adding files, run collectstatic in production if applicable.

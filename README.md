# Homenaje a los 60 años de Lila

Video horizontal 16:9, 1920×1080, 30 fps (listo para proyectar en TV), con las fotografías originales,
mensajes en pantalla y la canción "Gira el amor" (archivo MP3 de esta carpeta).

**Resultado:** `output/Homenaje_Lila_60_anos.mp4`

## Volver a generarlo
Requisitos: Python 3.9+, `pip install pillow numpy`, y `ffmpeg` con libx264.

```
python3 build_video.py                  # render completo (~3 min con 4 núcleos)
python3 build_video.py --preview 6,30   # solo fotogramas de prueba en cache/preview
python3 build_video.py --audio ruta.mp3 # usar otro archivo de audio
```

## Cómo editarlo
Todo el guion está al inicio de `build_video.py` (sección GUION):
- `SEQUENCE`: orden de las fotos, ritmo (`n` pausado, `m` medio, `j` alegre) y mensaje (opcional).
- `IMG`: ruta de cada foto. Para añadir una foto, agrégala en `IMG` y en `SEQUENCE`.
- `INTRO_*` y `CLOSING`: textos y tiempos de la introducción y el cierre.
- `*palabra*` marca texto en cursiva dorada.
- Las duraciones de las fotos se reparten solas entre 12 s y 141 s; los cortes se ajustan al pulso de la música.

Tipografías: Cormorant Garamond y Great Vibes (licencia SIL OFL, en `fonts/`).

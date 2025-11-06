# Koordinaten-Umrechnung: 1600x900 → 720x1280

## Bildschirm-Spezifikationen

### Altes Gerät:
- Auflösung: 1600 x 900 Pixel
- DPI: 240
- Seitenverhältnis: 16:9 (Querformat)

### Neues Gerät (VMOSCloud):
- Auflösung: 720 x 1280 Pixel
- DPI: 320
- Seitenverhältnis: 9:16 (Hochformat)

## Umrechnungsfaktoren

```
Faktor X = 720 / 1600 = 0.45
Faktor Y = 1280 / 900 = 1.422
```

**Wichtig:** Die Umrechnung ist nicht linear, da sich das Seitenverhältnis ändert!

## Click-Koordinaten

| Aktion | Original (1600x900) | Umgerechnet (720x1280) | Berechnung |
|--------|---------------------|------------------------|------------|
| **ESC Button** | (840, 100) | (378, 142) | 840×0.45, 100×1.422 |
| **Teilen Button** | (530, 1400) | (238, 1991) | 530×0.45, 1400×1.422 |
| **Bestätigen 1** | (300, 550) | (135, 782) | 300×0.45, 550×1.422 |
| **Bestätigen 2** | (520, 900) | (234, 1280) | 520×0.45, 900×1.422 |
| **LKW-Offset** | (+12, +12) | (+5, +5) | Angepasst für kleineren Screen |

## OCR-Bereiche (Crop-Boxen)

Format: (links, oben, rechts, unten)

| Bereich | Original (1600x900) | Umgerechnet (720x1280) | Berechnung |
|---------|---------------------|------------------------|------------|
| **Stärke** | (260, 1170, 370, 1250) | (117, 1664, 166, 1778) | Alle Werte mit Faktoren |
| **Server** | (220, 1100, 280, 1150) | (99, 1564, 126, 1636) | Alle Werte mit Faktoren |

### Detaillierte Berechnung Stärke-Box:
```
Links:  260 × 0.45 = 117
Oben:   1170 × 1.422 = 1664
Rechts: 370 × 0.45 = 166
Unten:  1250 × 1.422 = 1778
```

### Detaillierte Berechnung Server-Box:
```
Links:  220 × 0.45 = 99
Oben:   1100 × 1.422 = 1564
Rechts: 280 × 0.45 = 126
Unten:  1150 × 1.422 = 1636
```

## Python-Code für Umrechnung

```python
def convert_coordinates(x_old, y_old, 
                       old_width=1600, old_height=900,
                       new_width=720, new_height=1280):
    """
    Konvertiert Koordinaten von alter zu neuer Auflösung
    """
    factor_x = new_width / old_width
    factor_y = new_height / old_height
    
    x_new = int(x_old * factor_x)
    y_new = int(y_old * factor_y)
    
    return (x_new, y_new)

# Beispiel:
old_coord = (840, 100)
new_coord = convert_coordinates(840, 100)
print(f"{old_coord} → {new_coord}")  # (840, 100) → (378, 142)
```

## Umrechnung für andere Auflösungen

Falls dein Gerät eine andere Auflösung hat:

```python
# Für 1080x1920 (Full HD Portrait):
factor_x = 1080 / 1600 = 0.675
factor_y = 1920 / 900 = 2.133

# Für 1440x2560 (2K Portrait):
factor_x = 1440 / 1600 = 0.9
factor_y = 2560 / 900 = 2.844
```

## Testen der Koordinaten

### 1. Screenshot erstellen:
```bash
adb shell screencap -p /sdcard/test.png
adb pull /sdcard/test.png
```

### 2. Koordinaten visuell markieren:
```python
import cv2
from PIL import Image, ImageDraw

# Bild laden
img = Image.open('test.png')
draw = ImageDraw.Draw(img)

# Koordinate markieren
x, y = 378, 142
radius = 10
draw.ellipse([x-radius, y-radius, x+radius, y+radius], 
             outline='red', width=3)

img.save('test_marked.png')
```

### 3. Klick testen:
```bash
# Klick auf berechnete Koordinate
adb shell input tap 378 142

# Warte und prüfe Ergebnis
sleep 1
adb shell screencap -p /sdcard/after.png
adb pull /sdcard/after.png
```

## Feinabstimmung

Falls die Koordinaten nicht exakt passen:

### Methode 1: Manuelles Testen
```python
# In lkw_bot_web.py anpassen:
COORDS_NEW = {
    'esc': (378 + OFFSET_X, 142 + OFFSET_Y),
    # ...
}

# Verschiedene Offsets ausprobieren:
# OFFSET_X = -5, 0, +5
# OFFSET_Y = -5, 0, +5
```

### Methode 2: Interaktive Koordinaten-Suche
```python
import cv2

img = cv2.imread('screen.png')

def click_event(event, x, y, flags, params):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Koordinate: ({x}, {y})")
        cv2.circle(img, (x, y), 5, (0, 0, 255), -1)
        cv2.imshow('image', img)

cv2.imshow('image', img)
cv2.setMouseCallback('image', click_event)
cv2.waitKey(0)
cv2.destroyAllWindows()
```

### Methode 3: Template-Matching für Buttons
```python
import cv2
import numpy as np

# Screenshot und Button-Template
screen = cv2.imread('screen.png')
button = cv2.imread('esc_button.png')

# Finde Button
result = cv2.matchTemplate(screen, button, cv2.TM_CCOEFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

# Berechne Zentrum
h, w = button.shape[:2]
center_x = max_loc[0] + w // 2
center_y = max_loc[1] + h // 2

print(f"Button-Zentrum: ({center_x}, {center_y})")
```

## Bekannte Probleme

### Problem: Button wird nicht getroffen
**Lösung:** 
- Offset anpassen (±5-10 Pixel)
- Skalierung des UI prüfen (DPI-Einstellungen)
- Template-Matching für exakte Position nutzen

### Problem: OCR erkennt nichts
**Lösung:**
- OCR-Box verschieben/vergrößern
- Screenshot erstellen und Box visuell prüfen
- Kontrast/Helligkeit anpassen

### Problem: Unterschiedliche UI-Skalierung
**Lösung:**
- DPI-Einstellungen im Emulator prüfen
- Nicht nur nach Pixeln, sondern nach DP (density-independent pixels) rechnen

## Checkliste für neue Auflösung

- [ ] Alte Koordinaten dokumentieren
- [ ] Umrechnungsfaktoren berechnen
- [ ] Neue Koordinaten berechnen
- [ ] Screenshots erstellen
- [ ] Koordinaten visuell markieren
- [ ] Klicks einzeln testen
- [ ] OCR-Bereiche anpassen
- [ ] Template-Bilder bei Bedarf neu erstellen
- [ ] Vollständigen Durchlauf testen
- [ ] Werte in Code übertragen
- [ ] Dokumentation aktualisieren

## Hilfsmittel

### ADB Koordinaten-Tester
```bash
#!/bin/bash
# test_coords.sh

echo "Teste Koordinate: $1, $2"
adb shell screencap -p /sdcard/before.png
adb shell input tap $1 $2
sleep 1
adb shell screencap -p /sdcard/after.png
adb pull /sdcard/before.png
adb pull /sdcard/after.png
echo "Screenshots: before.png, after.png"
```

Verwendung:
```bash
bash test_coords.sh 378 142
```

## Weitere Ressourcen

- ADB Commands: https://developer.android.com/studio/command-line/adb
- OpenCV Template Matching: https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
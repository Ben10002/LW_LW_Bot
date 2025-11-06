# LKW-Bot für Last War - Web Edition

Automatisierter Bot zum Finden und Teilen von Rentier-LKWs in Last War, speziell für VMOSCloud und Raspberry Pi optimiert.

## Features

✅ **Web-Interface** - Steuerung über Browser von überall  
✅ **Login-Schutz** - Sichere Authentifizierung mit Benutzername/Passwort  
✅ **VMOSCloud-Support** - Verbindung über SSH-Tunnel  
✅ **Angepasste Koordinaten** - Optimiert für 720x1280 (320 DPI)  
✅ **Live-Statistiken** - Echtzeit-Überwachung der Bot-Aktivität  
✅ **Filter-Optionen** - Stärke und Server können gefiltert werden  
✅ **Auto-Reset** - Automatisches Zurücksetzen der gespeicherten Stärken  
✅ **Raspberry Pi optimiert** - Läuft stabil als Systemdienst  

## Schnellstart

### 1. Voraussetzungen installieren
```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip adb tesseract-ocr
```

### 2. Python-Pakete installieren
```bash
pip3 install -r requirements.txt
```

### 3. Konfiguration anpassen
Öffne `lkw_bot_web.py` und ändere:
- **SSH-Verbindungsdaten** (Zeilen 28-33)
- **app.secret_key** (Zeile 40) - WICHTIG!
- **Admin-Passwort** (Zeile 318) - WICHTIG!

### 4. Bot starten
```bash
python3 lkw_bot_web.py
```

### 5. Im Browser öffnen
```
http://localhost:5000
```

**Standard-Login:**
- Benutzername: `admin`
- Passwort: `admin123` (BITTE ÄNDERN!)

## Koordinaten-Umrechnung

Von **1600x900** (DPI 240) zu **720x1280** (DPI 320):

| Aktion | Alt (1600x900) | Neu (720x1280) | Faktor |
|--------|----------------|----------------|--------|
| ESC | 840, 100 | 378, 142 | x: 0.45, y: 1.422 |
| Teilen | 530, 1400 | 238, 1991 | x: 0.45, y: 1.422 |
| Bestätigen 1 | 300, 550 | 135, 782 | x: 0.45, y: 1.422 |
| Bestätigen 2 | 520, 900 | 234, 1280 | x: 0.45, y: 1.422 |

**OCR-Bereiche:**
- **Stärke-Box**: (117, 1664, 166, 1778)
- **Server-Box**: (99, 1564, 126, 1636)

## SSH-Tunnel zu VMOSCloud

Der Bot baut automatisch einen SSH-Tunnel auf:

```bash
ssh -oHostKeyAlgorithms=+ssh-rsa \
    10.0.8.67_1762116558169@103.237.100.130 \
    -p 1824 \
    -L 5839:adb-proxy:24345 \
    -Nf
```

Dann wird ADB verbunden:
```bash
adb connect localhost:5839
```

## Web-Interface

### Dashboard
- **Status-Anzeige** mit Live-Indikator (grün/gelb/rot)
- **Control-Buttons** zum Starten/Pausieren/Stoppen
- **Statistiken** über verarbeitete, geteilte und übersprungene LKWs
- **ADB-Verbindungsstatus**

### Einstellungen
- **Stärkebeschränkung**: Nur LKWs bis zu einer bestimmten Stärke teilen
- **Server-Filter**: Nur LKWs von bestimmtem Server teilen
- **Reset-Intervall**: Automatisches Zurücksetzen der Stärken-Liste

### Screenshots
Die Oberfläche aktualisiert sich alle 2 Sekunden automatisch.

## API-Endpunkte

### Status abrufen
```
GET /api/status
```
Gibt aktuellen Bot-Status, Statistiken und letzte Aktion zurück.

### Bot steuern
```
POST /api/start    # Bot starten
POST /api/pause    # Bot pausieren/fortsetzen
POST /api/stop     # Bot stoppen
```

### Einstellungen
```
GET  /api/settings              # Einstellungen abrufen
POST /api/settings              # Einstellungen speichern
POST /api/reset_stats           # Statistiken zurücksetzen
```

## Systemdienst einrichten

Als Service laufen lassen (startet automatisch beim Booten):

```bash
sudo cp lkw-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lkw-bot.service
sudo systemctl start lkw-bot.service
```

Status prüfen:
```bash
sudo systemctl status lkw-bot.service
```

## Zugriff von außen (Internet)

### Option 1: Port-Forwarding im Router
1. Router-Einstellungen öffnen
2. Port-Forwarding einrichten: `[Externes Port] -> [Raspberry-Pi-IP]:5000`
3. Zugriff über: `http://[Deine-Externe-IP]:[Port]`

### Option 2: DynDNS + HTTPS (empfohlen)
1. DynDNS-Dienst einrichten (z.B. No-IP, DuckDNS)
2. Nginx als Reverse Proxy mit Let's Encrypt SSL
3. Zugriff über: `https://deine-domain.de`

Siehe `INSTALLATION.md` für Details.

## Sicherheit

🔒 **Wichtige Sicherheitsmaßnahmen:**

1. **Standard-Passwort ändern!**
   ```python
   # In lkw_bot_web.py Zeile 318
   'admin': User('1', 'admin', generate_password_hash('DEIN-SICHERES-PASSWORT'))
   ```

2. **Secret Key ändern!**
   ```python
   # In lkw_bot_web.py Zeile 40
   app.secret_key = 'ÄNDERE-DIESEN-SCHLÜSSEL'
   ```

3. **Firewall konfigurieren**
   ```bash
   sudo ufw enable
   sudo ufw allow 5000/tcp
   ```

4. **HTTPS verwenden** (für Internet-Zugriff)

5. **SSH-Keys** statt Passwörter verwenden

## Troubleshooting

### Bot findet keine LKWs
- Prüfe ob `rentier_template.png` korrekt ist
- Template-Matching-Schwellwert anpassen (Zeile 271: `threshold`)

### OCR erkennt Stärke nicht
- OCR-Boxen anpassen: `STAERKE_BOX` und `SERVER_BOX`
- Tesseract-Sprache prüfen: `lang='eng'`
- Manuell testen: `tesseract staerke_ocr.png stdout`

### SSH-Tunnel bricht ab
- ServerAliveInterval ist auf 60 Sekunden gesetzt
- Prüfe Internetverbindung
- Logs prüfen: `sudo journalctl -u lkw-bot.service -f`

### ADB-Verbindung verloren
- Bot stoppt und startet SSH-Tunnel neu
- Manuell: `adb kill-server && adb start-server`

### Web-Interface lädt nicht
- Prüfe ob Port 5000 frei ist: `sudo lsof -i :5000`
- Firewall-Regeln prüfen
- Logs prüfen

## Dateistruktur

```
lkw-bot/
├── lkw_bot_web.py          # Hauptskript
├── requirements.txt         # Python-Abhängigkeiten
├── INSTALLATION.md         # Detaillierte Installation
├── README.md               # Diese Datei
├── rentier_template.png    # Template für LKW-Erkennung
├── lkw_staerken.txt       # Gespeicherte Stärken (automatisch)
├── templates/
│   ├── login.html         # Login-Seite
│   └── index.html         # Dashboard
├── screen.png             # Screenshots (temporär)
├── info.png               # Info-Screenshot (temporär)
├── staerke_ocr.png        # OCR-Ausschnitt (temporär)
└── server_ocr.png         # Server-OCR (temporär)
```

## Technische Details

### Verwendete Technologien
- **Python 3** - Hauptprogrammiersprache
- **Flask** - Webframework
- **OpenCV** - Template-Matching für LKW-Erkennung
- **Tesseract OCR** - Text-Erkennung für Stärke und Server
- **ADB** - Android Debug Bridge für Gerätesteuerung
- **SSH** - Sichere Verbindung zu VMOSCloud

### Systemanforderungen
- Raspberry Pi 3B+ oder neuer (4GB RAM empfohlen)
- Python 3.7+
- Raspbian OS (Bullseye oder neuer)
- Min. 2GB freier Speicher

### Performance
- Screenshot: ~2 Sekunden
- Template-Matching: ~0.5 Sekunden
- OCR: ~1 Sekunde
- Gesamte Verarbeitung pro LKW: ~5-8 Sekunden

## Geplante Features

- [ ] Multi-User-Support
- [ ] Erweiterte Statistiken und Diagramme
- [ ] Benachrichtigungen (Telegram, Discord)
- [ ] Template-Management über Web-Interface
- [ ] Koordinaten-Anpassung über GUI
- [ ] Datenbank statt Textdatei
- [ ] Mehrere Geräte gleichzeitig steuern
- [ ] Mobile App

## Lizenz

Dieses Projekt ist für den privaten Gebrauch bestimmt. Die Nutzung erfolgt auf eigene Verantwortung.

## Support & Kontakt

Bei Fragen oder Problemen:
1. Logs prüfen: `sudo journalctl -u lkw-bot.service -n 100`
2. INSTALLATION.md lesen
3. Issue erstellen (falls GitHub verwendet wird)

## Changelog

### Version 2.0 (Aktuell)
- ✨ Web-Interface statt Tkinter-GUI
- ✨ VMOSCloud-Support über SSH-Tunnel
- ✨ Koordinaten für 720x1280 angepasst
- ✨ Login-Schutz
- ✨ Live-Statistiken
- ✨ Systemdienst-Support

### Version 1.0
- Basis-Bot mit Tkinter-GUI
- Direkter ADB-Zugriff
- Koordinaten für 1600x900

---

**Hinweis**: Automatisierung in Spielen kann gegen die Nutzungsbedingungen verstoßen. Verwende diesen Bot auf eigene Verantwortung.
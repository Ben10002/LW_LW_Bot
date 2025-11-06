#!/bin/bash
# LKW-Bot Setup-Script für Raspberry Pi

set -e

echo "=================================="
echo "LKW-Bot Installation"
echo "=================================="
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Prüfe ob als root ausgeführt
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}Bitte NICHT als root ausführen!${NC}"
    echo "Führe aus mit: bash setup.sh"
    exit 1
fi

echo -e "${YELLOW}1. System-Updates...${NC}"
sudo apt-get update
sudo apt-get upgrade -y

echo ""
echo -e "${YELLOW}2. Installiere System-Pakete...${NC}"
sudo apt-get install -y \
    python3 \
    python3-pip \
    adb \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    libatlas-base-dev \
    libhdf5-dev \
    libhdf5-serial-dev \
    libjasper-dev \
    libqtgui4 \
    libqt4-test

echo ""
echo -e "${YELLOW}3. Installiere Python-Pakete...${NC}"
pip3 install --upgrade pip
pip3 install -r requirements.txt

echo ""
echo -e "${YELLOW}4. Erstelle Projektverzeichnis...${NC}"
INSTALL_DIR="$HOME/lkw-bot"
mkdir -p "$INSTALL_DIR"

# Kopiere Dateien wenn wir nicht bereits im Zielverzeichnis sind
if [ "$PWD" != "$INSTALL_DIR" ]; then
    echo "Kopiere Dateien nach $INSTALL_DIR..."
    cp -r ./* "$INSTALL_DIR/"
    cd "$INSTALL_DIR"
fi

echo ""
echo -e "${YELLOW}5. Konfiguration...${NC}"
echo ""
echo -e "${RED}WICHTIG: Du musst folgende Werte in lkw_bot_web.py anpassen:${NC}"
echo "  - SSH-Verbindungsdaten (Zeilen 28-33)"
echo "  - app.secret_key (Zeile 40)"
echo "  - Admin-Passwort (Zeile 318)"
echo ""
read -p "Möchtest du die Datei jetzt bearbeiten? (j/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    nano lkw_bot_web.py
fi

echo ""
echo -e "${YELLOW}6. Systemdienst einrichten...${NC}"
read -p "Als Systemdienst installieren (startet automatisch beim Booten)? (j/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Jj]$ ]]; then
    # Passe Pfade in Service-Datei an
    sed -i "s|/home/pi/lkw-bot|$INSTALL_DIR|g" lkw-bot.service
    sed -i "s|User=pi|User=$USER|g" lkw-bot.service
    sed -i "s|Group=pi|Group=$USER|g" lkw-bot.service
    
    sudo cp lkw-bot.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable lkw-bot.service
    
    echo -e "${GREEN}✓ Systemdienst installiert${NC}"
    echo "  Start:  sudo systemctl start lkw-bot.service"
    echo "  Stop:   sudo systemctl stop lkw-bot.service"
    echo "  Status: sudo systemctl status lkw-bot.service"
    echo "  Logs:   sudo journalctl -u lkw-bot.service -f"
fi

echo ""
echo -e "${YELLOW}7. Firewall konfigurieren...${NC}"
if command -v ufw &> /dev/null; then
    read -p "Port 5000 in Firewall öffnen? (j/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Jj]$ ]]; then
        sudo ufw allow 5000/tcp
        echo -e "${GREEN}✓ Port 5000 geöffnet${NC}"
    fi
else
    echo "UFW nicht installiert, überspringe..."
fi

echo ""
echo -e "${GREEN}=================================="
echo "Installation abgeschlossen!"
echo "==================================${NC}"
echo ""
echo "Nächste Schritte:"
echo ""
echo "1. Stelle sicher, dass du die Konfiguration angepasst hast:"
echo "   nano $INSTALL_DIR/lkw_bot_web.py"
echo ""
echo "2. Template-Bild bereitstellen:"
echo "   cp /pfad/zu/rentier_template.png $INSTALL_DIR/"
echo ""
echo "3. Bot starten:"
if systemctl is-enabled lkw-bot.service &> /dev/null; then
    echo "   sudo systemctl start lkw-bot.service"
else
    echo "   cd $INSTALL_DIR"
    echo "   python3 lkw_bot_web.py"
fi
echo ""
echo "4. Im Browser öffnen:"
echo "   http://localhost:5000"
echo "   oder"
echo "   http://$(hostname -I | awk '{print $1}'):5000"
echo ""
echo "Standard-Login:"
echo "   Benutzername: admin"
echo "   Passwort: admin123 (BITTE ÄNDERN!)"
echo ""
echo -e "${RED}WICHTIG: Ändere das Standard-Passwort!${NC}"
echo ""
echo "Viel Erfolg! 🚛"
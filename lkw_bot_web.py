#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LKW-Bot für Last War mit Web-Interface
Optimiert für Raspberry Pi und VMOSCloud über SSH-Tunnel
Version 2.0 - Mit Timer-Feature und verbessertem Share-Mode-Management
"""

import subprocess
import time
import cv2
import numpy as np
from PIL import Image
import pytesseract
import os
import re
import threading
import json
from datetime import datetime, timedelta
import pytz
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import logging

# Übersetzungen
TRANSLATIONS = {
    'de': {
        'app_title': 'LKW-Bot Steuerung',
        'app_subtitle': 'VMOSCloud Edition für Raspberry Pi',
        'logout': 'Abmelden',
        'status': 'Status',
        'loading': 'Lade...',
        'adb_connected': 'ADB: Verbunden',
        'adb_disconnected': 'ADB: Getrennt',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stopp',
        'statistics': 'Statistiken',
        'processed': 'Verarbeitet',
        'shared': 'Geteilt',
        'skipped': 'Übersprungen',
        'reset_stats': 'Statistiken zurücksetzen',
        'settings': 'Einstellungen',
        'use_strength_limit': 'Stärkebeschränkung nutzen',
        'max_strength': 'Maximale Stärke (M)',
        'filter_server': 'Server filtern',
        'server_number': 'Servernummer',
        'reset_interval': 'Reset-Intervall (Minuten)',
        'share_mode': 'Teilen in',
        'share_world': 'Weltchat',
        'share_alliance': 'A4O',
        'save_settings': 'Einstellungen speichern',
        'login_title': 'LKW-Bot',
        'username': 'Benutzername',
        'password': 'Passwort',
        'login_button': 'Anmelden',
        'login_info': 'Last War LKW-Sharing Bot',
        'login_subtitle': 'VMOSCloud Edition',
        'invalid_credentials': 'Ungültige Anmeldedaten',
        'stopped': 'Gestoppt',
        'running': 'Läuft',
        'paused': 'Pausiert',
        'no_action': 'Keine Aktion',
        'settings_saved': 'Einstellungen gespeichert!',
        'confirm_reset': 'Statistiken wirklich zurücksetzen?',
        'language': 'Sprache',
        'admin_dashboard': 'Admin',
        'use_timer': 'Timer verwenden',
        'timer_minutes': 'Laufzeit (Minuten)',
        'timer_remaining': 'Verbleibende Zeit',
        'request_mode_change': 'Modus-Wechsel anfordern',
        'mode_change_requested': 'Modus-Wechsel angefordert'
    },
    'en': {
        'app_title': 'Truck Bot Control',
        'app_subtitle': 'VMOSCloud Edition for Raspberry Pi',
        'logout': 'Logout',
        'status': 'Status',
        'loading': 'Loading...',
        'adb_connected': 'ADB: Connected',
        'adb_disconnected': 'ADB: Disconnected',
        'btn_start': 'Start',
        'btn_pause': 'Pause',
        'btn_stop': 'Stop',
        'statistics': 'Statistics',
        'processed': 'Processed',
        'shared': 'Shared',
        'skipped': 'Skipped',
        'reset_stats': 'Reset Statistics',
        'settings': 'Settings',
        'use_strength_limit': 'Use strength limit',
        'max_strength': 'Maximum Strength (M)',
        'filter_server': 'Filter server',
        'server_number': 'Server number',
        'reset_interval': 'Reset interval (minutes)',
        'share_mode': 'Share in',
        'share_world': 'World Chat',
        'share_alliance': 'A4O',
        'save_settings': 'Save Settings',
        'login_title': 'Truck Bot',
        'username': 'Username',
        'password': 'Password',
        'login_button': 'Login',
        'login_info': 'Last War Truck Sharing Bot',
        'login_subtitle': 'VMOSCloud Edition',
        'invalid_credentials': 'Invalid credentials',
        'stopped': 'Stopped',
        'running': 'Running',
        'paused': 'Paused',
        'no_action': 'No action',
        'settings_saved': 'Settings saved!',
        'confirm_reset': 'Really reset statistics?',
        'language': 'Language',
        'admin_dashboard': 'Admin',
        'use_timer': 'Use timer',
        'timer_minutes': 'Runtime (minutes)',
        'timer_remaining': 'Time remaining',
        'request_mode_change': 'Request mode change',
        'mode_change_requested': 'Mode change requested'
    }
}

# ================== SSH/ADB Konfiguration ==================

# SSH-Verbindungsdaten zu VMOSCloud
SSH_USER = 'socks'
SSH_HOST = 'kp.vmoscloud.com'
SSH_PORT = 26282
SSH_KEY = '41dGo-'

# Lokaler Port für ADB-Tunnel
LOCAL_ADB_PORT = 16789
# ADB-Port auf VMOSCloud
REMOTE_ADB = 'localhost:5555'

# ================== Flask Setup ==================

app = Flask(__name__)
app.secret_key = 'dein-geheimer-schluessel-hier-ändern-123!@#'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ================== Logging ==================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('lkw-bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================== Dateipfade ==================

TEMPLATE_FILE = 'rentier_template.png'
STAERKEN_FILE = 'lkw_staerken.txt'
USERS_FILE = 'users.json'
AUDIT_LOG_FILE = 'audit_log.json'
MAINTENANCE_FILE = 'maintenance.json'
STATS_FILE = 'truck_stats.json'
MODE_REQUESTS_FILE = 'mode_requests.json'

# ================== User System ==================

class User(UserMixin):
    def __init__(self, username, password, role='user', blocked=False, can_choose_share_mode=True, forced_share_mode=None):
        self.id = username
        self.username = username
        self.password = password
        self.role = role
        self.blocked = blocked
        self.can_choose_share_mode = can_choose_share_mode
        self.forced_share_mode = forced_share_mode

def init_users():
    """Initialisiere Benutzer-Datenbank"""
    if not os.path.exists(USERS_FILE):
        users = {
            'admin': {
                'password': generate_password_hash('rREq8/1F4m#'),
                'role': 'admin',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
            },
            'All4One': {
                'password': generate_password_hash('52B1z_'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
            },
            'Server39': {
                'password': generate_password_hash('!3Z4d5'),
                'role': 'user',
                'blocked': False,
                'can_choose_share_mode': True,
                'forced_share_mode': None
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)

def load_users():
    """Lade User-Datenbank"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    """Speichere User-Datenbank"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def log_audit(username, action, details=""):
    """Log Benutzeraktionen"""
    if not os.path.exists(AUDIT_LOG_FILE):
        logs = []
    else:
        with open(AUDIT_LOG_FILE, 'r') as f:
            logs = json.load(f)
    
    from datetime import datetime
    import pytz
    
    # Deutsche Zeit
    tz = pytz.timezone('Europe/Berlin')
    timestamp = datetime.now(tz).strftime('%d.%m.%Y %H:%M:%S')
    
    logs.append({
        'username': username,
        'action': action,
        'details': details,
        'timestamp': timestamp
    })
    
    # Nur letzte 500 Einträge behalten
    logs = logs[-500:]
    
    with open(AUDIT_LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=2)

@login_manager.user_loader
def load_user(username):
    users = load_users()
    if username in users:
        user_data = users[username]
        return User(
            username, 
            user_data['password'], 
            user_data['role'], 
            user_data.get('blocked', False),
            user_data.get('can_choose_share_mode', True),
            user_data.get('forced_share_mode', None)
        )
    return None

# Initialisiere Users beim Start
init_users()

# ================== Bot-Steuerung ==================

class BotController:
    def __init__(self):
        self.running = False
        self.paused = False
        self.thread = None
        self.ssh_process = None
        self.status = "Gestoppt"
        self.last_action = ""
        self.lock = threading.Lock()
        self.current_user = None
        
        # Timer-Funktionen
        self.use_timer = False
        self.timer_duration_minutes = 60
        self.timer_start_time = None
        self.timer_thread = None
        
        # Einstellungen
        self.use_limit = False
        self.strength_limit = 60.0
        self.use_server_filter = False
        self.server_number = "49"
        self.reset_interval = 15
        self.share_mode = "world"
        self.adb_connected = False
        
        # Mode-Change-Requests
        self.mode_change_requests = self.load_mode_change_requests()
        
        # Fehlerüberwachung
        self.last_success_time = time.time()
        self.error_count = 0
        self.maintenance_mode = self.load_maintenance_mode()
        
        # Statistiken
        self.trucks_processed = 0
        self.trucks_shared = 0
        self.trucks_skipped = 0
        
        # Maintenance Mode
        self.maintenance_mode = self.load_maintenance_mode()
        self.last_success_time = time.time()  # Letzte erfolgreiche Aktion
        self.no_truck_threshold = 300  # 5 Minuten ohne Fund = Problem
        
    def load_mode_change_requests(self):
        """Lade Mode-Change-Requests"""
        if os.path.exists(MODE_REQUESTS_FILE):
            with open(MODE_REQUESTS_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def save_mode_change_requests(self):
        """Speichere Mode-Change-Requests"""
        with open(MODE_REQUESTS_FILE, 'w') as f:
            json.dump(self.mode_change_requests, f, indent=2)
    
    def request_mode_change(self, username, requested_mode):
        """Fordere Modus-Wechsel an"""
        self.mode_change_requests[username] = {
            'requested_mode': requested_mode,
            'timestamp': datetime.now().isoformat(),
            'status': 'pending'
        }
        self.save_mode_change_requests()
        logger.info(f"Mode change requested by {username}: {requested_mode}")
        
    def approve_mode_change(self, username):
        """Genehmige Modus-Wechsel"""
        if username in self.mode_change_requests:
            req = self.mode_change_requests[username]
            users = load_users()
            if username in users:
                users[username]['forced_share_mode'] = req['requested_mode']
                users[username]['can_choose_share_mode'] = True
                save_users(users)
                req['status'] = 'approved'
                self.save_mode_change_requests()
                
                # Wenn dieser User gerade den Bot nutzt, aktualisiere den Modus
                if self.current_user == username:
                    self.share_mode = req['requested_mode']
                
                return True
        return False
    
    def reject_mode_change(self, username):
        """Lehne Modus-Wechsel ab"""
        if username in self.mode_change_requests:
            self.mode_change_requests[username]['status'] = 'rejected'
            self.save_mode_change_requests()
            return True
        return False
    
    def get_remaining_time_seconds(self):
        """Gibt die verbleibende Zeit in Sekunden zurück"""
        if not self.use_timer or not self.timer_start_time:
            return None
        
        elapsed = time.time() - self.timer_start_time
        remaining = (self.timer_duration_minutes * 60) - elapsed
        return max(0, remaining)
    
    def check_timer(self):
        """Überprüft den Timer und stoppt den Bot wenn Zeit abgelaufen"""
        while self.running and self.use_timer:
            remaining = self.get_remaining_time_seconds()
            if remaining is not None and remaining <= 0:
                logger.info(f"Timer abgelaufen - Bot wird gestoppt")
                self.stop()
                break
            time.sleep(1)
        
    def load_maintenance_mode(self):
        """Lade Maintenance-Status"""
        if os.path.exists(MAINTENANCE_FILE):
            with open(MAINTENANCE_FILE, 'r') as f:
                data = json.load(f)
                return data.get('enabled', False)
        return False
    
    def set_maintenance_mode(self, enabled):
        """Setze Maintenance-Mode"""
        self.maintenance_mode = enabled
        with open(MAINTENANCE_FILE, 'w') as f:
            json.dump({'enabled': enabled}, f)
        logger.info(f"Maintenance Mode: {'Aktiviert' if enabled else 'Deaktiviert'}")
    
    def check_auto_maintenance(self):
        """Prüfe ob automatischer Maintenance-Mode aktiviert werden soll"""
        if self.maintenance_mode:
            return  # Bereits im Maintenance-Mode
        
        time_since_success = time.time() - self.last_success_time
        if time_since_success > self.no_truck_threshold:
            logger.warning(f"Keine LKWs seit {int(time_since_success)}s - aktiviere Maintenance-Mode")
            self.set_maintenance_mode(True)
    
    def log_truck_stat(self, strength, server):
        """Speichere Truck-Statistik"""
        if not os.path.exists(STATS_FILE):
            stats = []
        else:
            try:
                with open(STATS_FILE, 'r') as f:
                    content = f.read().strip()
                    if content:
                        stats = json.loads(content)
                    else:
                        stats = []
            except (json.JSONDecodeError, ValueError):
                logger.error(f"Korrupte Stats-Datei, erstelle neue")
                stats = []
        
        # Deutsche Zeit für Timestamp
        tz = pytz.timezone('Europe/Berlin')
        timestamp = datetime.now(tz).isoformat()
        
        stats.append({
            'strength': strength,
            'server': server,
            'timestamp': timestamp,
            'user': self.current_user
        })
        
        # Behalte nur letzte 1000 Einträge
        stats = stats[-1000:]
        
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump(stats, f, indent=2)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Stats: {e}")
    
    def setup_ssh_tunnel(self):
        """Erstellt SSH-Tunnel zu VMOSCloud"""
        try:
            # Prüfe ob Tunnel bereits läuft
            result = subprocess.run(['pgrep', '-f', f':{LOCAL_ADB_PORT}:'], 
                                  capture_output=True, text=True)
            if result.stdout:
                logger.info("SSH-Tunnel läuft bereits")
                return True
            
            # Starte SSH-Tunnel
            cmd = [
                'ssh',
                '-oHostKeyAlgorithms=+ssh-rsa',
                '-oStrictHostKeyChecking=no',
                '-oServerAliveInterval=60',
                '-oServerAliveCountMax=3',
                SSH_HOST,
                '-p', str(SSH_PORT),
                '-L', f'{LOCAL_ADB_PORT}:{REMOTE_ADB}',
                '-Nf'
            ]
            
            logger.info("Starte SSH-Tunnel...")
            self.ssh_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(3)  # Warte auf Verbindungsaufbau
            
            # Verbinde ADB
            adb_cmd = ['adb', 'connect', f'localhost:{LOCAL_ADB_PORT}']
            result = subprocess.run(adb_cmd, capture_output=True, text=True)
            
            if 'connected' in result.stdout.lower():
                logger.info("ADB erfolgreich verbunden")
                self.adb_connected = True
                return True
            else:
                logger.error(f"ADB-Verbindung fehlgeschlagen: {result.stdout}")
                return False
                
        except Exception as e:
            logger.error(f"SSH-Tunnel-Fehler: {e}")
            return False
    
    def close_ssh_tunnel(self):
        """Schließt SSH-Tunnel"""
        try:
            # Trenne ADB
            subprocess.run(['adb', 'disconnect', f'localhost:{LOCAL_ADB_PORT}'])
            
            # Beende SSH-Prozess
            subprocess.run(['pkill', '-f', f':{LOCAL_ADB_PORT}:'])
            logger.info("SSH-Tunnel geschlossen")
            self.adb_connected = False
        except Exception as e:
            logger.error(f"Fehler beim Schließen des Tunnels: {e}")
    
    def make_screenshot(self, filename='screen.png'):
        """Erstellt Screenshot über ADB"""
        try:
            adb_device = f'localhost:{LOCAL_ADB_PORT}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'screencap', '-p', f'/sdcard/{filename}'], 
                         timeout=10)
            subprocess.run(['adb', '-s', adb_device, 'pull', f'/sdcard/{filename}', filename], 
                         timeout=10)
            return os.path.exists(filename)
        except Exception as e:
            logger.error(f"Screenshot-Fehler: {e}")
            return False
    
    def click(self, x, y):
        """Klickt auf Koordinaten"""
        try:
            adb_device = f'localhost:{LOCAL_ADB_PORT}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'tap', str(x), str(y)])
            return True
        except Exception as e:
            logger.error(f"Klick-Fehler: {e}")
            return False
    
    def swipe(self, x1, y1, x2, y2, duration=500):
        """Swipe-Geste"""
        try:
            adb_device = f'localhost:{LOCAL_ADB_PORT}'
            subprocess.run(['adb', '-s', adb_device, 'shell', 'input', 'swipe', 
                          str(x1), str(y1), str(x2), str(y2), str(duration)])
            return True
        except Exception as e:
            logger.error(f"Swipe-Fehler: {e}")
            return False
    
    def load_staerken(self):
        """Lädt bereits geteilte Stärken"""
        if os.path.exists(STAERKEN_FILE):
            with open(STAERKEN_FILE, 'r') as f:
                return f.read().splitlines()
        return []
    
    def save_staerke(self, staerke):
        """Speichert geteilte Stärke"""
        staerken = self.load_staerken()
        if staerke not in staerken:
            staerken.append(staerke)
            with open(STAERKEN_FILE, 'w') as f:
                f.write('\n'.join(staerken))
    
    def reset_staerken(self):
        """Setzt die Stärken-Liste zurück"""
        if os.path.exists(STAERKEN_FILE):
            os.remove(STAERKEN_FILE)
        logger.info("Stärken-Liste zurückgesetzt")
    
    def find_template(self, screenshot_path):
        """Sucht nach Template im Screenshot"""
        if not os.path.exists(TEMPLATE_FILE):
            logger.error(f"Template-Datei '{TEMPLATE_FILE}' nicht gefunden!")
            return None
        
        screenshot = cv2.imread(screenshot_path)
        template = cv2.imread(TEMPLATE_FILE)
        
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        
        if max_val > 0.8:
            h, w = template.shape[:2]
            return (max_loc[0], max_loc[1], w, h)
        return None
    
    def extract_text_from_region(self, screenshot_path, x, y, w, h):
        """Extrahiert Text aus Region mit OCR"""
        img = cv2.imread(screenshot_path)
        region = img[y:y+h, x:x+w]
        
        # Verbesserung für OCR
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
        
        text = pytesseract.image_to_string(thresh, lang='deu+eng')
        return text
    
    def extract_truck_info(self):
        """Extrahiert LKW-Informationen aus Screenshot"""
        if not self.make_screenshot():
            return None
        
        location = self.find_template('screen.png')
        if not location:
            return None
        
        x, y, w, h = location
        
        # OCR für Stärke (rechts vom Template)
        strength_text = self.extract_text_from_region('screen.png', x+w, y, 150, h)
        strength_match = re.search(r'(\d+[,.]?\d*)\s*M', strength_text)
        
        # OCR für Server (über dem Template)
        server_text = self.extract_text_from_region('screen.png', x, y-50, w+150, 50)
        server_match = re.search(r'Server\s*(\d+)', server_text)
        
        if strength_match:
            strength = strength_match.group(1).replace(',', '.')
            server = server_match.group(1) if server_match else "?"
            
            return {
                'strength': float(strength),
                'server': server,
                'coords': (x + w//2, y + h//2)
            }
        return None
    
    def share_truck(self):
        """Teilt einen LKW"""
        # Klick auf Teilen-Button
        self.click(540, 1500)  # Anpassbar je nach Auflösung
        time.sleep(2)
        
        # Wähle Chat-Typ basierend auf share_mode
        if self.share_mode == 'alliance':
            # A4O Chat
            self.click(300, 800)
        else:
            # Weltchat
            self.click(500, 800)
        
        time.sleep(1)
        
        # Bestätigen
        self.click(540, 1200)
        time.sleep(2)
    
    def bot_loop(self):
        """Haupt-Bot-Schleife"""
        logger.info("Bot-Schleife gestartet")
        
        # SSH-Tunnel einrichten
        if not self.setup_ssh_tunnel():
            self.status = "SSH-Fehler"
            return
        
        self.status = "Läuft"
        self.last_action = "Bot gestartet"
        
        # Timer-Thread starten wenn aktiviert
        if self.use_timer:
            self.timer_start_time = time.time()
            self.timer_thread = threading.Thread(target=self.check_timer, daemon=True)
            self.timer_thread.start()
            logger.info(f"Timer gestartet für {self.timer_duration_minutes} Minuten")
        
        # Starte Reset-Timer
        reset_thread = threading.Thread(target=self.reset_timer, daemon=True)
        reset_thread.start()
        
        # Deutsche Zeitzone
        tz = pytz.timezone('Europe/Berlin')
        
        while self.running:
            # Pausieren wenn nötig
            if self.paused:
                self.status = "Pausiert"
                time.sleep(1)
                continue
            
            # Maintenance-Mode
            if self.maintenance_mode:
                self.status = "Maintenance-Mode"
                time.sleep(10)
                continue
            
            try:
                truck_info = self.extract_truck_info()
                
                if truck_info:
                    self.trucks_processed += 1
                    strength_str = f"{truck_info['strength']:.1f}M"
                    server_str = truck_info['server']
                    
                    # Log Statistik
                    self.log_truck_stat(strength_str, server_str)
                    
                    # Prüfe Filter
                    skip = False
                    
                    # Stärke-Filter
                    if self.use_limit and truck_info['strength'] > self.strength_limit:
                        skip = True
                        self.last_action = f"LKW {strength_str} übersprungen (zu stark)"
                    
                    # Server-Filter
                    if self.use_server_filter and server_str != self.server_number:
                        skip = True
                        self.last_action = f"LKW Server {server_str} übersprungen"
                    
                    # Bereits geteilt?
                    truck_id = f"{server_str}/{strength_str}"
                    if truck_id in self.load_staerken():
                        skip = True
                        self.last_action = f"LKW {truck_id} bereits geteilt"
                    
                    if skip:
                        self.trucks_skipped += 1
                    else:
                        # Teile LKW
                        self.share_truck()
                        self.save_staerke(truck_id)
                        self.trucks_shared += 1
                        
                        zeit = datetime.now(tz).strftime('%H:%M:%S')
                        self.last_action = f"[{zeit}] LKW {truck_id} geteilt ({self.share_mode})"
                        logger.info(self.last_action)
                        
                        # Reset Fehler-Counter
                        self.last_success_time = time.time()
                        self.error_count = 0
                        
                        # Warte nach Teilen
                        time.sleep(5)
                    
                    # Zurück und weiter suchen
                    self.click(100, 100)  # Zurück-Button
                    time.sleep(2)
                    self.swipe(540, 1000, 540, 500)  # Nach oben scrollen
                    time.sleep(2)
                    
                else:
                    # Kein LKW gefunden
                    self.last_action = "Suche nach LKWs..."
                    self.swipe(540, 1000, 540, 500)
                    time.sleep(3)
                    
                    # Fehlerüberwachung
                    self.error_count += 1
                    if self.error_count > 30:
                        logger.warning("Lange keine LKWs gefunden")
                        self.error_count = 0
                
            except Exception as e:
                logger.error(f"Fehler in Bot-Schleife: {e}")
                self.last_action = f"Fehler: {str(e)}"
                time.sleep(5)
            
            # Prüfe Maintenance-Mode
            self.check_auto_maintenance()
        
        # Cleanup
        self.close_ssh_tunnel()
        self.status = "Gestoppt"
        logger.info("Bot-Schleife beendet")
    
    def reset_timer(self):
        """Timer für automatischen Reset der Stärken-Liste"""
        while self.running:
            time.sleep(self.reset_interval * 60)
            if self.running:
                self.reset_staerken()
                self.last_action = f"Stärken-Liste nach {self.reset_interval} Min. zurückgesetzt"
    
    def start(self):
        """Startet den Bot"""
        if not self.running:
            self.running = True
            self.paused = False
            self.thread = threading.Thread(target=self.bot_loop, daemon=True)
            self.thread.start()
            logger.info(f"Bot gestartet von {self.current_user}")
    
    def pause(self):
        """Pausiert/Fortsetzt den Bot"""
        if self.running:
            self.paused = not self.paused
            logger.info(f"Bot {'pausiert' if self.paused else 'fortgesetzt'}")
    
    def stop(self):
        """Stoppt den Bot"""
        self.running = False
        self.use_timer = False  # Timer deaktivieren
        self.timer_start_time = None
        if self.thread:
            self.thread.join(timeout=10)
        if self.timer_thread:
            self.timer_thread.join(timeout=5)
        logger.info("Bot gestoppt")

# Globale Bot-Instanz
bot = BotController()

# ================== Flask Routes ==================

def get_language():
    """Holt die aktuelle Sprache aus der Session"""
    return session.get('language', 'de')

def translate(key):
    """Übersetzt einen Schlüssel in die aktuelle Sprache"""
    lang = get_language()
    return TRANSLATIONS.get(lang, TRANSLATIONS['de']).get(key, key)

@app.route('/set_language/<lang>')
def set_language(lang):
    """Setzt die Sprache"""
    if lang in TRANSLATIONS:
        session['language'] = lang
    return redirect(request.referrer or url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        if username in users:
            user_data = users[username]
            if user_data.get('blocked', False):
                error = "Benutzer ist gesperrt"
                return render_template('login.html', error=error, t=translate, lang=get_language())
            
            if check_password_hash(user_data['password'], password):
                user = User(username, user_data['password'], user_data['role'], user_data.get('blocked', False))
                login_user(user)
                log_audit(username, 'Login', '')
                return redirect(url_for('index'))
        
        error = translate('invalid_credentials')
        return render_template('login.html', error=error, t=translate, lang=get_language())
    
    return render_template('login.html', t=translate, lang=get_language())

@app.route('/logout')
@login_required
def logout():
    log_audit(current_user.username, 'Logout', '')
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', t=translate, lang=get_language(), user=current_user)

@app.route('/api/status')
@login_required
def api_status():
    remaining_time = None
    if bot.use_timer:
        remaining_seconds = bot.get_remaining_time_seconds()
        if remaining_seconds:
            minutes = int(remaining_seconds // 60)
            seconds = int(remaining_seconds % 60)
            remaining_time = f"{minutes:02d}:{seconds:02d}"
    
    return jsonify({
        'running': bot.running,
        'paused': bot.paused,
        'status': bot.status,
        'last_action': bot.last_action,
        'trucks_processed': bot.trucks_processed,
        'trucks_shared': bot.trucks_shared,
        'trucks_skipped': bot.trucks_skipped,
        'adb_connected': bot.adb_connected,
        'current_user': bot.current_user,
        'maintenance_mode': bot.maintenance_mode,
        'timer_remaining': remaining_time,
        'use_timer': bot.use_timer
    })

@app.route('/api/start', methods=['POST'])
@login_required
def api_start():
    # Queue-System: Admin hat Priorität
    users = load_users()
    if current_user.username in users and users[current_user.username].get('blocked', False):
        return jsonify({'error': 'User is blocked'}), 403
    
    with bot.lock:
        if bot.current_user and bot.current_user != current_user.username:
            if current_user.role != 'admin':
                return jsonify({'error': f'Bot wird bereits von {bot.current_user} verwendet'}), 409
            # Admin übernimmt
            bot.stop()
        
        bot.current_user = current_user.username
        bot.start()
        log_audit(current_user.username, 'Start Bot', f'Timer: {bot.use_timer}, Duration: {bot.timer_duration_minutes}min')
    
    return jsonify({'success': True})

@app.route('/api/pause', methods=['POST'])
@login_required
def api_pause():
    bot.pause()
    log_audit(current_user.username, 'Pause Bot', '')
    return jsonify({'success': True})

@app.route('/api/stop', methods=['POST'])
@login_required
def api_stop():
    with bot.lock:
        bot.stop()
        bot.current_user = None
        log_audit(current_user.username, 'Stop Bot', '')
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    if request.method == 'POST':
        # Prüfe ob User gesperrt ist
        users = load_users()
        if current_user.username in users and users[current_user.username].get('blocked', False):
            return jsonify({'error': 'User is blocked'}), 403
        
        data = request.json
        bot.use_limit = data.get('use_limit', False)
        bot.strength_limit = float(data.get('strength_limit', 60))
        bot.use_server_filter = data.get('use_server_filter', False)
        bot.server_number = data.get('server_number', '49')
        bot.reset_interval = int(data.get('reset_interval', 15))
        
        # Timer-Einstellungen
        bot.use_timer = data.get('use_timer', False)
        bot.timer_duration_minutes = int(data.get('timer_duration', 60))
        
        # Share-Mode: Prüfe ob User wählen darf
        user_data = users.get(current_user.username, {})
        if user_data.get('can_choose_share_mode', True):
            bot.share_mode = data.get('share_mode', 'world')
        else:
            # User darf nicht wählen - nutze forced_mode
            bot.share_mode = user_data.get('forced_share_mode', 'world')
        
        log_audit(current_user.username, 'Change Settings', 
                 f"limit={data.get('use_limit')}, strength={data.get('strength_limit')}, "
                 f"server={data.get('server_number')}, mode={bot.share_mode}, "
                 f"timer={bot.use_timer}, duration={bot.timer_duration_minutes}")
        
        return jsonify({'success': True})
    else:
        # Prüfe ob User share_mode wählen darf
        users = load_users()
        user_data = users.get(current_user.username, {})
        can_choose = user_data.get('can_choose_share_mode', True)
        forced_mode = user_data.get('forced_share_mode', None)
        
        # Prüfe ob Mode-Change-Request existiert
        mode_request = bot.mode_change_requests.get(current_user.username, {})
        
        return jsonify({
            'use_limit': bot.use_limit,
            'strength_limit': bot.strength_limit,
            'use_server_filter': bot.use_server_filter,
            'server_number': bot.server_number,
            'reset_interval': bot.reset_interval,
            'share_mode': forced_mode if forced_mode and not can_choose else bot.share_mode,
            'can_choose_share_mode': can_choose,
            'forced_share_mode': forced_mode,
            'use_timer': bot.use_timer,
            'timer_duration': bot.timer_duration_minutes,
            'mode_change_request': mode_request.get('status', None),
            'requested_mode': mode_request.get('requested_mode', None)
        })

@app.route('/api/request_mode_change', methods=['POST'])
@login_required
def api_request_mode_change():
    """Fordert einen Modus-Wechsel an"""
    data = request.json
    requested_mode = data.get('requested_mode')
    
    if requested_mode in ['world', 'alliance']:
        bot.request_mode_change(current_user.username, requested_mode)
        log_audit(current_user.username, 'Request Mode Change', requested_mode)
        return jsonify({'success': True})
    
    return jsonify({'error': 'Invalid mode'}), 400

@app.route('/api/reset_stats', methods=['POST'])
@login_required
def api_reset_stats():
    bot.trucks_processed = 0
    bot.trucks_shared = 0
    bot.trucks_skipped = 0
    log_audit(current_user.username, 'Reset Statistics', '')
    return jsonify({'success': True})

# Admin Routes
@app.route('/admin')
@login_required
def admin():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('admin.html', user=current_user)

@app.route('/api/admin/users')
@login_required
def api_admin_users():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    user_list = []
    for username, data in users.items():
        user_list.append({
            'username': username,
            'role': data['role'],
            'blocked': data.get('blocked', False),
            'can_choose_share_mode': data.get('can_choose_share_mode', True),
            'forced_share_mode': data.get('forced_share_mode', None)
        })
    return jsonify({'users': user_list})

@app.route('/api/admin/user/toggle_block/<username>', methods=['POST'])
@login_required
def api_admin_toggle_block(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    users = load_users()
    if username in users:
        users[username]['blocked'] = not users[username].get('blocked', False)
        save_users(users)
        log_audit(current_user.username, 'Toggle User Block', username)
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/user/set_share_mode/<username>', methods=['POST'])
@login_required
def api_admin_set_share_mode(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    users = load_users()
    if username in users:
        users[username]['can_choose_share_mode'] = data.get('can_choose', True)
        users[username]['forced_share_mode'] = data.get('forced_mode', None)
        save_users(users)
        log_audit(current_user.username, 'Set User Share Mode', f"{username}: {data}")
        return jsonify({'success': True})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/admin/mode_requests')
@login_required
def api_admin_mode_requests():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({'requests': bot.mode_change_requests})

@app.route('/api/admin/approve_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_approve_mode_change(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if bot.approve_mode_change(username):
        log_audit(current_user.username, 'Approve Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/reject_mode_change/<username>', methods=['POST'])
@login_required
def api_admin_reject_mode_change(username):
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if bot.reject_mode_change(username):
        log_audit(current_user.username, 'Reject Mode Change', username)
        return jsonify({'success': True})
    return jsonify({'error': 'Request not found'}), 404

@app.route('/api/admin/stats')
@login_required
def api_admin_stats():
    """API für Truck-Statistiken"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Zeitbereich aus Query-Parametern
    start_str = request.args.get('start', '')
    end_str = request.args.get('end', '')
    
    # Lade Statistiken
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    all_stats = json.loads(content)
                else:
                    all_stats = []
        except (json.JSONDecodeError, ValueError):
            logger.error("Fehler beim Laden der Statistiken")
            all_stats = []
    else:
        all_stats = []
    
    # Filter nach Zeitbereich wenn angegeben
    filtered_stats = []
    for stat in all_stats:
        try:
            stat_time = datetime.fromisoformat(stat['timestamp'].replace('Z', '+00:00'))
            include = True
            
            if start_str:
                start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                if stat_time < start_time:
                    include = False
            
            if end_str:
                end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                if stat_time > end_time:
                    include = False
            
            if include:
                filtered_stats.append(stat)
        except Exception as e:
            logger.error(f"Fehler beim Filtern der Statistik: {e}")
            continue
    
    return jsonify({'trucks': filtered_stats})

@app.route('/api/admin/audit_log')
@login_required
def api_admin_audit_log():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, 'r') as f:
            logs = json.load(f)
    else:
        logs = []
    
    # Nur letzte 100 Einträge
    return jsonify({'logs': logs[-100:]})

@app.route('/api/admin/maintenance', methods=['POST'])
@login_required
def api_admin_maintenance():
    if current_user.role != 'admin':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.json
    enabled = data.get('enabled', False)
    bot.set_maintenance_mode(enabled)
    log_audit(current_user.username, 'Set Maintenance Mode', str(enabled))
    
    return jsonify({'success': True})

@app.route('/stats')
@login_required
def stats_page():
    if current_user.role != 'admin':
        return redirect(url_for('index'))
    return render_template('stats.html', user=current_user)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
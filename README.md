# KIT KlimaCrawler 🌍

Pipeline zur systematischen Erfassung von Energie- und Klimarichtlinien bayerischer Kommunen für die **GraphRAG-Analyse**.

---

## 🛠 Voraussetzungen

- Python 3.9+ (empfohlen: 3.10)
- macOS, Linux oder Windows
- Stabile Internetverbindung
- Ausreichend Laufzeit (Großstädte: > 10 Stunden)

---

## 📦 Setup & Installation

### 1️⃣ Repository klonen

```bash
git clone <repository-url>
cd KIT_KlimaCrawler
```

---

### 2️⃣ Virtuelle Umgebung erstellen (wi2026)

#### Windows (PowerShell)

```powershell
python -m venv wi2026
.\wi2026\Scripts\Activate.ps1
```

#### Windows (CMD)

```cmd
python -m venv wi2026
wi2026\Scripts\activate
```

#### macOS / Linux

```bash
python3 -m venv wi2026
source wi2026/bin/activate
```

#### Alternative: Conda

```bash
conda create -n wi2026 python=3.10 -y
conda activate wi2026
```

---

### 3️⃣ Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

---

## 🏃‍♂️ Crawl starten

Der Crawler verarbeitet die Job-Queue aus:

```
crawler/data/db/crawl.sqlite
```

### Einzel-Lauf (eine Kommune)

```bash
python3 -m crawler.scripts.run_worker --limit 1
```

### Batch-Lauf (z. B. 100 Kommunen)

```bash
python3 -m crawler.scripts.run_worker --limit 100
```

---

## 👯 Verteiltes Arbeiten (Sharding)

Für paralleles Crawling Bayerns werden vorab aufgeteilte Datenbank-Pakete genutzt.

1. **Paket laden**  
   Lade einen Ordner (z. B. `pkg_05`) aus der Cloud.

2. **Platzieren**  
   Kopiere die enthaltene `crawl.sqlite` nach:
   ```
   crawler/data/db/
   ```

3. **Starten**  
   Führe den Crawler aus, bis alle Jobs erledigt sind.

4. **Upload**  
   Benenne die Datei um in:
   ```
   pkg_05_DONE_Name.sqlite
   ```
   und lade sie wieder hoch.

---

## ☕ WICHTIG: Standby verhindern

Wenn der Rechner in den Ruhezustand geht, stoppt der Crawl.

### macOS (Terminal-Trick)

```bash
caffeinate -i python3 -m crawler.scripts.run_worker --limit 1
```

Der Mac bleibt wach, bis der Prozess endet.

### Windows

Nutze Tools wie:
- Caffeine
- PowerToys Awake

---

## 📊 Monitoring & Erfolgskontrolle

### Fortschritt prüfen

```bash
sqlite3 crawler/data/db/crawl.sqlite "SELECT segment_type, COUNT(*) FROM segments GROUP BY segment_type;"
```

### Erfolgreicher Lauf

- `run_worker` beendet sich ohne Fehlermeldung
- `seed_jobs.status` wechselt zu `done`
- Neue Einträge in:
  - `documents_raw`
  - `segments`

---

## ⚠ Fehlerquellen

- **Netzwerk**: VPN-Abbruch oder instabiles WLAN
- **Tools**: `pdftotext` muss im Systempfad verfügbar sein
- **Standby**: Rechner ging während eines Langlaufs schlafen

---

## 📌 Kurzfassung (TL;DR)

```bash
git clone <repository-url>
cd KIT_KlimaCrawler
python3 -m venv venv && source venv/bin/activate  # macOS
pip install -r requirements.txt
caffeinate -i python3 -m crawler.scripts.run_worker --limit 1
```
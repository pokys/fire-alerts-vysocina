# Hasiči Vysočina — kalendář zásahů

Automaticky generovaný iCalendar feed událostí hasičů na Vysočině.
Data pochází z [webohled.hasici-vysocina.cz](http://webohled.hasici-vysocina.cz).

---

## 📅 Přihlášení ke kalendáři

Zkopíruj URL a vlož ji do své kalendářové aplikace (Přidat kalendář → Z URL).

| Kalendář | URL |
|---|---|
| 🔴 **Okres Pelhřimov** | `https://raw.githubusercontent.com/pokys/fire-alerts-vysocina/main/calendar-pelhrimov.ics` |
| 🟠 **Celá Vysočina** | `https://raw.githubusercontent.com/pokys/fire-alerts-vysocina/main/calendar-vysocina.ics` |

> **iOS / macOS:** Nastavení → Kalendář → Přidat účet → Jiný → Přidat přihlášený kalendář
> **Android (Google Calendar):** calendar.google.com → Další kalendáře (+) → Z URL
> **Outlook:** Přidat kalendář → Přihlásit se k internetu

---

## 📋 Co je v každé události

**Název:** `🔥 saze v komíně - Horní Cerekev`
— emoji podle typu zásahu + podtyp + obec

| Emoji | Typ zásahu |
|---|---|
| 🔥 | Požár |
| 🚗 | Dopravní nehoda |
| ☣️ | Únik nebezpečných látek |
| 🛠️ | Technická pomoc |
| 🚑 | Záchrana osob a zvířat |
| ⚠️ | Planý poplach |

**Popis události:**
```
📍 Sídliště Pražská, Havlíčkův Brod
💬 Zastavení unikajícího plynu.

🚒 CAS (CHS Havlíčkův Brod)
🚒 DA (SDH Pacov) ×2
```

**Mapa:** událost obsahuje GPS souřadnice — kliknutím se otevře Apple Maps / Google Maps přímo na místě zásahu.

---

## 🔔 Telegram notifikace

Při každém novém zásahu přijde zpráva do Telegram chatu. Podporovány jsou dva nezávislé kanály:

| Secret | Popis |
|---|---|
| `TELEGRAM_CHAT_ID` | Zásahy v **okrese Pelhřimov** |
| `TELEGRAM_CHAT_ID_VYSOCINA` | Zásahy v **celém kraji Vysočina** |

**Nastavení:**
1. Vytvoř bota přes [@BotFather](https://t.me/BotFather) → `/newbot` → zkopíruj token
2. Zjisti Chat ID — pošli botovi zprávu a otevři `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. V GitHub repozitáři přidej secrets (`Settings → Secrets → Actions`):
   - `TELEGRAM_BOT_TOKEN` — token bota (povinné)
   - `TELEGRAM_CHAT_ID` — chat ID pro Pelhřimov (volitelné)
   - `TELEGRAM_CHAT_ID_VYSOCINA` — chat ID pro Vysočinu (volitelné)

Bez nakonfigurovaných secrets se notifikace tiše přeskočí. Lokálně v Dockeru:
```bash
TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... TELEGRAM_CHAT_ID_VYSOCINA=... docker compose up
```

---

## ⚙️ Technické detaily

- Data se aktualizují přibližně každých 30 minut přes GitHub Actions
- Zobrazují se události za posledních **48 hodin**
- Souřadnice jsou převáděny z S-JTSK (gis1/gis2) na WGS84
- Technika (vozidla) se načítá z doplňkového API endpointu
- Formát: RFC 5545 iCalendar, GPS: RFC 5870 `geo:` URI

## 🛠️ Lokální spuštění

**Python:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 generate.py
```

**Docker:**
```bash
docker compose up          # spustí generátor, každých 30 minut přegeneruje kalendáře
docker compose up -d       # na pozadí
INTERVAL=300 docker compose up  # vlastní interval v sekundách
```

Vygenerované soubory `calendar-pelhrimov.ics` a `calendar-vysocina.ics` se objeví přímo ve složce repozitáře.

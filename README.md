# ReepL V5 — Free Discord Translator

ReepL posts replies translating Discord channel messages into EN, DE, FR or ESP. Buttons EN/DE/FR/ESP/OFF can be operated by all users and change the **entire channel**, not individual user preferences. The `/translator` and `/translator_status` commands remain available.

## What changed from V4

- Replaced unofficial Google Translate scraping (`deep-translator`) with MyMemory's public REST translation endpoint. No API key needed. The public service has usage limits and can be unavailable or throttle requests.
- Local language detection with `langdetect`: messages already in the destination language are skipped, and uncertain short messages may be skipped.
- Shared request queue with a gap between outgoing requests; a SQLite cache reduces repeat requests.
- Conservative local daily budget (default 4,500 characters in total, UTC day). This is deliberately below the public anonymous allowance to avoid accidental overuse. If the public quota is exhausted, translations pause until it resets.
- Original message is kept, translations are replies. Text longer than 450 UTF-8 bytes is skipped, rather than sent with unsupported API parameters.

## Deploy on Railway using existing GitHub repository

1. Back up the current project and current SQLite database if persistent storage is used.
2. Upload the CONTENTS of this ZIP into the root of your existing GitHub repository, replacing `bot.py`, `requirements.txt`, etc. Do **not** upload `.env` or your bot token.
3. Railway → project → service → Settings: root directory `/` if these files are at repo root; start command `python bot.py`.
4. Keep `DISCORD_TOKEN` in Railway → Variables.
5. Optional Railway variables:
   - `DATABASE_PATH=/data/translator.sqlite3` only if you have a persistent volume mounted at `/data`. If you do not, you can omit this variable, but channel settings/cache reset on redeployment.
   - `MAX_PARALLEL_TRANSLATIONS=1`
   - `DAILY_CHAR_LIMIT=4500` (set LOWER if you wish; 0 disables the local budget but does not remove the provider's limit)
   - `MIN_REQUEST_GAP_SECONDS=2.5`
   - `MYMEMORY_EMAIL=` optional contact address for the public API; not required.
6. Commit; check Railway Deploy Logs for `Connected as ReepL`.
7. In Discord, use `/translator`, select a target and write a clear sentence in a different language. The bot needs Message Content Intent, Send Messages, Read Message History, View Channels permissions.

### Limits and privacy

MyMemory receives the message content and source/target language in an API call. Do not enable translation for channels containing secrets or sensitive messages. MyMemory's anonymous usage quota is limited (see https://mymemory.translated.net/doc/usagelimits.php). Provider availability is outside our control. The bot is not guaranteed to translate every message or work 24/7 with zero hosting costs. Railway's plan and resource consumption determine billing. No paid translation API is configured.

The code was syntax-checked but not live tested with Discord or MyMemory from this environment.

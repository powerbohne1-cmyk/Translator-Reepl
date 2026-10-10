# ReepL V6 — Personal Translator (EN / DE / FR / ESP / OFF)

ReepL V6 is based on the working V5.1 Discord bot. Every member can choose a **personal target language for each channel**. Translations are **on demand** and visible **only to the member requesting them** (Discord ephemeral interaction responses).

## User guide
1. In a Discord channel run `/translator` (no admin rights required).
2. Click EN, DE, FR, or ESP. OFF removes **your** preference for this channel. Other users' choices are not affected.
3. Translate using one of these methods:
   - Press **Translate latest** in the panel for the latest regular text message in that channel.
   - On desktop, right-click a specific message → **Apps → Translate with ReepL**.
   - On mobile, long-press a message → **Apps → Translate with ReepL**.
4. The translation is a private Discord response: **Only you can see this**. No public messages are sent.
5. `/translator_status` displays your own setting in the current channel.

**Important Discord limitation:** Bots cannot attach buttons to other users' existing messages or translate a message privately into a user's view without that user's interaction. There are no automatic per-user public translations in V6.

## Deploy update from V5.1
1. Unzip this archive.
2. Upload `bot.py` and `README.md` to the root of your existing GitHub repository, replacing the old versions. The existing `requirements.txt`, `railway.json`, `Procfile` and assets are provided as well if needed. Do **not** upload `.env` or your Discord token.
3. Wait for Railway to finish deploying. The startup log should include `ReepL V6 personal on-demand mode`.
4. In Discord, run `/translator` again to post an updated panel. An old panel's language buttons will also set user-specific preferences after V6 restarts, but it won't have the new **Translate latest** button.
5. Check whether **Translate with ReepL** appears under **Apps** on messages. Global context-menu commands may take time to propagate on Discord; setting `TEST_GUILD_ID` is optional for quick test-guild registration.

### Railway Variables
Required: `DISCORD_TOKEN` (set it privately in Railway → Variables).

Optional:
- `DATABASE_PATH`: defaults to `translator.sqlite3`. Set `/data/translator.sqlite3` only if you have created and mounted a persistent Railway volume at `/data`. Otherwise your preferences and cache may be lost on redeploy.
- `DAILY_CHAR_LIMIT`: defaults to `4500` translation-input characters per UTC day for the whole bot; `0` disables the local guard (not recommended).
- `MIN_REQUEST_GAP_SECONDS`: defaults to `2.5` seconds between remote requests.
- `MYMEMORY_EMAIL`: optional contact address used by MyMemory.
- `TEST_GUILD_ID`: optional Discord server ID to sync commands instantly within one test server.

Build/start: `python bot.py`. Bot permission requirements: View Channels, Send Messages, Read Message History, Use Application Commands, Message Content Intent for **Translate latest**. Message context menu depends on Discord's Apps/Integration permissions.

### Free-service limits
ReepL still uses **MyMemory** (no paid API key). Free public service limits, errors, privacy considerations, and downtime apply. Never use the public free service for sensitive/private text. The existing local cache and global daily quota help reduce usage. ReepL has no paid translation service but Railway may charge depending on the hosting plan/usage; **zero total cost is not guaranteed**.

### Upgrade / data compatibility
V6 creates a new `user_languages` table. It leaves V5.1 database tables, including the translation cache and usage, unchanged. Old shared channel language settings no longer cause public auto-translations.

### Troubleshooting
- **Buttons work but no translation**: choose a language first, then click Translate latest / use Apps on the message. Merely sending a message does not auto-translate in V6.
- **No Apps action**: ensure V6 has started, check integrations and `applications.commands` scope. It can take a little while for global commands to appear.
- **No recent message found**: check Read Message History and Message Content Intent.
- **Daily limit**: wait until the next UTC day or adjust the local limit; MyMemory still has its own limits.
- **Bot is online but no log on user click**: check Railway Deploy Logs for interaction errors and ensure the active code reports V6 in startup.

Python syntax checked locally. Discord and external-API functionality has not been live-tested in your server.


## V6.1 language detection fix
When detection is uncertain or the message is mixed-language, ReepL tries a translation rather than immediately declining. Source estimates may be inaccurate; if the original is already in your chosen language, the service may return identical text.

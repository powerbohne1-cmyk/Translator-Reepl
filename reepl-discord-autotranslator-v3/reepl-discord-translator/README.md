# ReepL V3 – Discord Auto Translator

Persistent Discord button panel with **EN / DE / FR / ESP / OFF**. Click one language to enable automatic translation in the panel's channel; select another to switch; OFF disables it. The original messages stay untouched. Translations appear as replies to messages; the bot skips text that already appears to be in the target language (best effort).

**Permissions:** Only members with **Manage Server** can click buttons that change translation settings; the whole channel sees the resulting translations. This is a shared channel setting, **not** a private per-user language setting. Each channel can have its own panel and language.

## Installation

1. Create a Discord bot at https://discord.com/developers/applications and copy its token. Enable **Message Content Intent** (privileged intent) on its Bot tab. For verified bots, Discord may require approval.
2. Invite using OAuth2 scopes `bot` and `applications.commands` with permission to View Channels, Read Message History, Send Messages, and Embed Links.
3. Python 3.10+ in VS Code / Windows:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

4. Set `DISCORD_TOKEN` in `.env`. Optionally set `TEST_GUILD_ID` to the Discord server ID for faster slash command registration.
5. Start with `python bot.py`.
6. Run `/translator` in a channel to publish the **ReepL buttons**. Click **EN**, **DE**, **FR**, **ESP**, or **OFF**. Use `/translator_status` to see the current channel setting.

Buttons continue working after bot restart as long as its service and the Discord panel message exist. If using previous V1 SQLite data, selecting a button replaces the old language settings for that channel.

## Railway

Deploy to Railway with `DISCORD_TOKEN` set as a variable and `python bot.py` as the start command. Persist settings on a Railway volume mounted at `/data`, set `DATABASE_PATH=/data/translator.sqlite3`.

## Privacy / limitations

Text to be translated is sent to an **unofficial third-party translation service** used by `deep-translator`, which may experience rate limits or outages. Inform your members and do not enable translation in confidential channels. The bot ignores other bots, webhooks, commands, and link-only messages. Mentions and links are removed from messages before translation. Language auto-detection and same-language skipping are best effort. A click changes translation for **everyone** in that channel, not just the clicker.

## ReepL name and logo

The supplied ReepL icon is included at `assets/reepl-logo.png`. In the [Discord Developer Portal](https://discord.com/developers/applications), open your application, set its **Name** to **ReepL**, upload the image as the application icon, and (if desired) change the bot username to **ReepL** on the Bot tab. The bot token is not included; existing tokens and the developer portal identity are not changed automatically.

The prior panel button identifiers remain unchanged for backward compatibility with already-posted V2 panels.

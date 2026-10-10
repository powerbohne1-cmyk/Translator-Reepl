"""ReepL V6: personal, opt-in, ephemeral Discord translations.

No public auto-translation: Discord does not support per-reader replacement of
other users' messages. The context-menu action and panel button return private
(interaction-ephemeral) replies.
"""
import asyncio
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from langdetect import DetectorFactory, detect_langs
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN', '').strip()
DB_PATH = os.getenv('DATABASE_PATH', 'translator.sqlite3')
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID', '').strip()
DAILY_CHAR_LIMIT = max(0, int(os.getenv('DAILY_CHAR_LIMIT', '4500')))
MIN_REQUEST_GAP = max(0.5, float(os.getenv('MIN_REQUEST_GAP_SECONDS', '2.5')))
TRANSLATION_EMAIL = os.getenv('MYMEMORY_EMAIL', '').strip()
MAX_TRANSLATION_BYTES = 450
LANGUAGES = {'en': 'EN', 'de': 'DE', 'fr': 'FR', 'es': 'ESP'}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('ReepL')
request_lock = asyncio.Lock()
last_request_at = 0.0


class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        # Keep V5.1 tables and cache intact when upgrading.
        self.connection.execute('CREATE TABLE IF NOT EXISTS translation_cache (source TEXT NOT NULL, target TEXT NOT NULL, input TEXT NOT NULL, output TEXT NOT NULL, PRIMARY KEY (source,target,input))')
        self.connection.execute('CREATE TABLE IF NOT EXISTS translation_usage (day TEXT PRIMARY KEY, chars INTEGER NOT NULL DEFAULT 0)')
        self.connection.execute('CREATE TABLE IF NOT EXISTS user_languages (guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, user_id INTEGER NOT NULL, target TEXT NOT NULL, PRIMARY KEY(guild_id,channel_id,user_id))')
        self.connection.commit()

    def choose_user(self, guild_id, channel_id, user_id, target):
        if target:
            self.connection.execute('INSERT INTO user_languages(guild_id,channel_id,user_id,target) VALUES(?,?,?,?) ON CONFLICT(guild_id,channel_id,user_id) DO UPDATE SET target=excluded.target', (guild_id,channel_id,user_id,target))
        else:
            self.connection.execute('DELETE FROM user_languages WHERE guild_id=? AND channel_id=? AND user_id=?', (guild_id,channel_id,user_id))
        self.connection.commit()

    def get_user(self, guild_id, channel_id, user_id):
        row = self.connection.execute('SELECT target FROM user_languages WHERE guild_id=? AND channel_id=? AND user_id=?', (guild_id,channel_id,user_id)).fetchone()
        return row[0] if row else None

    def cached(self, source, target, value):
        row = self.connection.execute('SELECT output FROM translation_cache WHERE source=? AND target=? AND input=?', (source,target,value)).fetchone()
        return row[0] if row else None

    def save_cache(self, source, target, value, result):
        self.connection.execute('INSERT OR REPLACE INTO translation_cache(source,target,input,output) VALUES(?,?,?,?)', (source,target,value,result))
        self.connection.commit()

    def quota_available(self, amount):
        day = datetime.now(timezone.utc).date().isoformat()
        row = self.connection.execute('SELECT chars FROM translation_usage WHERE day=?',(day,)).fetchone()
        return DAILY_CHAR_LIMIT == 0 or (row[0] if row else 0) + amount <= DAILY_CHAR_LIMIT

    def charge(self, amount):
        day = datetime.now(timezone.utc).date().isoformat()
        self.connection.execute('INSERT INTO translation_usage(day,chars) VALUES(?,?) ON CONFLICT(day) DO UPDATE SET chars=chars+excluded.chars',(day,amount))
        self.connection.commit()


store = Storage(DB_PATH)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)
LINK_RE = re.compile(r'https?://\S+', re.I)
CUSTOM_EMOJI_RE = re.compile(r'<a?:\w+:\d+>')
MENTION_RE = re.compile(r'<(?:@!?|@&|#)\d+>')


def cleaned(text):
    return MENTION_RE.sub('', CUSTOM_EMOJI_RE.sub('', LINK_RE.sub('', text))).strip()


def equivalent(a, b):
    return re.sub(r'[^\w]+', '', a.casefold()) == re.sub(r'[^\w]+', '', b.casefold())


def detect_source(text, target):
    """Choose a plausible source; never silently block an explicit translation request.

    MyMemory needs an explicit language pair. Language detection is unreliable
    for short or mixed-language chat messages, so we use a documented fallback.
    """
    try:
        options = detect_langs(text)
    except LangDetectException:
        options = []
    candidates = [(item.lang.split('-')[0], item.prob) for item in options]
    if candidates:
        best, confidence = candidates[0]
        if best in LANGUAGES and best != target and confidence >= 0.55:
            return best, False
        # Prefer a plausible non-target alternative for mixed messages.
        for language, probability in candidates[1:]:
            if language in LANGUAGES and language != target and probability >= 0.15:
                return language, True
    # Unknown or detected as target: attempt the requested translation anyway.
    # Most community messages are English; for English output, German is our fallback.
    return ('de' if target == 'en' else 'en'), True


async def translate_free(text, source, target):
    global last_request_at
    hit = store.cached(source, target, text)
    if hit:
        return hit, None
    async with request_lock:
        hit = store.cached(source, target, text)
        if hit:
            return hit, None
        if not store.quota_available(len(text)):
            return None, 'Free daily translation budget reached. Try again tomorrow (UTC).'
        loop = asyncio.get_running_loop()
        await asyncio.sleep(max(0, MIN_REQUEST_GAP - (loop.time() - last_request_at)))
        last_request_at = loop.time()
        store.charge(len(text))
        params = {'q': text, 'langpair': f'{source}|{target}'}
        if TRANSLATION_EMAIL:
            params['de'] = TRANSLATION_EMAIL
        try:
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://api.mymemory.translated.net/get', params=params) as response:
                    if response.status == 429:
                        return None, 'The free translation service is rate-limited. Try again later.'
                    if response.status != 200:
                        log.warning('MyMemory HTTP %s', response.status)
                        return None, 'The translation service is currently unavailable.'
                    data = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            log.warning('MyMemory request failed: %s', exc)
            return None, 'Could not reach the free translation service. Try again later.'
        status = data.get('responseStatus', 200)
        translated = unescape(str(data.get('responseData', {}).get('translatedText', ''))).strip()
        if str(status) != '200' or not translated or 'MYMEMORY WARNING' in translated.upper() or 'QUOTA' in translated.upper():
            log.warning('MyMemory unusable response: %s', status)
            return None, 'The free translation service could not translate this message.'
        store.save_cache(source, target, text, translated)
        return translated, None


async def private_translation(interaction: discord.Interaction, message: discord.Message):
    """Use only after deferring an ephemeral interaction."""
    target = store.get_user(interaction.guild_id, interaction.channel_id, interaction.user.id)
    if target is None:
        await interaction.followup.send('Choose your language first with `/translator` (EN, DE, FR or ESP).', ephemeral=True)
        return
    text = cleaned(message.content or '')
    if not text or not any(ch.isalpha() for ch in text):
        await interaction.followup.send('This message has no translatable text.', ephemeral=True)
        return
    if len(text.encode('utf-8')) > MAX_TRANSLATION_BYTES:
        await interaction.followup.send(f'This message is too long for the free service (maximum {MAX_TRANSLATION_BYTES} UTF-8 bytes).', ephemeral=True)
        return
    source, guessed_source = detect_source(text, target)
    result, error = await translate_free(text, source, target)
    if error:
        await interaction.followup.send('⚠️ ' + error, ephemeral=True)
        return
    if not result or equivalent(text, result):
        await interaction.followup.send('No different translation was returned. The message may already be in your selected language; mixed or short messages can be difficult to identify.', ephemeral=True)
        return
    safe_result = discord.utils.escape_markdown(discord.utils.escape_mentions(result))
    note = ' · source estimated' if guessed_source else ''
    await interaction.followup.send(f'🌐 **{LANGUAGES[target]}** · {discord.utils.escape_markdown(message.author.display_name)}{note}\n{safe_result[:1700]}', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


class TranslatorPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def set_language(self, interaction, code):
        if not interaction.guild_id or not interaction.channel_id:
            await interaction.response.send_message('Only available in a server channel.', ephemeral=True)
            return
        store.choose_user(interaction.guild_id, interaction.channel_id, interaction.user.id, code)
        if code:
            msg = f'✅ Your personal language in **this channel** is now **{LANGUAGES[code]}**. Use **Translate latest** below, or right-click/long-press a message → **Apps → Translate with ReepL**. Only you see translations.'
        else:
            msg = '⏹️ Your personal translation preference is OFF in this channel.'
        await interaction.response.send_message(msg, ephemeral=True)

    # Keep V5.1 custom IDs so older posted panels still activate personal settings.
    @discord.ui.button(label='EN', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:en', row=0)
    async def en(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'en')

    @discord.ui.button(label='DE', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:de', row=0)
    async def de(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'de')

    @discord.ui.button(label='FR', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:fr', row=0)
    async def fr(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'fr')

    @discord.ui.button(label='ESP', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:es', row=0)
    async def es(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'es')

    @discord.ui.button(label='OFF', style=discord.ButtonStyle.danger, custom_id='vanguard:translate:off', row=0)
    async def off(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, None)

    @discord.ui.button(label='Translate latest', emoji='🌐', style=discord.ButtonStyle.success, custom_id='reepl:v6:latest', row=1)
    async def latest(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if not interaction.guild_id or not interaction.channel_id:
            await interaction.followup.send('Use this button inside a server text channel.', ephemeral=True)
            return
        if not store.get_user(interaction.guild_id, interaction.channel_id, interaction.user.id):
            await interaction.followup.send('Choose EN, DE, FR or ESP first.', ephemeral=True)
            return
        channel = interaction.channel
        if not hasattr(channel, 'history'):
            await interaction.followup.send('This channel does not support message history.', ephemeral=True)
            return
        try:
            async for msg in channel.history(limit=30):
                if not msg.author.bot and msg.content and not msg.content.startswith(('/', '!')):
                    await private_translation(interaction, msg)
                    return
        except discord.Forbidden:
            await interaction.followup.send('ReepL needs **Read Message History** in this channel.', ephemeral=True)
            return
        await interaction.followup.send('No recent text message found.', ephemeral=True)


@bot.event
async def setup_hook():
    bot.add_view(TranslatorPanel())
    if TEST_GUILD_ID:
        guild = discord.Object(id=int(TEST_GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()


@bot.event
async def on_ready():
    log.info('Connected as %s (%s) - ReepL V6 personal on-demand mode', bot.user, bot.user.id)


@bot.tree.command(name='translator', description='Open personal translation controls for this channel')
@app_commands.guild_only()
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(title='🌐 ReepL · PERSONAL TRANSLATOR', description='Choose **your own language** for this channel. Everyone can choose independently: **EN / DE / FR / ESP / OFF**.\n\nTo translate privately, click **Translate latest** or right-click / long-press any message and select **Apps → Translate with ReepL**.\n\nTranslations are shown **only to you**. No automatic public replies.', color=0x536DCC)
    await interaction.response.send_message(embed=embed, view=TranslatorPanel())


@bot.tree.command(name='translator_status', description='Show your personal translation language in this channel')
@app_commands.guild_only()
async def translator_status(interaction: discord.Interaction):
    target = store.get_user(interaction.guild_id, interaction.channel_id, interaction.user.id)
    await interaction.response.send_message(f'Your personal language in this channel: **{LANGUAGES[target] if target else "OFF"}**', ephemeral=True)


@bot.tree.context_menu(name='Translate with ReepL')
@app_commands.guild_only()
async def translate_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        await private_translation(interaction, message)
    except Exception as exc:
        log.exception('Private translation failed: %s', exc)
        await interaction.followup.send('Could not translate this message. Please try again later.', ephemeral=True)


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('Missing DISCORD_TOKEN in Railway Variables or .env')
    bot.run(TOKEN, log_handler=None)

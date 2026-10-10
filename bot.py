import asyncio
import logging
import os
import re
import sqlite3
from pathlib import Path

import discord
from deep_translator import GoogleTranslator
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN', '').strip()
DB_PATH = os.getenv('DATABASE_PATH', 'translator.sqlite3')
TEST_GUILD_ID = os.getenv('TEST_GUILD_ID', '').strip()
MAX_PARALLEL = int(os.getenv('MAX_PARALLEL_TRANSLATIONS', '3'))
LANGUAGES = {'en': 'EN', 'de': 'DE', 'fr': 'FR', 'es': 'ESP'}

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('ReepL')
semaphore = asyncio.Semaphore(MAX_PARALLEL)

class Storage:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute('CREATE TABLE IF NOT EXISTS channels (guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, target TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, PRIMARY KEY (guild_id, channel_id, target))')
        self.connection.commit()

    def choose(self, guild_id, channel_id, target):
        self.connection.execute('DELETE FROM channels WHERE guild_id=? AND channel_id=?', (guild_id, channel_id))
        if target:
            self.connection.execute('INSERT INTO channels(guild_id,channel_id,target,enabled) VALUES(?,?,?,1)', (guild_id, channel_id, target))
        self.connection.commit()

    def get(self, guild_id, channel_id):
        row = self.connection.execute('SELECT target FROM channels WHERE guild_id=? AND channel_id=? AND enabled=1 AND target IN (\'en\',\'de\',\'fr\',\'es\') LIMIT 1', (guild_id, channel_id)).fetchone()
        return row[0] if row else None

store = Storage(DB_PATH)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

class TranslatorPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def set_language(self, interaction: discord.Interaction, code: str | None):
        if not interaction.guild or not interaction.channel_id:
            await interaction.response.send_message('Only available inside a server channel.', ephemeral=True)
            return
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message('You need **Manage Server** permission to change channel auto-translation.', ephemeral=True)
            return
        # Settings apply to the channel containing the panel, not to the whole server.
        store.choose(interaction.guild_id, interaction.channel_id, code)
        message = f'✅ Auto-translation in this channel → **{LANGUAGES[code]}**.' if code else '⏹️ Auto-translation disabled in this channel.'
        await interaction.response.send_message(message, ephemeral=True)

    @discord.ui.button(label='EN', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:en')
    async def english(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'en')

    @discord.ui.button(label='DE', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:de')
    async def german(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'de')

    @discord.ui.button(label='FR', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:fr')
    async def french(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'fr')

    @discord.ui.button(label='ESP', style=discord.ButtonStyle.primary, custom_id='vanguard:translate:es')
    async def spanish(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, 'es')

    @discord.ui.button(label='OFF', style=discord.ButtonStyle.danger, custom_id='vanguard:translate:off')
    async def off(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.set_language(interaction, None)

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
    log.info('Connected as %s (%s)', bot.user, bot.user.id)

@bot.tree.command(name='translator', description='Post the ReepL translator control panel (EN/DE/FR/ESP/OFF)')
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message('You need **Manage Server** permission.', ephemeral=True)
        return
    embed = discord.Embed(title='🌐 ReepL · AUTO TRANSLATOR', description='Choose the output language for **this channel**.\n\n🇬🇧 **EN** · 🇩🇪 **DE** · 🇫🇷 **FR** · 🇪🇸 **ESP**\n\n**OFF** stops automatic translations. Only server managers can change the setting. Original messages remain unchanged.', color=0x536DCC)
    await interaction.response.send_message(embed=embed, view=TranslatorPanel())

@bot.tree.command(name='translator_status', description='Show the active output language for this channel')
@app_commands.guild_only()
async def translator_status(interaction: discord.Interaction):
    target = store.get(interaction.guild_id, interaction.channel_id)
    await interaction.response.send_message(f'Channel translation: **{LANGUAGES[target] if target else "OFF"}**', ephemeral=True)

LINK_RE = re.compile(r'https?://\S+', re.IGNORECASE)
CUSTOM_EMOJI_RE = re.compile(r'<a?:\w+:\d+>')
MENTION_RE = re.compile(r'<(?:@!?|@&|#)\d+>')

def cleaned(text):
    return MENTION_RE.sub('', CUSTOM_EMOJI_RE.sub('', LINK_RE.sub('', text))).strip()

def equivalent(a, b):
    return re.sub(r'[^\w]+', '', a.casefold()) == re.sub(r'[^\w]+', '', b.casefold())

def translate_sync(text, language):
    return GoogleTranslator(source='auto', target=language).translate(text)

async def translate_message(message: discord.Message, target: str):
    original = cleaned(message.content)
    if len(original) < 3 or not any(ch.isalpha() for ch in original):
        return
    try:
        async with semaphore:
            result = await asyncio.wait_for(asyncio.to_thread(translate_sync, original[:4500], target), timeout=25)
        if not result or equivalent(original, result):
            return
        # Do not post stale translations if the moderator has changed the setting.
        if store.get(message.guild.id, message.channel.id) != target:
            return
        result = discord.utils.escape_markdown(discord.utils.escape_mentions(result))
        header = f'🌐 **{LANGUAGES[target]}** · {discord.utils.escape_markdown(message.author.display_name)}\n'
        available = 1900 - len(header)
        await message.reply(header + result[:available] + ('…' if len(result) > available else ''), mention_author=False, allowed_mentions=discord.AllowedMentions.none(), fail_if_not_exists=False)
    except Exception as exc:
        log.warning('Translation failed channel=%s language=%s: %s', message.channel.id, target, exc)

@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot or message.webhook_id or not message.content:
        return
    if message.content.startswith(('/', '!', '.')):
        return
    target = store.get(message.guild.id, message.channel.id)
    if target:
        asyncio.create_task(translate_message(message, target))

if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('Missing DISCORD_TOKEN. Copy .env.example to .env and insert your bot token.')
    bot.run(TOKEN, log_handler=None)

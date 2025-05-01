import discord
from discord.ext import commands
from discord.ui import View, Button
import random
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ROLE_ID = int(os.getenv("ROLE_ID"))

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

game_data = {
    'organizer': None,
    'players': [],
    'votes': {},
    'voted_users': set(),
    'words': {},
    'theme': '',
    'citizen_word': '',
    'wolf_word': '',
    'vote_message': None,
    'vote_start_time': None,
    'message_embed': None
}

def load_themes():
    themes = {}
    with open('お題.txt', 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) == 2:
                theme, words = parts
                themes[theme] = words.split(',')
    return themes

theme_pool = load_themes()

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.tree.sync()

class JoinStartView(View):
    def __init__(self, organizer):
        super().__init__(timeout=None)
        self.organizer = organizer

    @discord.ui.button(label="👍 参加", style=discord.ButtonStyle.success, custom_id="join_game")
    async def join_button(self, interaction: discord.Interaction, button: Button):
        user = interaction.user
        if user in game_data['players']:
            await interaction.response.send_message("すでに参加しています！", ephemeral=True)
        else:
            game_data['players'].append(user)
            await update_embed_players()
            await interaction.response.send_message("参加しました！", ephemeral=True)

    @discord.ui.button(label="✅ 開始", style=discord.ButtonStyle.primary, custom_id="start_game")
    async def start_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user != self.organizer:
            await interaction.response.send_message("開始できるのは主催者だけです。", ephemeral=True)
            return

        if len(game_data['players']) < 3:
            await interaction.response.send_message("最低3人の参加者が必要です。", ephemeral=True)
            return

        await interaction.response.send_message("ゲームを開始します！", ephemeral=True)
        await start_game(interaction.channel)

@bot.tree.command(name="ワードウルフ", description="ワードウルフゲームを開始します")
async def word_wolf(interaction: discord.Interaction):
    if game_data['organizer']:
        await interaction.response.send_message('すでにゲームが進行中です', ephemeral=True)
        return

    game_data.update({
        'organizer': interaction.user,
        'players': [],
        'votes': {},
        'voted_users': set(),
        'words': {},
        'theme': '',
        'citizen_word': '',
        'wolf_word': '',
        'vote_message': None,
        'vote_start_time': None,
        'message_embed': None
    })

    embed = discord.Embed(
        title='ワードウルフ参加者募集！',
        description='お題：ランダム（あとで変更可能）\n\n**ボタンを押して参加してください。**\n\n**全員の参加が終わったら、主催者が「開始」を押してゲームを始めてください。**\n（最低3人以上必要です）',
        color=0x00ff00
    )
    embed.add_field(name='参加プレイヤー', value='なし')
    message = await interaction.channel.send(embed=embed, view=JoinStartView(interaction.user))
    game_data['message_embed'] = message
    await interaction.response.send_message("ゲームの準備を開始しました！", ephemeral=True)

async def update_embed_players():
    embed = game_data['message_embed'].embeds[0]
    player_names = '\n'.join(f'・{p.name}' for p in game_data['players'])
    theme_text = game_data['theme'] if game_data['theme'] else 'ランダム（あとで変更可能）'
    embed.set_field_at(0, name='参加プレイヤー', value=player_names or 'なし')
    embed.description = f'お題：{theme_text}\n\n**ボタンを押して参加してください。**\n\n**全員の参加が終わったら、主催者が「開始」を押してゲームを始めてください。**\n（最低3人以上必要です）'
    await game_data['message_embed'].edit(embed=embed)

async def start_game(channel):
    theme = game_data['theme']
    if not theme:
        theme = random.choice(list(theme_pool.keys()))
        game_data['theme'] = theme

    words = theme_pool[theme]
    selected = random.sample(words, 2)
    citizen_word, wolf_word = selected

    players = game_data['players'][:]
    wolf = random.choice(players)
    for p in players:
        word = wolf_word if p == wolf else citizen_word
        game_data['words'][p.id] = word
        try:
            await p.send(f'お題: **{theme}**\nあなたのワードは「{word}」です。')
        except:
            pass

    game_data['citizen_word'] = citizen_word
    game_data['wolf_word'] = wolf_word

    player_list = '\n'.join(p.name for p in players)
    embed = discord.Embed(title='ゲーム開始！',
                          description=f'カテゴリー：{theme}\n\n参加プレイヤー：\n{player_list}\n\n議論を始めてください！',
                          color=0xff0000)
    await channel.send(embed=embed)

    # 特定ロールへの役職通知
    role = discord.utils.get(channel.guild.roles, id=ROLE_ID)
    if role:
        embed_roles = discord.Embed(title="ゲームの役職情報", color=0x00ff00)
        for player in game_data['players']:
            role_text = "市民" if game_data['words'][player.id] == game_data['citizen_word'] else "ウルフ"
            embed_roles.add_field(name=player.name, value=role_text, inline=False)
        for member in role.members:
            try:
                await member.send(embed=embed_roles)
            except:
                pass

    await game_data['message_embed'].edit(view=None)

bot.run(TOKEN)

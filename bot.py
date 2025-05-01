import discord
from discord.ext import commands
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

bot = commands.Bot(command_prefix='!', intents=intents)

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
        title='🐺 ワードウルフ参加者募集！',
        description='**お題：** ランダム（あとで変更可能）\n\n👍 を押して参加！\n✅ を押すとゲーム開始！（主催者のみ）\n\n**※最低3人必要です**',
        color=discord.Color.green()
    )
    embed.add_field(name='👥 参加プレイヤー', value='なし', inline=False)
    message = await interaction.channel.send(embed=embed)
    game_data['message_embed'] = message
    await message.add_reaction('👍')
    await message.add_reaction('✅')
    await interaction.response.send_message('参加を開始しました！', ephemeral=True)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if reaction.message.id != getattr(game_data['message_embed'], 'id', None):
        return

    if reaction.emoji == '👍':
        if user not in game_data['players']:
            game_data['players'].append(user)
            await update_embed_players()

    elif reaction.emoji == '✅' and user == game_data['organizer']:
        if len(game_data['players']) < 3:
            await reaction.message.channel.send(f'{game_data["organizer"].mention} ゲーム開始には最低3人の参加者が必要です。')
            return
        await start_game(reaction.message.channel)

async def update_embed_players():
    embed = game_data['message_embed'].embeds[0]
    player_names = '\n'.join(f'・{p.name}' for p in game_data['players']) or 'なし'
    theme_text = game_data['theme'] if game_data['theme'] else 'ランダム（あとで変更可能）'
    embed.set_field_at(0, name='👥 参加プレイヤー', value=player_names, inline=False)
    embed.description = f'**お題：** {theme_text}\n\n👍 を押して参加！\n✅ を押すとゲーム開始！（主催者のみ）\n\n**※最低3人必要です**'
    await game_data['message_embed'].edit(embed=embed)

async def start_game(channel):
    theme = game_data['theme'] or random.choice(list(theme_pool.keys()))
    game_data['theme'] = theme

    words = random.sample(theme_pool[theme], 2)
    citizen_word, wolf_word = words
    game_data['citizen_word'] = citizen_word
    game_data['wolf_word'] = wolf_word

    players = game_data['players'][:]
    wolf = random.choice(players)
    for p in players:
        word = wolf_word if p == wolf else citizen_word
        game_data['words'][p.id] = word
        try:
            await p.send(f'📝 お題: **{theme}**\nあなたのワードは「{word}」です。')
        except:
            pass

    player_list = '\n'.join(p.name for p in players)
    embed = discord.Embed(
        title='🎮 ゲーム開始！',
        description=f'**カテゴリー：** {theme}\n\n👥 **参加プレイヤー：**\n{player_list}\n\n🗣️ 議論を始めましょう！',
        color=discord.Color.red()
    )
    await channel.send(embed=embed)
    await game_data['message_embed'].clear_reactions()

@bot.tree.command(name="お題一覧", description="ゲームのお題一覧を表示します")
async def お題一覧(interaction: discord.Interaction):
    theme_names = '\n'.join(theme_pool.keys())
    embed = discord.Embed(title='📚 お題一覧', description=theme_names, color=discord.Color.teal())
    await interaction.response.send_message(embed=embed)

@bot.command(name="お題変更")
async def お題変更(ctx, *, theme_name: str):
    if not game_data['organizer']:
        await ctx.send("まだゲームが開始されていません")
        return

    if theme_name not in theme_pool:
        await ctx.send(f'お題「{theme_name}」は存在しません。')
        return

    game_data['theme'] = theme_name
    await update_embed_players()
    await ctx.send(f'✅ お題が「{theme_name}」に変更されました！')

@bot.tree.command(name="終了", description="ワードウルフゲームを終了します")
async def 終了(interaction: discord.Interaction):
    if not game_data['organizer']:
        await interaction.response.send_message("ゲームが開始されていません", ephemeral=True)
        return

    if interaction.user != game_data['organizer']:
        await interaction.response.send_message("このコマンドは主催者のみ実行できます", ephemeral=True)
        return

    players = game_data['players']
    wolf = next(p for p in players if game_data['words'][p.id] == game_data['wolf_word'])

    result_text = f"🛑 **ゲーム終了！**\n\n🐺 ウルフのワード: 「{game_data['wolf_word']}」\n🧑 市民のワード: 「{game_data['citizen_word']}」\n\n👤 ウルフは {wolf.name} さんでした！"

    embed = discord.Embed(title="📢 結果発表", description=result_text, color=discord.Color.red())
    await interaction.channel.send(embed=embed)
    reset_game()
    await interaction.response.send_message("ゲームを終了しました。", ephemeral=True)

def reset_game():
    game_data.clear()
    game_data.update({
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
    })

bot.run(TOKEN)

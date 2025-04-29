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

bot = commands.Bot(command_prefix="!", intents=intents)

# --- ゲームデータの保持 ---
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

from collections import defaultdict

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

# --- スラッシュコマンド ---
@bot.tree.command(name="ワードウルフ", description="ワードウルフゲームを開始します")
async def slash_word_wolf(interaction: discord.Interaction):
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
    embed = discord.Embed(title='ワードウルフ参加者募集！',
                          description='お題：ランダム（あとで変更可能）\n\nリアクションで参加してください。\n\n**全員の参加が終わったら、主催者が ✅ を押してゲームを開始します。**\n（最低3人以上必要です）',
                          color=0x00ff00)
    embed.add_field(name='参加プレイヤー', value='なし')
    message = await interaction.channel.send(embed=embed)
    game_data['message_embed'] = message
    await message.add_reaction('👍')
    await message.add_reaction('✅')

@bot.tree.command(name="結果", description="投票結果を表示します")
async def slash_結果(interaction: discord.Interaction):
    if interaction.user != game_data['organizer']:
        await interaction.response.send_message('主催者だけが実行できます', ephemeral=True)
        return
    if not game_data['vote_start_time']:
        await interaction.response.send_message('まだ投票が開始されていません', ephemeral=True)
        return
    if (discord.utils.utcnow() - game_data['vote_start_time']).total_seconds() < 60:
        await interaction.response.send_message('投票開始から1分経っていません', ephemeral=True)
        return
    await show_result(interaction.channel)

@bot.tree.command(name="終了", description="ゲームを終了します")
async def slash_終了(interaction: discord.Interaction):
    await interaction.response.send_message('ゲームが終了しました！', ephemeral=True)
    reset_game()

@bot.tree.command(name="お題一覧", description="ゲームのお題一覧を表示します")
async def slash_お題一覧(interaction: discord.Interaction):
    theme_names = '\n'.join(theme_pool.keys())
    embed = discord.Embed(title="お題一覧", description=theme_names, color=0x00ffcc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- プレフィックス付きコマンド ---
@bot.command(name="ワードウルフ")
async def word_wolf(ctx):
    if game_data['organizer']:
        await ctx.send('すでにゲームが進行中です')
        return
    game_data.update({
        'organizer': ctx.author,
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
    embed = discord.Embed(title='ワードウルフ参加者募集！',
                          description='お題：ランダム（あとで変更可能）\n\nリアクションで参加してください。\n\n**全員の参加が終わったら、主催者が ✅ を押してゲームを開始します。**\n（最低3人以上必要です）',
                          color=0x00ff00)
    embed.add_field(name='参加プレイヤー', value='なし')
    message = await ctx.send(embed=embed)
    game_data['message_embed'] = message
    await message.add_reaction('👍')
    await message.add_reaction('✅')

@bot.command(name="結果")
async def 結果(ctx):
    if ctx.author != game_data['organizer']:
        await ctx.send('主催者だけが実行できます')
        return
    if not game_data['vote_start_time']:
        await ctx.send('まだ投票が開始されていません')
        return
    if (discord.utils.utcnow() - game_data['vote_start_time']).total_seconds() < 60:
        await ctx.send('投票開始から1分経っていません')
        return
    await show_result(ctx.channel)

@bot.command(name="終了")
async def 終了(ctx):
    await ctx.send('ゲームが終了しました！')
    reset_game()

@bot.command(name="お題一覧")
async def お題一覧(ctx):
    theme_names = '\n'.join(theme_pool.keys())
    embed = discord.Embed(title="お題一覧", description=theme_names, color=0x00ffcc)
    await ctx.send(embed=embed)

# --- ゲームの開始・結果表示 ---
async def show_result(channel):
    votes = game_data['votes']
    players = game_data['players']

    max_votes = max(votes.values())
    candidates = [i for i, v in votes.items() if v == max_votes]
    chosen_index = candidates[0]

    chosen = players[chosen_index]
    wolf = next(p for p in players if game_data['words'][p.id] == game_data['wolf_word'])

    result_text = f'もっとも投票されたのは {chosen.name} さんでした。得票数：{votes[chosen_index]}票\n\n'
    result_text += f'ウルフのワードは「{game_data["wolf_word"]}」\n市民のワードは「{game_data["citizen_word"]}」\n\n'
    result_text += f'ウルフは {wolf.name} さんでした！\n\n'

    if chosen == wolf:
        result_text += '市民の勝ち！ 🎉'
    else:
        result_text += 'ウルフの勝ち！ 🐺'

    embed = discord.Embed(title="投票結果", description=result_text, color=0xff0000)
    await channel.send(embed=embed)
    reset_game()

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

# イベントハンドラ（ボットが起動したときなど）
@bot.event
async def on_ready():
    await bot.tree.sync()  # スラッシュコマンドの同期
    print(f"{bot.user} has connected to Discord!")

bot.run(TOKEN)

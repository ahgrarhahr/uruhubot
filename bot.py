import discord
from discord.ext import commands, tasks
import random
import asyncio
import os
from dotenv import load_dotenv  # ← 追加

# 環境変数を読み込む
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # ← 追加

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

# --- データ保持用 ---
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

# お題読み込み
from collections import defaultdict

def load_themes():
    themes = defaultdict(list)
    with open('お題.txt', 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(',')
            if len(parts) >= 3:
                theme, *words = parts
                themes[theme].extend(words)
    return themes

theme_pool = load_themes()

# --- コマンド ---

@bot.command()
async def ワードウルフ(ctx):
    if game_data['organizer']:
        await ctx.send('すでにゲームが進行中です')
        return
    
    game_data['organizer'] = ctx.author
    game_data['players'] = []
    game_data['votes'] = {}
    game_data['voted_users'] = set()
    game_data['words'] = {}
    game_data['vote_message'] = None
    game_data['vote_start_time'] = None

    game_data['theme'] = 'ランダム'

    embed = discord.Embed(title='ワードウルフ参加者募集！',
                          description='お題：ランダム\n\nリアクションで参加してください。\n\n**全員の参加が終わったら、主催者が ✅ を押してゲームを開始します。**\n（最低3人以上必要です）',
                          color=0x00ff00)
    embed.add_field(name='参加プレイヤー', value='なし')
    message = await ctx.send(embed=embed)
    game_data['message_embed'] = message
    await message.add_reaction('✅')

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if reaction.message.id != getattr(game_data['message_embed'], 'id', None):
        return

    if reaction.emoji == '✅':
        if user != game_data['organizer']:
            return
        if len(game_data['players']) < 3:
            await reaction.message.channel.send('開始するには最低3人参加する必要があります')
            return
        await start_game(reaction.message.channel)
        return

    if user not in game_data['players']:
        game_data['players'].append(user)
        await update_embed_players()

async def update_embed_players():
    embed = game_data['message_embed'].embeds[0]
    player_names = '\n'.join(f'・{p.name}' for p in game_data['players'])
    embed.set_field_at(0, name='参加プレイヤー', value=player_names or 'なし')
    await game_data['message_embed'].edit(embed=embed)

async def start_game(channel):
    # お題決定
    if game_data['theme'] == 'ランダム':
        theme = random.choice(list(theme_pool.keys()))
    else:
        theme = game_data['theme']

    words = theme_pool[theme]
    selected = random.sample(words, 2)
    citizen_word, wolf_word = selected

    players = game_data['players'][:]
    wolf = random.choice(players)
    for p in players:
        word = wolf_word if p == wolf else citizen_word
        game_data['words'][p.id] = word
        try:
            await p.send(f'あなたのワードは「{word}」です。')
        except:
            pass

    game_data['theme'] = theme
    game_data['citizen_word'] = citizen_word
    game_data['wolf_word'] = wolf_word

    # ゲーム開始メッセージ
    player_list = '\n'.join(p.name for p in players)
    embed = discord.Embed(title='ゲーム開始！',
                          description=f'カテゴリー：{theme}\n\n参加プレイヤー：\n{player_list}\n\n議論を始めてください！',
                          color=0xff0000)
    await channel.send(embed=embed)

@bot.command()
async def 投票(ctx):
    if ctx.author not in game_data['players']:
        await ctx.send('ゲームに参加していません')
        return

    desc = '\n'.join([f'{i+1}. {p.name}' for i, p in enumerate(game_data['players'])])
    embed = discord.Embed(title='投票を始めます', description='リアクションで投票してください\n\n' + desc, color=0x00ffcc)
    vote_msg = await ctx.send(embed=embed)
    game_data['vote_message'] = vote_msg
    game_data['votes'] = {i: 0 for i in range(len(game_data['players']))}
    game_data['voted_users'] = set()
    game_data['vote_start_time'] = discord.utils.utcnow()

    for i in range(len(game_data['players'])):
        await vote_msg.add_reaction(f'{i+1}⃣')  # 1️⃣, 2️⃣, etc

@bot.event
async def on_reaction_add_vote(reaction, user):
    if user.bot or reaction.message.id != getattr(game_data['vote_message'], 'id', None):
        return
    if user.id in game_data['voted_users']:
        return

    for i in range(len(game_data['players'])):
        if reaction.emoji == f'{i+1}⃣':
            game_data['votes'][i] += 1
            game_data['voted_users'].add(user.id)
            break

    if len(game_data['voted_users']) == len(game_data['players']):
        await show_result(reaction.message.channel)

@bot.command()
async def 終了(ctx):
    await show_result(ctx.channel)
    reset_game()

@bot.command(name='結果', aliases=['!結果'])
async def manual_result(ctx):
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
    reset_game()

async def show_result(channel):
    votes = game_data['votes']
    players = game_data['players']

    # 投票数最大を取得
    max_votes = max(votes.values())
    candidates = [i for i, v in votes.items() if v == max_votes]
    chosen_index = candidates[0]

    chosen = players[chosen_index]
    wolf = next(p for p in players if game_data['words'][p.id] == game_data['wolf_word'])

    result_text = f'もっとも投票されたのは {chosen.name} さんでした。\n\n'
    result_text += f'ウルフのワードは「{game_data["wolf_word"]}」\n市民のワードは「{game_data["citizen_word"]}」\n\n'
    result_text += f'ウルフは {wolf.name} さんでした！\n\n'

    if chosen == wolf:
        result_text += '市民の勝ち！ 🎉'
    else:
        result_text += 'ウルフの勝ち！ 🐺'

    await channel.send(result_text)

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

@bot.event
async def on_raw_reaction_add(payload):
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    user = payload.member
    reaction = discord.utils.get(message.reactions, emoji=payload.emoji.name)
    if game_data['vote_message'] and message.id == game_data['vote_message'].id:
        await on_reaction_add_vote(reaction, user)
    else:
        await on_reaction_add(reaction, user)

bot.run(TOKEN)

import discord
from discord.ext import commands
import random
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
ROLE_ID = int(os.getenv("ROLE_ID"))  # 特定のロールID（環境変数で指定）

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.members = True

# コマンドプレフィックスを!と/両方使えるように設定
bot = commands.Bot(command_prefix=['!', '/'], intents=intents)

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

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')

@bot.command(name="ワードウルフ", description="ワードウルフゲームを開始します")
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
    player_names = '\n'.join(f'・{p.name}' for p in game_data['players'])
    theme_text = game_data['theme'] if game_data['theme'] else 'ランダム（あとで変更可能）'
    embed.set_field_at(0, name='参加プレイヤー', value=player_names or 'なし')
    embed.description = f'お題：{theme_text}\n\nリアクションで参加してください。\n\n**全員の参加が終わったら、主催者が ✅ を押してゲームを開始します。**\n（最低3人以上必要です）'
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
    await game_data['message_embed'].clear_reactions()

@bot.command(name="結果", description="投票結果を表示します")
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

@bot.command(name="終了", description="ゲームを終了します")
async def 終了(ctx):
    if game_data['organizer'] != ctx.author:
        await ctx.send('ゲームを終了できるのは主催者だけです。')
        return

    result_text = f'ゲームは終了しました！\n\nウルフのワードは「{game_data["wolf_word"]}」\n市民のワードは「{game_data["citizen_word"]}」\n'
    result_text += f'ウルフは {next(p.name for p in game_data["players"] if game_data["words"][p.id] == game_data["wolf_word"]).name} さんでした！'

    embed = discord.Embed(title="ゲーム終了", description=result_text, color=0xff0000)
    await ctx.send(embed=embed)
    reset_game()

@bot.command(name="投票", description="ウルフを投票します")
async def 投票(ctx, target: discord.User):
    if target == ctx.author:
        await ctx.send("自分に投票することはできません。")
        return

    if target not in game_data['players']:
        await ctx.send(f"{target.name} はゲームに参加していません。")
        return

    if ctx.author.id in game_data['voted_users']:
        await ctx.send("あなたはすでに投票しました。")
        return

    game_data['votes'][target.id] = game_data['votes'].get(target.id, 0) + 1
    game_data['voted_users'].add(ctx.author.id)

    await ctx.send(f"{ctx.author.name} さんが {target.name} さんに投票しました。")

    # 全員が投票したら結果を表示
    if len(game_data['voted_users']) == len(game_data['players']):
        await show_result(ctx.channel)

@bot.command(name="お題変更", description="ゲームのお題を変更します")
async def お題変更(ctx, *, theme_name: str):
    if not game_data['organizer']:
        await ctx.send("まだゲームが開始されていません")
        return

    if theme_name not in theme_pool:
        await ctx.send(f'お題「{theme_name}」は存在しません。')
        return

    game_data['theme'] = theme_name
    await update_embed_players()
    await ctx.send(f'お題が「{theme_name}」に変更されました！')

@bot.command(name="お題一覧", description="ゲームのお題一覧を表示します")
async def お題一覧(ctx):
    theme_names = '\n'.join(theme_pool.keys())
    embed = discord.Embed(title="お題一覧", description=theme_names, color=0x00ffcc)
    await ctx.send(embed=embed)

@bot.command(name="全員のワード確認", description="特定のロールのメンバーに市民かウルフのワードをDMで送ります")
async def 全員のワード確認(ctx):
    if not any(role.id == ROLE_ID for role in ctx.author.roles):
        await ctx.send("このコマンドは特定のロールを持つユーザーのみ実行できます。")
        return

    if not game_data['players']:
        await ctx.send("ゲームに参加しているプレイヤーがいません。")
        return

    for player in game_data['players']:
        word = game_data['words'][player.id]
        role = "ウルフ" if word == game_data['wolf_word'] else "市民"
        try:
            await player.send(f'あなたの役職は「{role}」で、ワードは「{word}」です。')
        except:
            pass

    await ctx.send("全員にワードを送信しました。")

bot.run(TOKEN)

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
    await bot.tree.sync()

@bot.tree.command(name="ワードウルフ", description="ワードウルフゲームを開始します")
async def word_wolf(interaction: discord.Interaction):
    if game_data['organizer']:
        await interaction.response.send_message('すでにゲームが進行中です', ephemeral=True)
        return

    # ゲームデータを初期化
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

    # ボタン操作用のクラス
    class JoinView(discord.ui.View):
        @discord.ui.button(label='参加', style=discord.ButtonStyle.primary)
        async def join(self, interaction2: discord.Interaction, button: discord.ui.Button):
            if interaction2.user not in game_data['players']:
                # プレイヤーを追加
                game_data['players'].append(interaction2.user)
                await update_embed_players()
                await interaction2.response.defer()
            else:
                await interaction2.response.send_message("すでに参加しています！", ephemeral=True)

        @discord.ui.button(label='ゲーム開始（主催者のみ）', style=discord.ButtonStyle.success)
        async def start(self, interaction2: discord.Interaction, button: discord.ui.Button):
            if interaction2.user != game_data['organizer']:
                await interaction2.response.send_message("主催者のみが開始できます。", ephemeral=True)
                return
            if len(game_data['players']) < 3:
                await interaction2.response.send_message("最低3人のプレイヤーが必要です。", ephemeral=True)
                return
            await interaction2.response.defer()
            await start_game(interaction.channel)

    # 埋め込みメッセージの作成
    embed = discord.Embed(
        title='🎮 ワードウルフに参加しよう！',
        description=(
            '**📝 お題：ランダム（あとで変更可能）**\n'
            '\n'
            '1. **「参加」ボタンをクリックしてプレイヤーとして参加しましょう！**\n'
            '2. **全員が参加したら、主催者が「ゲーム開始」を押してください。（最低3人必要）**\n'
        ),
        color=0x00ff00
    )
    embed.add_field(name='現在の参加者リスト', value='誰も参加していません 🙃')

    # メッセージとボタンを送信
    message = await interaction.channel.send(embed=embed, view=JoinView())
    game_data['message_embed'] = message
    await interaction.response.send_message("ゲームを開始します！", ephemeral=True)

# プレイヤーリストを更新する関数
async def update_embed_players():
    embed = game_data['message_embed'].embeds[0]
    player_names = '\n'.join(f'・{p.name}' for p in game_data['players'])
    theme_text = game_data['theme'] if game_data['theme'] else 'ランダム（あとで変更可能）'
    embed.set_field_at(0, name='現在の参加者リスト', value=player_names or '誰も参加していません 🙃')
    embed.description = (
        f'**📝 お題**: {theme_text}\n\n'
        '1. **「参加」ボタンでゲームに参加しましょう！**\n'
        '2. **参加が完了したら、主催者が「ゲーム開始」を押してください（最低3人必要）。**'
    )
    await game_data['message_embed'].edit(embed=embed)

async def start_game(channel):
    # テーマの選定（指定がない場合はランダム）
    theme = game_data['theme']
    if not theme:
        theme = random.choice(list(theme_pool.keys()))
        game_data['theme'] = theme

    # 市民とウルフのワードを選択
    words = theme_pool[theme]
    selected = random.sample(words, 2)
    citizen_word, wolf_word = selected

    # プレイヤーリストとウルフを選定
    players = game_data['players'][:]
    wolf = random.choice(players)
    for p in players:
        word = wolf_word if p == wolf else citizen_word
        game_data['words'][p.id] = word
        # DMでプレイヤーにワードを送信
        try:
            await p.send(f'📝 **お題**: {theme}\nあなたのワードは「{word}」です。秘密を守りましょう！')
        except:
            pass

    # 市民とウルフのワードをゲームデータに保存
    game_data['citizen_word'] = citizen_word
    game_data['wolf_word'] = wolf_word

    # ゲーム開始メッセージを送信
    player_list = '\n'.join(p.name for p in players)
    embed = discord.Embed(
        title='🚀 ゲームスタート！',
        description=(
            f'🎭 **カテゴリー**: {theme}\n\n'
            f'👥 **参加プレイヤー**:\n{player_list}\n\n'
            '🕵️‍♂️ **議論を始めてください！タイムリミットを決めて話し合いましょう！**'
        ),
        color=0xff4500
    )
    await channel.send(embed=embed)

    # 特定のロールを持つユーザーに役職情報をDMで送信
    role = discord.utils.get(channel.guild.roles, id=ROLE_ID)
    if role:
        role_members = [member for member in role.members]
        embed_roles = discord.Embed(title="ゲームの役職情報", color=0x00ff00)
        for player in game_data['players']:
            role_text = "市民" if game_data['words'][player.id] == game_data['citizen_word'] else "ウルフ"
            embed_roles.add_field(name=player.name, value=role_text, inline=False)

        for member in role_members:
            try:
                await member.send(embed=embed_roles)
            except:
                pass
@bot.tree.command(name="投票", description="ウルフを投票で見つけましょう")
async def 投票(interaction: discord.Interaction):
    if interaction.user not in game_data['players']:
        await interaction.response.send_message('ゲームに参加していません', ephemeral=True)
        return

    class VoteView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            for i, player in enumerate(game_data['players']):
                self.add_item(self.make_button(i, player))

        def make_button(self, index, player):
            return discord.ui.Button(label=player.name, style=discord.ButtonStyle.primary, custom_id=str(index))

        @discord.ui.button(label="dummy", style=discord.ButtonStyle.primary, custom_id="dummy", disabled=True)
        async def button_callback(self, interaction2: discord.Interaction, button: discord.ui.Button):
            pass  # 未使用のダミーボタン

        async def interaction_check(self, interaction2: discord.Interaction):
            if interaction2.user.id in game_data['voted_users']:
                await interaction2.response.send_message("すでに投票しています。", ephemeral=True)
                return False
            index = int(interaction2.data['custom_id'])
            game_data['votes'][index] += 1
            game_data['voted_users'].add(interaction2.user.id)
            await interaction2.response.send_message("投票が完了しました。", ephemeral=True)

            # 全員が投票を終えたら結果を表示
            if len(game_data['voted_users']) == len(game_data['players']):
                await show_result(interaction2.channel)
            return True

    # 投票メッセージの埋め込みを作成
    desc = '\n'.join([f'{i+1}. {p.name}' for i, p in enumerate(game_data['players'])])
    embed = discord.Embed(
        title='🗳️ 投票タイム！',
        description='以下のボタンをクリックして投票を行ってください\n\n' + desc,
        color=0x00ffcc
    )
    game_data['vote_message'] = await interaction.channel.send(embed=embed, view=VoteView())
    game_data['votes'] = {i: 0 for i in range(len(game_data['players']))}
    game_data['voted_users'] = set()
    game_data['vote_start_time'] = discord.utils.utcnow()
    await interaction.response.send_message("投票メッセージを送信しました！", ephemeral=True)

@bot.tree.command(name="結果", description="投票結果を表示します")
async def 結果(interaction: discord.Interaction):
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

async def show_result(channel):
    votes = game_data['votes']
    players = game_data['players']

    # 投票の結果を集計
    max_votes = max(votes.values())
    candidates = [i for i, v in votes.items() if v == max_votes]
    chosen_index = candidates[0]  # 最も得票が多いプレイヤーのインデックスを選択

    chosen = players[chosen_index]
    wolf = next(p for p in players if game_data['words'][p.id] == game_data['wolf_word'])  # ウルフを特定

    # 結果メッセージの構築
    result_text = f'🗳️ **最多得票者**: {chosen.name} (得票数: {votes[chosen_index]}票)\n\n'
    result_text += f'🐺 **ウルフのワード**: 「{game_data["wolf_word"]}」\n'
    result_text += f'🛡️ **市民のワード**: 「{game_data["citizen_word"]}」\n\n'
    result_text += f'🔍 **ウルフは** {wolf.name} さんでした！\n\n'

    if chosen == wolf:
        result_text += '🎉 **市民の勝利！** 🎊'
    else:
        result_text += '🐺 **ウルフの勝利！** 🐾'

    # 埋め込みメッセージの送信
    embed = discord.Embed(title="🎊 結果発表！", description=result_text, color=0xff0000)
    await channel.send(embed=embed)

    # ゲームデータをリセット
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

@bot.tree.command(name="お題一覧", description="ゲームのお題一覧を表示します")
async def お題一覧(interaction: discord.Interaction):
    theme_names = '\n'.join(theme_pool.keys())
    embed = discord.Embed(title="お題一覧", description=theme_names, color=0x00ffcc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

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

    result_text = f"ゲームが終了しました！\n\n"
    result_text += f"ウルフのワードは「{game_data['wolf_word']}」\n"
    result_text += f"市民のワードは「{game_data['citizen_word']}」\n"
    result_text += f"ウルフは {wolf.name} さんでした！\n"

    embed = discord.Embed(title="ゲーム終了", description=result_text, color=0xff0000)
    await interaction.channel.send(embed=embed)

    reset_game()

bot.run(TOKEN)

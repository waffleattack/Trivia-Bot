import asyncio
import random
from dataclasses import asdict
from datetime import datetime
from typing import Union, List
from zoneinfo import ZoneInfo

import dacite
import discord
from dacite import from_dict
from discord import Message, Embed, Member, Role, TextChannel
from discord.ext import commands
from discord.ext.commands import Context
from pymongo import MongoClient

from data_classes import *
from util import shuffle_repeating

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix='?', intents=intents)
client = discord.Client(intents=intents)
Servers = {}
questionsList: List[Question] = []

# with open("questions.json") as f:
#    raw_questions = json.load(f)
#    for x in raw_questions["questions"]:
#        questions.append(dacite.from_dict(data_class=Question, data=x))


questions_generator = shuffle_repeating(questionsList)
token = open("./botToken", "r").read()
CONNECTION_STRING = open("./mongoDbToken", "r").read()
cluster = MongoClient(CONNECTION_STRING)


def add_footer(ctx: Union[Context, Message], embed: Embed):
    embed.set_footer(text=f"{ctx.guild}", icon_url=f"{ctx.guild.icon}")
    embed.timestamp = datetime.now(tz=ZoneInfo("America/New_York"))


@bot.event
async def on_ready():
    global Servers
    global questionsList
    question_db = cluster["Questions"]["Questions"]
    for x in question_db.find({}):
        questionsList.append(dacite.from_dict(data_class=Question, data=x))
    print(f'{bot.user} has connected to Discord!')
    for server in bot.guilds:
        print(f"Connected to Server {server.name}")
        server_data = cluster[str(server.id)]
        if server_data["Config"].count_documents({}) == 0:
            config = ServerConfig(_id=server.id)
        else:
            config = from_dict(data_class=ServerConfig, data=server_data["Config"].find({}).next())
        Servers[server.id] = ServerData(
            Scores=server_data["Scores"],
            config=config,
            currentQuestion=None
        )

    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name='MongoDB'))


@bot.hybrid_command(aliases=["et", "leaderboard"])
async def lb(ctx: Context, arg=10):
    """Shows Leaderboard"""
    server_data = Servers[ctx.guild.id]
    rankings = server_data.Scores.find().sort("score", -1)
    i = 1
    embed = discord.Embed(title=f"***Top {arg} users***")
    for x in rankings:
        user = await bot.fetch_user(int(x["_id"]))
        user_xp = x["score"]
        embed.add_field(name="", value=f"{i} : {user.mention} │ {user_xp}", inline=False)
        if i == arg:
            break
        else:
            i += 1
    add_footer(ctx, embed)
    await ctx.send(embed=embed)


@commands.cooldown(1, 2, commands.BucketType.guild)
@bot.hybrid_command(aliases=["tr"])
async def trivia(ctx: Context):
    """Creates new Trivia question : aliased to 'tr' """
    server_data = Servers[ctx.guild.id]
    if server_data.currentQuestion is not None:
        return

    server_data.currentQuestion = next(questions_generator)
    embed: Embed = discord.Embed(title="New Trivia Question!")
    print(server_data.currentQuestion.image)
    embed.set_image(url=server_data.currentQuestion.image)
    embed.add_field(value=server_data.currentQuestion, inline=True, name="")
    embed.set_footer(text=f"{ctx.guild}", icon_url=f"{ctx.guild.icon}")
    embed.timestamp = datetime.now(tz=ZoneInfo("America/New_York"))
    await ctx.send(embed=embed)


@trivia.error
async def command_name_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        em = discord.Embed(title=f"Slow it down bro!", description=f"Try again in {error.retry_after:.2f}s.")
        await ctx.send(embed=em)


@bot.hybrid_command(aliases=["sk"])
async def skip(ctx: Context):
    """skips current trivia question : aliased to 'sk'"""
    server_data = Servers[ctx.guild.id]
    if server_data.currentQuestion is None:
        return

    embed: Embed = discord.Embed(title="Answer Skipped!")
    embed.add_field(value=f"Correct answer was: {server_data.currentQuestion.answer}", inline=True, name="")
    embed.set_footer(text=f"{ctx.guild}", icon_url=f"{ctx.guild.icon}")
    embed.timestamp = datetime.now(tz=ZoneInfo("America/New_York"))
    server_data.currentQuestion = None
    await ctx.send(embed=embed)


def update_configs(ctx: Context, new_config: ServerConfig):
    config = cluster[str(ctx.guild.id)]["Config"]
    config.update_one(filter={}, upsert=True, update={"$set": asdict(new_config)})


@bot.hybrid_command(aliases=["setLeaderRole"], hidden=True)
async def set_leader_role(ctx: Context, role: Role):
    server_data = Servers[ctx.guild.id]
    server_data.config.leaderRole = role.id
    update_configs(ctx, server_data.config)
    await ctx.message.delete()


@bot.hybrid_command(aliases=["setLB"], hidden=True)
async def set_leader_board(ctx: Context, channel: TextChannel):
    server_data = Servers[ctx.guild.id]
    server_data.config.leaderboardChannel = channel.id
    update_configs(ctx, server_data.config)
    await ctx.message.delete()


async def update_leaderboard(ctx: Message):
    server_data = Servers[ctx.guild.id]
    config = server_data.config
    lb_id = config.leaderboardChannel
    lr_id = config.leaderRole

    rankings = server_data.Scores.find().sort("score", -1)
    if lr_id is not None:
        first_user: Member = await ctx.guild.fetch_member(int(rankings[0]["_id"]))
        leader_role: Role = ctx.guild.get_role(lr_id)
        if len(leader_role.members) == 0:
            await first_user.add_roles(leader_role, reason="Now Leader!")
        else:
            current_leader: Member = leader_role.members[0]
            if current_leader != first_user:
                await current_leader.remove_roles(leader_role, reason="No Longer Leader")
                await first_user.add_roles(leader_role, reason="Now Leader!")

    if lb_id is not None:
        leaderboard_channel = ctx.guild.get_channel(lb_id)
        embed = discord.Embed(title=f"***All users***")
        for i, x in enumerate(rankings):
            user = await bot.fetch_user(int(x["_id"]))
            user_xp = x["score"]
            embed.add_field(name="", value=f"{i + 1} : {user.mention} │ {user_xp}", inline=False)
        add_footer(ctx, embed)
        messages = [x async for x in leaderboard_channel.history(limit=200) if x.author == bot.user]
        if len(messages) == 0:
            await leaderboard_channel.send(embed=embed)
        else:
            try:
                await messages[0].edit(embed=embed)
            except discord.errors.HTTPException:
                await messages[0].delete()
                await leaderboard_channel.send(embed=embed)


@bot.listen('on_message')
async def process_message(ctx: Message):
    global Servers
    server_data = Servers[ctx.guild.id]
    score_counter = server_data.Scores
    if ctx.author == bot.user or ctx.author.bot:
        return

    myquery = {"_id": ctx.author.id}

    if score_counter.count_documents(myquery) == 0:
        post = {"_id": ctx.author.id, "author": ctx.author.name, "score": 0}
        score_counter.insert_one(post)
    if server_data.currentQuestion is None:
        return
    if "".join(ctx.content).upper() == server_data.currentQuestion.answer.upper():
        query = {"_id": ctx.author.id}
        user = score_counter.find(query)
        score = 0
        for result in user:
            score = result["score"]
        score = score + 1
        score_counter.update_one({"_id": ctx.author.id}, {"$set": {"score": score}})
        await ctx.channel.send("Correct!")
        server_data.currentQuestion = None
        await update_leaderboard(ctx)


async def query_string(ctx: Context, query: str) -> str:
    def check(m: Context):
        return ctx.author == m.author and ctx.channel == m.channel

    await ctx.send(query, delete_after=30)
    new_ctx: Message = await bot.wait_for("message", check=check, timeout=30)
    content = "".join(new_ctx.content)
    await new_ctx.delete()
    return content


async def query_image(ctx: Context, query: str) -> Optional[str]:
    def check(m: Context):
        return ctx.author == m.author and ctx.channel == m.channel

    await ctx.send(query, delete_after=30)
    new_ctx: Message = await bot.wait_for("message", check=check, timeout=30)
    print(new_ctx.attachments)
    if len(new_ctx.attachments) == 0:
        content = None
        if "http" in "".join(new_ctx.content):
            content = "".join(new_ctx.content)
        await new_ctx.delete()
        return content
    content = new_ctx.attachments[0].url
    # ?await new_ctx.delete()
    return content


@bot.hybrid_command(aliases=["newQ"])
async def add_question(ctx: Context):
    """adds a new question to the databse"""
    try:
        new_question = await query_string(ctx, "Enter Question")
        new_answer = await query_string(ctx, "Enter Answer")
        new_image = await query_image(ctx, "Enter Image Url or n for no image")
        question = Question(answer=new_answer, question=new_question, image=new_image)
        cluster["Questions"]["Questions"].insert_one(asdict(question))
        questionsList.append(question)
        await ctx.send("Question created!", delete_after=5)
    except asyncio.TimeoutError:
        await ctx.send("Question Creation Timeout", delete_after=10)
        return


@bot.hybrid_command(aliases=["ec"])
async def echo(ctx: Context):
    print(ctx.message.attachments[0].url)
    print(type(ctx.message.attachments[0].url))
    await ctx.send(ctx.message.attachments[0].url)


bot.run(token)

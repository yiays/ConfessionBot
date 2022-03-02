import asyncio
import disnake
from disnake.ext import tasks, commands
from time import time
import re

from disnake.raw_models import RawReactionActionEvent, RawReactionClearEvent

class Poll(commands.Cog):
  """poll is an almost stateless poll extension for discord bots
  this improved poll handles votes even if the bot goes offline and keeps the countdown timer up to date for a week after expiry"""

  emojis = ['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣','6️⃣','7️⃣','8️⃣','9️⃣','🔟']

  def __init__(self, bot:commands.Bot):
    self.bot = bot
    self.current_poll_timer.start()
    self.old_poll_timer.start()
    self.ancient_poll_timer.start()
    # ensure config file has required data
    if not bot.config.has_section('poll'):
      bot.config.add_section('poll')
  
  @commands.Cog.listener('on_raw_reaction_add')
  @commands.Cog.listener('on_raw_reaction_remove')
  async def poll_react(self, ctx:RawReactionActionEvent):
    if str(ctx.channel_id)+'_'+str(ctx.message_id)+'_expiry' in self.bot.config['poll']:
      expiry = int(self.bot.config['poll'][str(ctx.channel_id)+'_'+str(ctx.message_id)+'_expiry'])
      if expiry > time():
        channel = await self.bot.fetch_channel(ctx.channel_id)
        pollmsg = await channel.fetch_message(ctx.message_id)
        await self.redraw_poll(pollmsg, expiry)
  @commands.Cog.listener('on_raw_reaction_clear')
  async def poll_react_clear(self, ctx:RawReactionClearEvent):
    if str(ctx.channel_id)+'_'+str(ctx.message_id)+'_expiry' in self.bot.config['poll']:
      expiry = int(self.bot.config['poll'][str(ctx.channel_id)+'_'+str(ctx.message_id)+'_expiry'])
      if expiry > time():
        channel = await self.bot.fetch_channel(ctx.channel_id)
        pollmsg = await channel.fetch_message(ctx.message_id)
        await self.redraw_poll(pollmsg, expiry)

  @tasks.loop(minutes=1)
  async def current_poll_timer(self):
    for key,value in self.bot.config['poll'].items():
      try:
        expiry = int(value)
      except:
        continue
      keysplit = key.split('_')
      if len(keysplit) == 3:
        channel_id,message_id,_ = keysplit
        channel = await self.bot.fetch_channel(channel_id)
        votemsg = await channel.fetch_message(message_id)
        if expiry > time():
          await self.redraw_poll(votemsg, expiry)
        else:
          await self.expire_poll(votemsg, expiry)

  @tasks.loop(hours=1)
  async def old_poll_timer(self):
    for key,value in self.bot.config['poll'].items():
      try:
        expiry = int(value)
      except:
        continue
      if expiry < time() and expiry > time() - 86400:
        keysplit = key.split('_')
        if len(keysplit) == 4:
          channel_id,message_id,_,_ = keysplit
          channel = await self.bot.fetch_channel(channel_id)
          votemsg = await channel.fetch_message(message_id)
          await self.redraw_poll(votemsg, expiry, expired=True)
  @tasks.loop(hours=24)
  async def ancient_poll_timer(self):
    for key,value in self.bot.config['poll'].items():
      try:
        expiry = int(value)
      except:
        continue
      if expiry < time() - 86400:
        keysplit = key.split('_')
        if len(keysplit) == 4:
          channel_id,message_id,_,_ = keysplit
          channel = await self.bot.fetch_channel(channel_id)
          votemsg = await channel.fetch_message(message_id)
          await self.redraw_poll(votemsg, expiry, expired=True)
          if expiry < time() - 604800:
            self.bot.config.remove_option('poll', key)
            self.bot.config.save()

  def inttotime(self, i:int, precisionlimit:int=0, beforeprefix:str='', afterprefix:str='happened'):
    #TODO: add babel support
    if i == 0: return ' '.join([beforeprefix, 'now.'])
    out = []
    ii = abs(i)
    multipliers = [ 31449600, 2419200, 604800, 86400, 3600,   60,       1        ]
    timenames   = [ 'year',   'month', 'week', 'day', 'hour', 'minute', 'second' ]
    precision = len(multipliers) - precisionlimit
    pluralizer  = 's'

    for multiplier,timename in tuple(zip(multipliers[0:precision], timenames[0:precision])):
      if ii>=multiplier:
        product = ii//multiplier
        if product>0:
          out.append(str(product)+' '+timename+(pluralizer if product!=1 else ''))
          ii = ii%multiplier
    if len(out) > 1: out.insert(len(out)-1, 'and')
    out = ', '.join(out).replace(', and,',' and')
    if out == '': out = (afterprefix+' recently.' if i < 0 else ' '.join([beforeprefix, 'soon.']))
    else: out = (afterprefix+' ' if i<0 else beforeprefix+(' in 'if beforeprefix else '')) + out + (' ago.' if i<0 else '.')
    return out
  
  def generate_poll_line(self, value:int, max:int):
    width = round(((value/max)*20))
    return '[' + width*'■' + abs(width-20)*'□' + ']'
  def generate_poll_embed(self, title:str, counter:int, answers:list, votes:list):
    """generates a poll embed based on the provided data"""
    embed = disnake.Embed(title=title)
    if counter>0: embed.description = f"{'⏳' if counter>60 else '⌛'} {self.inttotime(counter, 1, beforeprefix='closing')}"
    elif counter < -604800: embed.description = "⌛ expired a long time ago"
    else: embed.description = f"⌛ {self.inttotime(counter, 2 if counter > -86400 else 3, afterprefix='closed')}"
    if len(answers) > 0:
      votemax = max(max(votes),1)
      index = 0
      for answer,votes in tuple(zip(answers,votes)):
        embed.add_field(name=f'{self.emojis[index]} {answer}:', value=f'{self.generate_poll_line(votes,votemax)} ({votes})', inline=False)
        index += 1
    embed.set_footer(text="react to vote | this poll is multichoice")
    return embed

  async def redraw_poll(self, msg:disnake.Message, expiry:int, expired:bool=False):
    """redraws the poll using real data"""
    title = msg.embeds[0].title
    counter = expiry - round(time())
    answers = [f.name[4:-1] for f in msg.embeds[0].fields]
    if expired: votes = [int(re.match(r'.*\((\d+)\)', f.value).group(1)) for f in msg.embeds[0].fields]
    else:
      votes = [0 for _ in answers]
      for react in msg.reactions:
        if str(react.emoji) in self.emojis:
          votes[self.emojis.index(str(react.emoji))] = react.count-1
    embed = self.generate_poll_embed(title, counter, answers, votes)
    await msg.edit(embed=embed)
    return title, answers, votes # just returning these for the one situation where they need to be reused
  
  async def expire_poll(self, msg:disnake.Message, expiry:int):
    """announces the winner of the poll"""
    title, answers, votes = await self.redraw_poll(msg, expiry, expired=True)
    winners = []
    votemax = max(max(votes),1)
    if votemax > 0:
      for answer,votecount in tuple(zip(answers, votes)):
        if votecount == votemax:
          winners.append(answer)
    
    if len(winners) == 0:
      await msg.channel.send(self.bot.babel((None, msg.guild.id,), 'poll', 'no_winner', title=title))
    elif len(winners) == 1:
      await msg.channel.send(self.bot.babel((None, msg.guild.id,), 'poll', 'one_winner', title=title, winner=winners[0]))
    else:
      if len(winners) > 2:
        winners.insert(len(winners)-1, 'and')
      winnerstring = '", "'.join(winners).replace(', and,', ' and')
      await msg.channel.send(self.bot.babel((None, msg.guild.id,), 'poll', 'multiple_winners', title=title, num=len(winners), winners=winnerstring))
    
    self.bot.config.remove_option('poll', f'{msg.channel.id}_{msg.id}_expiry')
    self.bot.config['poll'][f'{msg.channel.id}_{msg.id}_expiry_expired'] = str(expiry)
    self.bot.config.save()

  @commands.command(aliases=['vote'])
  @commands.guild_only()
  async def poll(self, ctx:commands.Context, *, title:str):
    """poll creation wizard"""
    counter = 300
    answers = []
    votes = []
    embed = self.generate_poll_embed(title, counter, answers, votes)
    pollmsg = await ctx.send(self.bot.babel(ctx, 'poll', 'poll_preview'), embed=embed)

    done = False
    while not done and len(answers)<10:
      qmsg = await ctx.reply(self.bot.babel(ctx, 'poll', 'setup1'))
      try:
        reply = await self.bot.wait_for('message', check=lambda m: m.author==ctx.author and m.channel==ctx.channel, timeout=30)
      except asyncio.TimeoutError:
        if len(answers) == 0:
          await pollmsg.delete()
          await qmsg.delete()
          await ctx.reply(self.bot.babel(ctx, 'poll', 'setup_cancelled'))
          return
        else:
          await qmsg.delete()
          done=True
      else:
        if reply.content == '[stop]':
          if len(answers) == 0:
            await pollmsg.delete()
            await qmsg.delete()
            await ctx.reply(self.bot.babel(ctx, 'poll', 'setup_cancelled'))
            return
          else:
            await qmsg.delete()
            await reply.delete()
            done=True
        else:
          answers.append(reply.content)
          votes.append(0)
          embed = self.generate_poll_embed(title, counter, answers, votes)
          await pollmsg.edit(embed=embed)
          await pollmsg.add_reaction(self.emojis[len(answers)-1])
          await qmsg.delete()
          await reply.delete()
      
    qmsg = await ctx.reply(self.bot.babel(ctx, 'poll', 'setup2'))
    reply = None
    try:
      reply = await self.bot.wait_for('message', check=lambda m: m.author==ctx.author and m.channel==ctx.channel, timeout=30)
    except asyncio.TimeoutError:
      pass
    else:
      try:
        counter = int(reply.content)*60
      except:
        pass
    await qmsg.delete()
    if reply: await reply.delete()
    if counter == 300:
      await ctx.reply(self.bot.babel(ctx, 'poll', 'setup2_failed'))
    
    await pollmsg.delete()
    embed = self.generate_poll_embed(title, counter, answers, votes)
    pollmsg = await ctx.reply(self.bot.babel(ctx, 'poll', 'poll_created', author=ctx.author.mention), embed=embed)
    for emoji in self.emojis[:len(answers)]:
      await pollmsg.add_reaction(emoji)

    self.bot.config['poll'][f'{ctx.channel.id}_{pollmsg.id}_expiry'] = str(round(time())+counter)
    self.bot.config.save()

def setup(bot):
  bot.add_cog(Poll(bot))
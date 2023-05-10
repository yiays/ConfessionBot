"""
  EventMsg - Automated messages triggered by events
  Generalized version of welcome and farewell
  Dependancies: Auth
"""

import disnake
from disnake.ext import commands
from enum import Enum

class Action(Enum):
  """ Actions that can be performed on an event """
  disable = 0
  enable = 1

class Event(Enum):
  """ Types of events that are supported """
  welcome = 0
  farewell = 1
  rank = 2
  derank = 3

class EventMsg(commands.Cog):
  """ Setup custom messages to send on an event """
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'eventmsg'")
    if not bot.config.getboolean('extensions', 'help', fallback=False):
      print(Warning("'help' is a recommended extension for 'eventmsg'"))
    # ensure config file has required data
    if not bot.config.has_section('eventmsg'):
      bot.config.add_section('eventmsg')

  @commands.Cog.listener("on_member_join")
  async def on_welcome(self, member):
    """welcome service, shows a custom welcome message to new users"""
    if f"{member.guild.id}_welcome" in self.bot.config['eventmsg']:
      data = self.bot.config['eventmsg'][f"{member.guild.id}_welcome"].split(', ')
      channel = member.guild.get_channel(int(data[0]))
      await channel.send(', '.join(data[1:]).format(member.mention, member.guild.name))

  @commands.Cog.listener("on_member_leave")
  async def on_farewell(self, member):
    """farewell service, shows a custom farewell message whenever someone leaves"""
    if f"{member.guild.id}_farewell" in self.bot.config['eventmsg']:
      data = self.bot.config['eventmsg'][f"{member.guild.id}_farewell"].split(', ')
      channel = member.guild.get_channel(int(data[0]))
      await channel.send(', '.join(data[1:]).format(f"{member.name}#{member.discriminator}", member.guild.name))

  @commands.slash_command()
  async def eventmessage(
    self,
    inter:disnake.GuildCommandInteraction,
    
  )

  @commands.group()
  @commands.guild_only()
  async def welcome(self, ctx:commands.Context):
    """welcome setter / getter"""
    if ctx.invoked_subcommand is None:
      raise commands.BadArgument
  @welcome.command(name='get')
  async def welcome_get(self, ctx:commands.Context):
    if f'{ctx.guild.id}_welcome' in self.bot.config['eventmsg']:
      data = self.bot.config['eventmsg'][f"{ctx.guild.id}_welcome"].split(', ')
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'greeting_preview', channel=ctx.guild.get_channel(int(data[0])).mention, message=', '.join(data[1:]).format('@USER', ctx.guild.name)))
    else:
      await self.welcome_set(ctx)
  @welcome.command(name='set')
  async def welcome_set(self, ctx:commands.Context, *, message:str=''):
    self.bot.cogs['Auth'].admins(ctx.message)
    if not message:
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'welcome_set_instructions'))
    else:
      self.bot.config['eventmsg'][f'{ctx.guild.id}_welcome'] = f"{ctx.channel.id}, {message}"
      self.bot.config.save()
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'welcome_set_success'))
  @welcome.command(name='clear')
  async def welcome_clear(self, ctx:commands.Context):
    self.bot.cogs['Auth'].admins(ctx.message)
    if f'{ctx.guild.id}_welcome' in self.bot.config['eventmsg']:
      self.bot.config.remove_option('eventmsg', f'{ctx.guild.id}_welcome')
      self.bot.config.save()
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'welcome_clear_success'))
    else:
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'welcome_clear_failed'))

  @commands.group()
  @commands.guild_only()
  async def farewell(self, ctx:commands.Context):
    """getter / setter for farewell"""
    if ctx.invoked_subcommand is None:
      raise commands.BadArgument
  @farewell.command(name='get')
  async def farewell_get(self, ctx:commands.Context):
    if f'{ctx.guild.id}_farewell' in self.bot.config['eventmsg']:
      data = self.bot.config['eventmsg'][f"{ctx.guild.id}_farewell"].split(', ')
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'greeting_preview', channel=ctx.guild.get_channel(int(data[0])).mention, message=', '.join(data[1:]).format('USER#1234', ctx.guild.name)))
    else:
      await self.farewell_set(ctx)
  @farewell.command(name='set')
  async def farewell_set(self, ctx:commands.Context, *, message:str=''):
    self.bot.cogs['Auth'].admins(ctx.message)
    if not message:
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'farewell_set_instructions'))
    else:
      self.bot.config['eventmsg'][f'{ctx.guild.id}_farewell'] = f"{ctx.channel.id}, {message}"
      self.bot.config.save()
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'farewell_set_success'))
  @farewell.command(name='clear')
  async def farewell_clear(self, ctx:commands.Context):
    self.bot.cogs['Auth'].admins(ctx.message)
    if f'{ctx.guild.id}_farewell' in self.bot.config['eventmsg']:
      self.bot.config.remove_option('eventmsg', f'{ctx.guild.id}_farewell')
      self.bot.config.save()
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'farewell_clear_success'))
    else:
      await ctx.reply(self.bot.babel(ctx, 'eventmsg', 'farewell_clear_failure'))


def setup(bot:commands.Bot):
  bot.add_cog(EventMsg(bot))
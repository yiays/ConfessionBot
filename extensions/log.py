"""
  Log - User activity recording and error tracing
  Features: to file, to channel, command, responses to a command, errors, misc
  Recommended cogs: Error
"""

import traceback
from typing import Union
import disnake
from disnake.ext import commands

class Log(commands.Cog):
  """ Record messages, commands and errors to file or a discord channel """
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    self.logchannel = None
    # ensure config file has required data
    if not bot.config.has_section('log'):
      bot.config.add_section('log')
    if 'logchannel' not in bot.config['log']:
      bot.config['log']['logchannel'] = ''

  @commands.Cog.listener('on_ready')
  async def get_logchannel(self):
    """ Connect to the logging channel """
    if self.bot.config['log']['logchannel'].isdigit():
      self.logchannel = await self.bot.fetch_channel(int(self.bot.config['log']['logchannel']))

  def truncate(self, string:str, maxlen:int=80):
    """ trim a long string and add ellipsis """
    return string[:maxlen] + ('...' if len(string) > maxlen else '')

  def wrap(self, content:str, author:disnake.User, channel:disnake.abc.Messageable):
    """ Format log data consistently """
    if isinstance(channel, disnake.TextChannel):
      return f"[{self.truncate(channel.guild.name, 10)}#{self.truncate(channel.name, 20)}] {self.truncate(author.name, 10)}#{author.discriminator}: {self.truncate(content)}"
    if isinstance(channel, disnake.DMChannel):
      if channel.recipient:
        return f"[DM({self.truncate(channel.recipient.name, 10)}#{channel.recipient.discriminator})] {author.name}#{author.discriminator}: {self.truncate(content)}"
      return f"[DM] {self.truncate(author.name, 10)}#{author.discriminator}: {self.truncate(content)}"
    if isinstance(channel, disnake.Thread):
      return f"[Thread] {self.truncate(author.name, 10)}#{author.discriminator}: {self.truncate(content)}"
    return f"[Unknown] {self.truncate(author.name, 10)}#{author.discriminator}: {self.truncate(content)}"

  @commands.Cog.listener('on_command')
  async def log_command(self, ctx:commands.Context):
    """ Record any command calls """
    logentry = self.wrap(ctx.message.content, ctx.message.author, ctx.message.channel)
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry, embed=ctx.message.embeds[0] if ctx.message.embeds else None)

  @commands.Cog.listener('on_application_command')
  async def log_slash_command(self, inter:disnake.ApplicationCommandInteraction):
    """ Record slash command calls """
    options = [f"{opt.name}:{self.truncate(str(opt.value), 30)}" for opt in inter.data.options]
    logentry = self.wrap(
      f"/{inter.data.name} {' '.join(options)}",
      inter.author,
      inter.channel
    )
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry)

  #TODO: research slash command completion
  @commands.Cog.listener('on_command_completion')
  async def log_response(self, ctx:commands.Context):
    """ Record any replies to a command """
    responses = []
    async for msg in ctx.history(after=ctx.message):
      if msg.author == self.bot.user and msg.reference and msg.reference.message_id == ctx.message.id:
        responses.append(msg)
    for response in responses:
      logentry = self.wrap(response.content, response.author, response.channel)
      print(logentry)
      if self.logchannel:
        await self.logchannel.send(logentry, embed=response.embeds[0] if response.embeds else None)

  async def log_misc_message(self, msg:disnake.Message):
    """ Record a message that is in some way related to a command """
    logentry = self.wrap(msg.content, msg.author, msg.channel)
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry, embed=msg.embeds[0] if msg.embeds else None)

  async def log_misc_str(self, ctx:Union[commands.Context, disnake.Interaction], content:str):
    """ Record a string and context separately """
    logentry = self.wrap(content, ctx.author, ctx.channel)
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry)

  @commands.Cog.listener('on_command_error')
  async def report_error(self, _:commands.Context, error:Exception):
    """ Record errors """
    ex = traceback.format_exception(type(error), error, error.__traceback__)
    logentry = f"caused an error:\n```\n{''.join(ex)}```"
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry)

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Log(bot))

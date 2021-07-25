import discord
from discord.ext import commands

class Log(commands.cog.Cog):
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
    if self.bot.config['log']['logchannel'].isdigit():
      self.logchannel = await self.bot.fetch_channel(int(self.bot.config['log']['logchannel']))

  def truncate(self, string:str, maxlen:int=30):
    return string[:maxlen] + ('...' if len(string) > maxlen else '')
  
  def wrap(self, message:discord.Message):
    if isinstance(message.channel, discord.TextChannel):
      return f"[{self.truncate(message.guild.name, 10)}#{self.truncate(message.channel.name)}] {self.truncate(message.author.name, 10)}#{message.author.discriminator}: {self.truncate(message.content)}"
    elif isinstance(message.channel, discord.DMChannel):
      return f"[DM({self.truncate(message.channel.recipient.name, 10)}#{message.channel.recipient.discriminator})] {'other' if message.author == self.bot.user else 'self'}: {self.truncate(message.content)}"

  @commands.Cog.listener('on_command')
  async def log_command(self, ctx:commands.Context):
    logentry = self.wrap(ctx.message)
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry, embed=ctx.message.embeds[0] if ctx.message.embeds else None)
  
  @commands.Cog.listener('on_command_completion')
  async def log_response(self, ctx:commands.Context):
    responses = []
    async for msg in ctx.history(after=ctx.message):
      if msg.author == self.bot.user and msg.reference.message_id == ctx.message.id:
        responses.append(msg)
    for response in responses:
      logentry = self.wrap(response)
      print(logentry)
      if self.logchannel:
        await self.logchannel.send(logentry, embed=response.embeds[0] if response.embeds else None)
  
  async def log_misc(self, msg:discord.Message):
    """This version is intended to be called externally from other modules that react to more than just commands."""
    logentry = self.wrap(msg)
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry, embed=msg.embeds[0] if msg.embeds else None)

  @commands.Cog.listener('on_command_error')
  async def report_error(self, ctx:commands.Context, error):
    logentry = 'caused an error:```'+str(error)+'```'
    print(logentry)
    if self.logchannel:
      await self.logchannel.send(logentry)

def setup(bot):
  bot.add_cog(Log(bot))
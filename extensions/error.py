import disnake
from disnake.ext import commands

class Error(commands.Cog):
  """user-friendly error reporting"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
  
  @commands.Cog.listener("on_command_error")
  async def handle_error(self, ctx:commands.Context, error):
    if isinstance(error, commands.CommandOnCooldown):
      print("cooldown")
      return
    elif isinstance(error, commands.CommandNotFound) or\
         isinstance(error, commands.BadArgument) or\
         isinstance(error, commands.MissingRequiredArgument):
      if 'Help' in self.bot.cogs:
        await self.bot.cogs['Help'].help(ctx, ctx.invoked_with)
      else:
        await ctx.reply(self.bot.babel(ctx, 'error', 'missingrequiredargument'))
      return
    elif isinstance(error, commands.NoPrivateMessage):
      await ctx.reply(self.bot.babel(ctx, 'error', 'noprivatemessage'))
    elif isinstance(error, commands.PrivateMessageOnly):
      await ctx.reply(self.bot.babel(ctx, 'error', 'privatemessageonly'))
    elif isinstance(error, commands.CommandInvokeError):
      await ctx.reply(self.bot.babel(ctx, 'error', 'commanderror'))
    elif isinstance(error, commands.CheckFailure) or\
         isinstance(error, commands.CheckAnyFailure):
      return
    raise error

def setup(bot):
  bot.add_cog(Error(bot))
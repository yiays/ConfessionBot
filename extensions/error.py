"""
  Error - Rich error handling cog
  Features: determine the nature of the error and explain what went wrong
  Recommended cogs: Help
"""

from typing import Union
import disnake
from disnake.ext import commands

class Error(commands.Cog):
  """user-friendly error reporting"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot

  @commands.Cog.listener("on_slash_command_error")
  @commands.Cog.listener("on_command_error")
  async def handle_error(
    self,
    ctx:Union[commands.Context, disnake.ApplicationCommandInteraction],
    error:commands.CommandError
  ):
    """ Report to the user what went wrong """
    if isinstance(error, commands.CommandOnCooldown):
      print("cooldown")
      return
    if isinstance(
      error,
      (commands.CommandNotFound, commands.BadArgument, commands.MissingRequiredArgument)
    ):
      if 'Help' in self.bot.cogs:
        await self.bot.cogs['Help'].help(
          ctx,
          ctx.invoked_with if isinstance(ctx, commands.Context) else ctx.application_command.name
        )
      else:
        await ctx.send(self.bot.babel(ctx, 'error', 'missingrequiredargument'))
      return
    if isinstance(error, commands.NoPrivateMessage):
      await ctx.send(self.bot.babel(ctx, 'error', 'noprivatemessage'))
      return
    if isinstance(error, commands.PrivateMessageOnly):
      await ctx.send(self.bot.babel(ctx, 'error', 'privatemessageonly'))
      return
    elif isinstance(error, commands.CommandInvokeError):
      if 'Auth' in self.bot.cogs and isinstance(error.original, self.bot.cogs['Auth'].AuthError):
        await ctx.send(str(error.original))
        return
      await ctx.send(self.bot.babel(ctx, 'error', 'commanderror'))
    elif isinstance(error, (commands.CheckFailure, commands.CheckAnyFailure)):
      return

def setup(bot):
  """ Bind this cog to the bot """
  bot.add_cog(Error(bot))

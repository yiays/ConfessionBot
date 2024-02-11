"""
  Example - Simple extension for Merely Framework
"""

import disnake
from disnake.ext import commands

class Test(commands.Cog):
  """ Adds an echo command and logs new members """
  def __init__(self, bot:commands.Bot):
    self.bot = bot

  @commands.user_command(name='throw_error')
  async def throw_error_usr(self, _):
    """ Throws an error for testing """
    raise Exception("Command failed successfully")

  @commands.message_command(name='throw_error')
  async def throw_error_msg(self, _):
    """ Throws an error for testing """
    raise Exception("Command failed successfully")

  @commands.slash_command(name='throw_error')
  async def throw_error_slash(self, _):
    """ Throws an error for testing """
    raise Exception("Command failed successfully")

  @commands.command(name='throw_error')
  async def throw_error_text(self, _):
    """ Throws an error for testing """
    raise Exception("Command failed successfully")

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Test(bot))

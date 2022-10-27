"""
  Example - Simple extension for Merely Framework
"""

import disnake
from disnake.ext import commands

class Example(commands.Cog):
  """ Adds an echo command and logs new members """
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('example'):
      bot.config.add_section('example')
  
  @commands.Cog.listener()
  async def on_member_join(self, member:disnake.Member):
    """ Record to log when a member joins """
    print(f"{member.name} has joined!")
  
  @commands.slash_command()
  async def example(self, inter:disnake.ApplicationCommandInteraction, echo:str):
    """ Just a simple echo command """
    await inter.send(echo, ephemeral=True)

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Example(bot))

import discord
from discord.ext import commands

class Meme(commands.cog.Cog):
  """cross promotion for another bot"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
  
  @commands.command()
  async def meme(self, ctx:commands.Context):
    await ctx.reply(self.bot.babel(ctx, 'meme', 'moving_news'))

def setup(bot):
  bot.add_cog(Meme(bot))
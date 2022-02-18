import disnake
from disnake.ext import commands

class Example(commands.Cog):
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('example'):
      bot.config.add_section('example')
  
  @commands.Cog.listener()
  async def on_member_join(self, member:disnake.Member):
    print(f"{member.name} has joined!")
  
  @commands.command()
  async def example(self, ctx:commands.Context, *, echo:str):
    await ctx.reply(echo)

def setup(bot):
  bot.add_cog(Example(bot))
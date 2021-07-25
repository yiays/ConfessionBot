import discord
from discord.ext import commands
import random

class Dice(commands.cog.Cog):
  """simple dice rolling command extension, could be treated like another example"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot

  @commands.command(aliases=['roll'])
  async def dice(self, ctx:commands.Context, *numbers):
    """rolls one more many n-sided die"""
    if len(numbers) == 0:
      numbers = ['6']
    elif len(numbers) > 8:
      numbers = numbers[:8]
    rolls = []
    for i,n in enumerate(numbers):
      if n.isdigit():
        r = random.choice(range(1, int(n) + 1))
        rolls.append(self.bot.babel(ctx, 'dice', 'roll_result', i=i + 1, r=r))
    await ctx.reply('\n'.join(rolls))

def setup(bot):
  bot.add_cog(Dice(bot))

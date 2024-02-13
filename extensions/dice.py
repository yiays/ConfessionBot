"""
  Dice - Random Number Generation
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
  from ..main import MerelyBot


class Dice(commands.Cog):
  """simple dice rolling command extension, could be treated like another example"""
  def __init__(self, bot:MerelyBot):
    self.bot = bot

  @commands.slash_command()
  async def dice(self, inter:disnake.ApplicationCommandInteraction, sides:str = 6):
    """
    Roll an n-sided dice

    Parameters
    ----------
    sides: The number of sides on your dice, separate with commas for multiple dice
    """

    result = []
    for i, n in enumerate(sides.split(',')):
      try:
        result.append(
          self.bot.babel(inter, 'dice', 'roll_result', i=i+1, r=random.choice(range(1, int(n) + 1)))
        )
      except (ValueError, IndexError):
        return await inter.send(self.bot.babel(inter, 'dice', 'roll_error'))

    await inter.send('\n'.join(result))


def setup(bot:MerelyBot):
  """ Bind this cog to the bot """
  bot.add_cog(Dice(bot))

"""
  Emoji - Nitro-like emoji features for all users
  Allows users to use emoji from other servers by command
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
  from ..main import MerelyBot


class Emoji(commands.Cog):
  """ Emojis from guilds as commands """
  def __init__(self, bot:MerelyBot):
    self.bot = bot

  @commands.slash_command()
  async def emoji(self, inter:disnake.ApplicationCommandInteraction, search:str):
    """
    Searches emojis from all servers merely is a part of for one to use

    Parameters
    ----------
    search: Type to refine your search
    """
    emojiname = search.split(' ', maxsplit=1)[0].replace(':','').lower()

    if '(' in search:
      try:
        guild = self.bot.get_guild(int(search.split('(')[1][:-1]))
      except ValueError:
        matches = []
      else:
        matches = [e for e in guild.emojis if emojiname == e.name.lower()] if guild else []
    else:
      matches = [e for e in self.bot.emojis if emojiname == e.name.lower()]

    if matches:
      await inter.send(matches[0])
    else:
      await inter.send(self.bot.babel(inter, 'emoji', 'not_found'))

  @emoji.autocomplete('search')
  def ac_emoji(self, _:disnake.ApplicationCommandInteraction, search:str):
    """ Autocomplete for emoji search """
    results = [
      f':{e.name}: ({e.guild_id})'
      for e in self.bot.emojis if search.replace(':','').lower() in e.name.lower()
    ]
    return results[:25]


def setup(bot:MerelyBot):
  """ Bind this cog to the bot """
  bot.add_cog(Emoji(bot))

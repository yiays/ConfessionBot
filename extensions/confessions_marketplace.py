"""
  Confessions Marketplace - Anonymous buying and selling of goods
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy

from overlay.extensions.confessions_common import ChannelType, check_channel


class ConfessionsMarketplace(commands.Cog):
  """ Enable anonymous trade """
  SCOPE = 'confessions'

  @property
  def config(self) -> SectionProxy:
    """ Shorthand for self.bot.config[scope] """
    return self.bot.config[self.SCOPE]

  def babel(self, target:Resolvable, key:str, **values: dict[str, str | bool]) -> str:
    """ Shorthand for self.bot.babel(scope, key, **values) """
    return self.bot.babel(target, self.SCOPE, key, **values)

  def __init__(self, bot:MerelyBot):
    self.bot = bot

    if 'confessions' not in bot.config['extensions']:
      raise Exception("Module `confessions` must be enabled!")

  # Slash commands

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  @commands.slash_command()
  async def sell(
    self,
    inter: disnake.GuildCommandInteraction,
    title: str = commands.Param(max_length=80),
    description: Optional[str] = commands.Param(default=None, max_length=1000),
    image: Optional[disnake.Attachment] = None
  ):
    """
    Start an anonymous listing

    Parameters
    ----------
    title: A short summary of the item you are selling
    description: Further details about the item you are selling
    image: A picture of the item you are selling
    """
    channeltype = check_channel(self.config, inter.guild_id, inter.channel_id)
    if channeltype != ChannelType.marketplace:
      if channeltype is False:
        await inter.send(self.babel(inter, 'nosendchannel'), ephemeral=True)
      else:
        await inter.send(self.babel(inter, 'wrongcommand', cmd='confess'), ephemeral=True)
      return

    clean_desc = description.replace('# ', '') if description else '' # TODO: do this with regex
    await self.bot.cogs['Confessions'].confess(
      inter, f'# For sale: {title}\n{clean_desc}', image, marketplace=True
    )


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(ConfessionsMarketplace(bot))

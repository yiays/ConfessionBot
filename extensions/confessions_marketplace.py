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

from overlay.extensions.confessions_common import ChannelType, get_guildchannels


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
    starting_price: str = commands.Param(max_length=10),
    payment_methods: str = commands.Param(min_length=3, max_length=60),
    description: Optional[str] = commands.Param(default=None, max_length=1000),
    image: Optional[disnake.Attachment] = None
  ):
    """
      Start an anonymous listing

      Parameters
      ----------
      title: A short summary of the item you are selling
      starting_price: The price you would like to start bidding at, in whatever currency you accept
      payment_methods: Payment methods you will accept, PayPal, Venmo, Crypto, etc.
      description: Further details about the item you are selling
      image: A picture of the item you are selling
    """
    guildchannels = get_guildchannels(self.config, inter.guild_id)
    if inter.channel_id not in guildchannels:
      await inter.send(self.babel(inter, 'nosendchannel'), ephemeral=True)
      return
    if guildchannels[inter.channel_id] != ChannelType.marketplace():
      await inter.send(self.babel(inter, 'wrongcommand', cmd='confess'), ephemeral=True)
      return

    clean_desc = description.replace('# ', '') if description else '' # TODO: do this with regex
    embed = disnake.Embed(title=title, description=clean_desc)
    embed.add_field('Starting price:', starting_price, inline=True)
    embed.add_field('Accepted payment methods:', payment_methods, inline=True)
    embed.set_footer(text=self.babel(inter, 'shop_disclaimer'))

    # We provide description as content for the spam checker, otherwise this is unused
    await self.bot.cogs['Confessions'].confess(
      inter, description if description else title, image=image, embed=embed
    )


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(ConfessionsMarketplace(bot))

"""
  Confessions Marketplace - Anonymous buying and selling of goods
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from enum import IntEnum
import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy

from overlay.extensions.confessions_common import ChannelType, get_guildchannels, ConfessionData


class MarketplaceFlags(IntEnum):
  UNSET = 0
  LISTING = 1
  OFFER = 2


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

  # Modals

  class OfferModal(discord.ui.Modal):
    """ Modal that appears when a user wants to make an offer on a listing """
    def __init__(
      self, parent:"ConfessionsMarketplace", origin:discord.Interaction
    ):
      self.parent = parent
      self.origin = origin
      super().__init__(
        title=parent.babel(origin, 'button_offer', listing=origin.message.embeds[0].title),
        custom_id="listing_offer"
      )
      self.price = discord.ui.TextInput(
        label=parent.babel(origin, 'offer_price_label'),
        placeholder=parent.babel(origin, 'offer_price_example'),
        custom_id='offer_price',
        style=discord.TextStyle.short,
        min_length=3,
        max_length=30
      )
      self.add_item(self.price)

      self.method = discord.ui.TextInput(
        label=parent.babel(origin, 'offer_method_label'),
        placeholder=parent.babel(origin, 'offer_method_example'),
        custom_id='offer_method',
        style=discord.TextStyle.short,
        min_length=3,
        max_length=30
      )
      self.add_item(self.method)

    async def on_submit(self, inter:discord.Interaction):
      """ User has completed making their offer """
      guildchannels = get_guildchannels(self.parent.config, inter.guild_id)
      if (
        inter.channel_id not in guildchannels or
        guildchannels[inter.channel_id] != ChannelType.marketplace
      ):
        await inter.response.send_message(self.parent.babel(inter, 'nosendchannel'), ephemeral=True)
        return

      embed = discord.Embed(
        title=self.parent.babel(self.origin, 'offer_for', listing=self.origin.message.embeds[0].title)
      )
      embed.add_field(name='Offer price:', value=self.price.value, inline=True)
      embed.add_field(name='Offer payment method:', value=self.method.value, inline=True)
      embed.set_footer(text=self.parent.babel(inter, 'shop_disclaimer'))

      pendingconfession = ConfessionData(self.parent.bot.cogs['Confessions'])
      pendingconfession.create(
        author=inter.user, targetchannel=inter.channel, reference=self.origin.message
      )
      pendingconfession.set_content(embed=embed)
      pendingconfession.channeltype_flags = MarketplaceFlags.OFFER

      if vetting := await pendingconfession.check_vetting(inter):
        await self.parent.bot.cogs['ConfessionsModeration'].send_vetting(
          inter, pendingconfession, vetting
        )
        return
      if vetting is False:
        return
      await pendingconfession.send_confession(inter, True, webhook_override=False)

  # Views

  class ListingView(discord.ui.View):
    """ Simply adds buy and withdraw buttons """
    def __init__(self, parent:ConfessionsMarketplace, inter:discord.Interaction, id_seller:str):
      super().__init__(timeout=None)
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_offer', listing=None),
        custom_id='confessionmarketplace_offer_'+id_seller,
        emoji='💵',
        style=discord.ButtonStyle.blurple
      ))
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_withdraw', sell=True),
        custom_id='confessionmarketplace_withdraw_'+id_seller,
        style=discord.ButtonStyle.grey
      ))

  class OfferView(discord.ui.View):
    """ Simply adds accept and withdraw buttons """
    def __init__(
      self, parent:ConfessionsMarketplace, inter:discord.Interaction, id_seller:str, id_buyer:str
    ):
      super().__init__(timeout=None)
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_accept', listing=None),
        custom_id='confessionmarketplace_accept_'+id_seller+'_'+id_buyer,
        emoji='✅',
        style=discord.ButtonStyle.gray
      ))
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_withdraw', sell=False),
        custom_id='confessionmarketplace_withdraw_'+id_buyer,
        style=discord.ButtonStyle.grey
      ))

  # Events

  @commands.Cog.listener('on_interaction')
  async def check_button_click(self, inter:discord.Interaction):
    """ Check the button press events and handle relevant ones """
    if inter.type != discord.InteractionType.component:
      return
    if inter.data.get('custom_id').startswith('confessionmarketplace_offer'):
      return await self.on_create_offer(inter)
    if inter.data.get('custom_id').startswith('confessionmarketplace_accept'):
      return await self.on_accept_offer(inter)
    if inter.data.get('custom_id').startswith('confessionmarketplace_withdraw'):
      return await self.on_withdraw(inter)

  async def on_create_offer(self, inter:discord.Interaction):
    """ Open the offer form when a user wants to make an offer on a listing """
    if len(inter.message.embeds) == 0:
      await inter.response.send_message(self.babel(inter, 'error_embed_deleted'), ephemeral=True)
      return
    id_seller = inter.data.get('custom_id')[28:]
    id_buyer = (
      self.bot.cogs['Confessions'].crypto.encrypt(inter.user.id.to_bytes(8, 'big')).decode('ascii')
    )
    if id_seller == id_buyer:
      await inter.response.send_message(self.babel(inter, 'error_self_offer'), ephemeral=True)
      return
    await inter.response.send_modal(self.OfferModal(self, inter))

  async def on_accept_offer(self, inter:discord.Interaction):
    listing = await inter.channel.fetch_message(inter.message.reference.message_id)
    if len(listing.embeds) == 0 or len(inter.message.embeds) == 0:
      await inter.response.send_message(self.babel(inter, 'error_embed_deleted'), ephemeral=True)
      return
    if len(inter.data.get('custom_id')) < 31:
      await inter.response.send_message(self.babel(inter, 'error_old_offer'), ephemeral=True)
      return
    encrypted_data = inter.data.get('custom_id')[29:].split('_')

    seller_id = int.from_bytes(self.bot.cogs['Confessions'].crypto.decrypt(encrypted_data[0]), 'big')
    buyer_id = int.from_bytes(self.bot.cogs['Confessions'].crypto.decrypt(encrypted_data[1]), 'big')
    if seller_id == inter.user.id:
      seller = inter.user
      buyer = await inter.guild.fetch_member(buyer_id)
    else:
      await inter.response.send_message(
        self.babel(inter, 'error_wrong_person', buy=True), ephemeral=True
      )
      return
    receipts = [listing.embeds[0], inter.message.embeds[0]]
    await inter.response.defer()
    await seller.send(self.babel(
      inter, 'sale_complete',
      listing=listing.embeds[0].title,
      sell=True,
      other=buyer.mention
    ), embeds=receipts)
    await buyer.send(self.babel(
      inter, 'sale_complete',
      listing=listing.embeds[0].title,
      sell=True,
      other=seller.mention
    ), embeds=receipts)
    await inter.message.edit(content=self.babel(inter, 'offer_accepted'), view=None)

  async def on_withdraw(self, inter:discord.Interaction):
    encrypted_data = inter.data.get('custom_id')[31:].split('_')
    owner_id = int.from_bytes(self.bot.cogs['Confessions'].crypto.decrypt(encrypted_data[-1]), 'big')
    if owner_id != inter.user.id:
      await inter.response.send_message(
        self.babel(inter, 'error_wrong_person', buy=False), ephemeral=True
      )
      return
    if len(encrypted_data) == 1: # listing
      await inter.message.edit(
        content=self.babel(inter, 'listing_withdrawn'),
        view=None
      )
    elif len(encrypted_data) == 2: # offer
      await inter.message.edit(
        content=self.babel(inter, 'offer_withdrawn'),
        view=None
      )
    else:
      raise Exception("Unknown state encountered!", len(encrypted_data))

  # Slash commands

  @app_commands.command()
  @app_commands.describe(
    title="A short summary of the item you are selling",
    starting_price="The price you would like to start bidding at, in whatever currency you accept",
    payment_methods="Payment methods you will accept, PayPal, Venmo, Crypto, etc.",
    description="Further details about the item you are selling",
    image="A picture of the item you are selling"
  )
  @commands.cooldown(1, 1, type=commands.BucketType.user)
  async def sell(
    self,
    inter:discord.Interaction,
    title:app_commands.Range[str, 1, 80],
    starting_price:app_commands.Range[str, 1, 10],
    payment_methods:app_commands.Range[str, 3, 60],
    description:Optional[app_commands.Range[str, 0, 1000]] = None,
    image:Optional[discord.Attachment] = None
  ):
    """
      Start an anonymous listing
    """
    guildchannels = get_guildchannels(self.config, inter.guild_id)
    if inter.channel_id not in guildchannels:
      await inter.response.send_message(self.babel(inter, 'nosendchannel'), ephemeral=True)
      return
    if guildchannels[inter.channel_id] != ChannelType.marketplace:
      await inter.response.send_message(self.babel(
        inter, 'wrongcommand', cmd='confess', channel=inter.channel.mention
      ), ephemeral=True)
      return

    clean_desc = description.replace('# ', '') if description else '' # TODO: do this with regex
    embed = discord.Embed(title=title, description=clean_desc)
    embed.add_field(name='Starting price:', value=starting_price, inline=True)
    embed.add_field(name='Accepted payment methods:', value=payment_methods, inline=True)
    embed.set_footer(text=self.babel(inter, 'shop_disclaimer'))

    pendingconfession = ConfessionData(self.bot.cogs['Confessions'])
    pendingconfession.create(author=inter.user, targetchannel=inter.channel)
    pendingconfession.set_content(embed=embed)
    if image:
      await inter.response.defer(ephemeral=True)
      await pendingconfession.add_image(attachment=image)
    pendingconfession.channeltype_flags = MarketplaceFlags.LISTING

    if vetting := await pendingconfession.check_vetting(inter):
      await self.bot.cogs['ConfessionsModeration'].send_vetting(inter, pendingconfession, vetting)
      return
    if vetting is False:
      return
    await pendingconfession.send_confession(inter, True, webhook_override=False)

  # Special ChannelType code
  async def on_channeltype_send(
    self, inter:discord.Interaction, data:ConfessionData
  ) -> dict[str] | bool:
    """ Add a view for headed for a marketplace channnel """
    if data.channeltype_flags == MarketplaceFlags.LISTING:
      id_seller = data.parent.crypto.encrypt(data.author.id.to_bytes(8, 'big')).decode('ascii')
      return {
        'use_webhook': False,
        'view': self.ListingView(self, inter, id_seller)
      }
    elif data.channeltype_flags == MarketplaceFlags.OFFER:
      listing = await data.targetchannel.fetch_message(data.reference.id)
      id_seller = listing.components[0].children[0].custom_id[28:]
      id_buyer = data.parent.crypto.encrypt(data.author.id.to_bytes(8, 'big')).decode('ascii')
      return {
        'use_webhook': False,
        'view': self.OfferView(self, inter, id_seller, id_buyer)
      }
    else:
      raise Exception("Unknown state encountered!", data.channeltype_flags)


async def setup(bot:MerelyBot):
  """ Bind this cog to the bot """
  await bot.add_cog(ConfessionsMarketplace(bot))

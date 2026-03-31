"""
  Confessions Marketplace - Anonymous buying and selling of goods
"""
from __future__ import annotations

from typing import Optional, Any, Literal, TYPE_CHECKING, cast
from enum import IntEnum
from base64 import b64encode, b64decode
import discord
from discord import app_commands
from discord.ext import commands

from .confessions_common import ConfessionCog, ChannelType, get_guildchannels, ConfessionData

if TYPE_CHECKING:
  from main import MerelyBot
  from .confessions_moderation import ConfessionsModeration


class MarketplaceFlags(IntEnum):
  UNSET = 0
  LISTING = 1
  OFFER = 2


class ConfessionsMarketplace(ConfessionCog):
  """ Enable anonymous trade """
  SCOPE = 'confessions'

  def __init__(self, bot:MerelyBot):
    self.bot = bot

    if 'confessions' not in bot.config['extensions']:
      raise Exception("Module `confessions` must be enabled!")

    cog = cast(ConfessionCog, bot.cogs['Confessions'])
    self.crypto = cog.crypto

  # Modals

  class OfferModal(discord.ui.Modal):
    """ Modal that appears when a user wants to make an offer on a listing """
    def __init__(
      self, parent:"ConfessionsMarketplace", origin:discord.Interaction
    ):
      self.parent = parent
      self.origin = origin
      assert origin.message is not None and origin.message.embeds[0].title is not None
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
      assert inter.channel is not None and inter.guild is not None
      guildchannels = get_guildchannels(self.parent.config, inter.guild.id)
      if guildchannels.get(inter.channel.id, ChannelType.unset) != ChannelType.marketplace:
        await inter.response.send_message(self.parent.babel(inter, 'nosendchannel'), ephemeral=True)
        return

      assert self.origin.message is not None and self.origin.message.embeds[0].title is not None
      embed = discord.Embed(
        title=self.parent.babel(self.origin, 'offer_for', listing=self.origin.message.embeds[0].title)
      )
      embed.add_field(name='Offer price:', value=self.price.value, inline=True)
      embed.add_field(name='Offer payment method:', value=self.method.value, inline=True)
      embed.set_footer(text=self.parent.babel(inter, 'shop_disclaimer'))

      pendingconfession = ConfessionData(self.parent)
      assert isinstance(inter.channel, (discord.TextChannel, discord.Thread))
      pendingconfession.create(
        author=inter.user, target=inter.channel, reference=self.origin.message
      )
      pendingconfession.set_content(embed=embed)
      pendingconfession.channeltype_flags = MarketplaceFlags.OFFER

      if vetting := await pendingconfession.check_vetting(inter):
        cog = cast("ConfessionsModeration", self.parent.bot.cogs['ConfessionsModeration'])
        await cog.send_vetting(inter, pendingconfession, vetting)
        return
      if vetting is False:
        return
      await pendingconfession.send_confession(inter, True, webhook_override=False)

  # Views

  class ListingView(discord.ui.View):
    """ Simply adds buy and withdraw buttons """
    def __init__(self, parent:ConfessionsMarketplace, inter:discord.Interaction, id_seller:str):
      assert inter.guild is not None
      super().__init__(timeout=None)
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_offer', listing=False),
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
      assert inter.guild is not None
      super().__init__(timeout=None)
      self.add_item(discord.ui.Button(
        label=parent.babel(inter.guild, 'button_accept', listing=False),
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
    assert inter.data is not None and 'custom_id' in inter.data
    if inter.data['custom_id'].startswith('confessionmarketplace_offer'):
      return await self.on_create_offer(inter)
    if inter.data['custom_id'].startswith('confessionmarketplace_accept'):
      return await self.on_accept_offer(inter)
    if inter.data['custom_id'].startswith('confessionmarketplace_withdraw'):
      return await self.on_withdraw(inter)

  async def on_create_offer(self, inter:discord.Interaction):
    """ Open the offer form when a user wants to make an offer on a listing """
    assert inter.message is not None
    if len(inter.message.embeds) == 0:
      await inter.response.send_message(self.babel(inter, 'error_embed_deleted'), ephemeral=True)
      return
    assert inter.data is not None and 'custom_id' in inter.data
    id_seller = inter.data['custom_id'][28:]
    raw_buyer = self.crypto.encrypt(inter.user.id.to_bytes(8, 'big'))
    id_buyer = b64encode(raw_buyer).decode('ascii')
    if id_seller == id_buyer:
      await inter.response.send_message(self.babel(inter, 'error_self_offer'), ephemeral=True)
      return
    await inter.response.send_modal(self.OfferModal(self, inter))

  async def on_accept_offer(self, inter:discord.Interaction):
    assert isinstance(inter.channel, (discord.TextChannel, discord.Thread))
    assert inter.message and inter.message.reference and inter.message.reference.message_id
    listing = await inter.channel.fetch_message(inter.message.reference.message_id)
    if len(listing.embeds) == 0 or len(inter.message.embeds) == 0:
      await inter.response.send_message(self.babel(inter, 'error_embed_deleted'), ephemeral=True)
      return
    assert inter.data is not None and 'custom_id' in inter.data
    if len(inter.data['custom_id']) < 31:
      await inter.response.send_message(self.babel(inter, 'error_old_offer'), ephemeral=True)
      return
    encrypted_data = inter.data['custom_id'][29:].split('_')

    raw_seller_id = self.crypto.decrypt(b64decode(encrypted_data[0]))
    seller_id = int.from_bytes(b64decode(raw_seller_id), 'big')
    raw_buyer_id = self.crypto.decrypt(b64decode(encrypted_data[1]))
    buyer_id = int.from_bytes(b64decode(raw_buyer_id), 'big')
    if seller_id == inter.user.id:
      seller = inter.user
      assert inter.guild is not None
      buyer = await inter.guild.fetch_member(buyer_id)
    else:
      await inter.response.send_message(
        self.babel(inter, 'error_wrong_person', buy=True), ephemeral=True
      )
      return
    receipts = [listing.embeds[0], inter.message.embeds[0]]
    await inter.response.defer()
    assert listing.embeds[0].title is not None
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
    assert inter.data is not None and 'custom_id' in inter.data
    assert inter.message is not None
    encrypted_data = inter.data['custom_id'][31:].split('_')
    raw_owner_id = self.crypto.decrypt(b64decode(encrypted_data[-1]))
    owner_id = int.from_bytes(b64decode(raw_owner_id), 'big')
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

  @app_commands.command(
    name=app_commands.locale_str('sell', scope=SCOPE),
    description=app_commands.locale_str('sell_desc', scope=SCOPE)
  )
  @app_commands.allowed_contexts(guilds=True)
  @app_commands.describe(
    title=app_commands.locale_str('sell_title_desc', scope=SCOPE),
    starting_price=app_commands.locale_str('sell_starting_price_desc', scope=SCOPE),
    payment_methods=app_commands.locale_str('sell_payment_methods_desc', scope=SCOPE),
    description=app_commands.locale_str('sell_description_desc', scope=SCOPE),
    image=app_commands.locale_str('sell_image_desc', scope=SCOPE)
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
    assert inter.guild is not None
    assert isinstance(inter.channel, (discord.TextChannel, discord.Thread))
    guildchannels = get_guildchannels(self.config, inter.guild.id)
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

    pendingconfession = ConfessionData(self)
    pendingconfession.create(author=inter.user, target=inter.channel)
    pendingconfession.set_content(embed=embed)
    if image:
      await inter.response.defer(ephemeral=True)
      await pendingconfession.add_image(attachment=image)
    pendingconfession.channeltype_flags = MarketplaceFlags.LISTING

    if vetting := await pendingconfession.check_vetting(inter):
      cog = cast("ConfessionsModeration", self.bot.cogs['ConfessionsModeration'])
      await cog.send_vetting(inter, pendingconfession, vetting)
      return
    if vetting is False:
      return
    await pendingconfession.send_confession(inter, True, webhook_override=False)

  # Special ChannelType code
  async def on_channeltype_send(
    self, inter:discord.Interaction, data:ConfessionData
  ) -> dict[str, Any] | Literal[False]:
    """ Add a view for headed for a marketplace channnel """
    if data.channeltype_flags == MarketplaceFlags.LISTING:
      raw_seller = data.parent.crypto.encrypt(data.author.id.to_bytes(8, 'big'))
      id_seller = b64encode(raw_seller).decode('ascii')
      return {
        'use_webhook': False,
        'view': self.ListingView(self, inter, id_seller)
      }
    elif data.channeltype_flags == MarketplaceFlags.OFFER:
      assert data.reference is not None
      listing = await data.target.fetch_message(data.reference.id)
      actionrow = listing.components[0]
      assert isinstance(actionrow, discord.ActionRow)
      button = actionrow.children[0]
      assert button.custom_id is not None
      id_seller = button.custom_id[28:]
      raw_buyer = data.parent.crypto.encrypt(data.author.id.to_bytes(8, 'big'))
      id_buyer = b64encode(raw_buyer).decode('ascii')
      return {
        'use_webhook': False,
        'view': self.OfferView(self, inter, id_seller, id_buyer)
      }
    else:
      raise Exception("Unknown state encountered!", data.channeltype_flags)


async def setup(bot:MerelyBot):
  """ Bind this cog to the bot """
  await bot.add_cog(ConfessionsMarketplace(bot))

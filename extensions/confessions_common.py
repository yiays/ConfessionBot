"""
  Confessions Common - Classes shared by multiple confessions submodules
  Note: Do not enable as an extension, code in here is used implicitly
  To reload, reload each of the enabled confessions modules
"""
from __future__ import annotations

import io, os, base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from typing import Optional, Union, TYPE_CHECKING
import disnake
import aiohttp

if TYPE_CHECKING:
  from collections.abc import Mapping
  from overlay.extensions.confessions import Confessions
  from overlay.extensions.confessions_moderation import ConfessionsModeration
  from overlay.extensions.confessions_setup import ConfessionsSetup
  from configparser import SectionProxy
  from babel import Babel, Resolvable


# Data Classes

class ChannelType:
  """ Channel Types as they are stored """

  name:str
  value:int
  icon:str
  anonid:bool

  NAMES = {
    -1: 'unset',
    0: 'untraceable',
    1: 'traceable',
    2: 'vetting',
    3: 'feedback',
    4: 'untraceablefeedback',
    5: 'marketplace'
  }

  ICONS = {
    -1: '❓',
    0: '👻',
    1: '💬',
    2: '🧑‍⚖️',
    3: '📢',
    4: '💨',
    5:  '🛒'
  }

  ANONIDS = {
    -1: False,
    0: False,
    1: True,
    2: True,
    3: True,
    4: False,
    5: True
  }

  DEPS = {
    -1: None,
    0: None,
    1: None,
    2: 'ConfessionsModeration',
    3: None,
    4: None,
    5: 'ConfessionsMarketplace'
  }

  SWAPS = {0:1, 1:0, 3:4, 4:3}

  def __init__(self, i:int):
    self.name = self.NAMES[i]
    self.value = i
    self.icon = self.ICONS[i]
    self.anonid = self.ANONIDS[i]

  def __getitem__(self, i:str) -> ChannelType:
    return ChannelType({v:k for k,v in self.NAMES.items()}[i])

  def __int__(self):
    return self.value

  def __eq__(self, other):
    return isinstance(other, ChannelType) and other.value == self.value

  @classmethod
  def unset(cls) -> ChannelType:
    """ A channel that has no config """
    return cls(-1)

  @classmethod
  def untraceable(cls) -> ChannelType:
    """ A channel that has anonymous messages, but no Anon-IDs """
    return cls(0)

  @classmethod
  def traceable(cls) -> ChannelType:
    """ A channel that has anonymous messages, with Anon-IDs """
    return cls(1)

  @classmethod
  def vetting(cls) -> ChannelType:
    """ A channel that intercepts messages headed to other channels """
    return cls(2)

  @classmethod
  def feedback(cls) -> ChannelType:
    """ A channel that has anonymous feedback messages, with Anon-IDs """
    return cls(3)

  @classmethod
  def untraceablefeedback(cls) -> ChannelType:
    """ A channel that has anonymous feedback messages, but no Anon-IDs """
    return cls(4)

  @classmethod
  def marketplace(cls) -> ChannelType:
    """ A channel that hosts an anonymous marketplace """
    return cls(5)

  def localname(self, babel:Babel, target:Resolvable, long:bool = True) -> str:
    """ Find name of current ChannelType in Babel """
    name = None
    #BABEL: channeltype_#,channeltype_#-#
    for key in babel.langs[babel.defaultlang]['confessions']:
      if key.startswith('channeltype_'):
        if key == f'channeltype_{self.value}':
          name = babel(target, 'confessions', key)
          break
        elif len(key) == 15 and self.value in range(int(key[-3]), int(key[-1]) + 1):
          name = babel(target, 'confessions', key)
          break
    ext = None
    if long and self.value in self.SWAPS.keys():
      if self.anonid:
        ext = babel(target, 'confessions', 'channeltype_traceable')
      else:
        ext = babel(target, 'confessions', 'channeltype_untraceable')
    return name + (' ' + ext if ext else '')


# Utility functions

def get_channeltypes(cogs:Mapping[str, disnake.ext.commands.Cog]) -> list[ChannelType]:
  """ Provide a selection of ChannelTypes based on the currently active modules """
  return [ChannelType(int(i)) for i, d in ChannelType.DEPS.items() if d is None or d in cogs]


def findvettingchannel(guildchannels:dict[int, ChannelType]) -> Optional[int]:
  """ Check if guild has a vetting channel and return it """
  for channel_id in guildchannels:
    if guildchannels[channel_id] == ChannelType.vetting():
      return channel_id
  return None


def get_guildchannels(config:SectionProxy, guild_id:int) -> dict[int, ChannelType]:
  """ Returns a dictionary of {channel_id: channel_type} for the provided guild """
  return {int(k):ChannelType(int(v)) for k,v in (
    e.split('=') for e in config.get(f'{guild_id}_channels', fallback='').split(',') if e
  )}


def set_guildchannels(config:SectionProxy, guild_id:int, guildchannels:dict[int, ChannelType] | None):
  """ Writes a dictionary of {channel_id: channel_type} to the config """
  if guildchannels:
    config[f'{guild_id}_channels'] = ','.join(f'{k}={int(v)}' for k,v in guildchannels.items())
  else:
    config.pop(f'{guild_id}_channels')


# Exceptions

class CorruptConfessionDataException(Exception):
  """ Thrown when decrypted ConfessionData doesn't fit the required format """


class NoMemberCacheError(Exception):
  """ Unable to continue without a member cache """


# Views

class ChannelSelectView(disnake.ui.View):
  """ View for selecting a target interactively """
  page: int = 0
  selection: Optional[disnake.TextChannel] = None
  done: bool = False

  def __init__(
      self,
      origin:disnake.Message | disnake.Interaction,
      parent:Confessions | ConfessionsSetup,
      matches:list[tuple[disnake.TextChannel, ChannelType]]
    ):
    super().__init__()
    self.origin = origin
    self.parent = parent
    self.matches = matches
    self.soleguild = matches[0][0].guild if all((m.guild for m,_ in matches)) else None
    self.update_list()
    self.channel_selector.placeholder = self.parent.babel(origin, 'channelprompt_placeholder')
    self.send_button.label = self.parent.babel(origin, 'channelprompt_button_send')

    if len(matches) > 25:
      # Add pagination only when needed
      self.page_decrement_button = disnake.ui.Button(
        disabled=True,
        style=disnake.ButtonStyle.secondary,
        label=self.parent.babel(origin, 'channelprompt_button_prev')
      )
      self.page_decrement_button.callback = self.change_page(-1)
      self.add_item(self.page_decrement_button)

      self.page_increment_button = disnake.ui.Button(
        disabled=False,
        style=disnake.ButtonStyle.secondary,
        label=self.parent.babel(origin, 'channelprompt_button_next')
      )
      self.page_increment_button.callback = self.change_page(1)
      self.add_item(self.page_increment_button)

  def update_list(self):
    """
      Fill channel selector with channels
      Discord limits this to 25 options, so longer lists need pagination
    """
    start = self.page*25
    self.channel_selector.options = [
      disnake.SelectOption(
        label='#' + channel.name + ('' if self.soleguild else f' (from {channel.guild.name})'),
        value=channel.id,
        emoji=channeltype.icon
      ) for channel,channeltype in self.matches[start:start+25]
    ]

  @disnake.ui.select()
  async def channel_selector(self, _:disnake.ui.Select, inter:disnake.MessageInteraction):
    """ Update the message to preview the selected target """
    if inter.user != self.origin.author:
      await inter.response.send_message(self.parent.bot.babel(inter, 'error', 'wronguser'))
      return
    self.send_button.disabled = False
    try:
      self.selection = await self.parent.bot.fetch_channel(int(inter.values[0]))
    except disnake.Forbidden:
      self.send_button.disabled = True
      await inter.response.edit_message(
        content=self.parent.babel(inter, 'missingchannelerr')+' (select)',
        view=self
      )
      return
    guildchannels = get_guildchannels(self.parent.config, self.selection.guild.id)
    vetting = findvettingchannel(guildchannels)
    channeltype = guildchannels[self.selection.id]
    await inter.response.edit_message(
      content=self.parent.babel(
        inter, 'channelprompted', channel=self.selection.mention,
        vetting=vetting and 'feedback' not in channeltype.name
      ),
      view=self)

  @disnake.ui.button(disabled=True, style=disnake.ButtonStyle.primary)
  async def send_button(self, _:disnake.Button, inter:disnake.MessageInteraction):
    """ Send the confession """
    if isinstance(self.origin, disnake.Interaction):
      raise Exception("This function is not designed for Interactions!")
    if self.parent.__cog_name__ != 'Confessions':
      raise Exception("Confessions cannot be sent unless the parent is Confessions!")

    if self.selection is None:
      self.disable(inter)
      return

    anonid = self.parent.get_anonid(self.selection.guild.id, inter.author.id)
    guildchannels = get_guildchannels(self.parent.config, self.selection.guild.id)
    channeltype = guildchannels.get(self.selection.id)

    result = self.parent.check_all(
      self.selection.guild.id,
      self.selection.id,
      anonid,
      self.origin.content,
      self.origin.attachments[0] if self.origin.attachments else None,
      None
    )
    if result:
      await inter.send(self.parent.babel(inter, result[0], **result[1]))
      await self.disable(inter)
      return

    pendingconfession = ConfessionData(
      self.parent, author=inter.author, targetchannel=self.selection
    )

    if self.origin.attachments:
      await inter.response.defer(ephemeral=True)
      await pendingconfession.download_image(self.origin.attachments[0].url)

    vetting = findvettingchannel(guildchannels)
    await pendingconfession.generate_embed(anonid, vetting or channeltype.anonid, self.origin.content)

    if vetting and 'feedback' not in channeltype.name:
      await self.parent.bot.cogs['ConfessionsModeration'].send_vetting(
        inter, pendingconfession, self.selection.guild.get_channel(vetting)
      )
      await self.disable(inter)
      return

    await pendingconfession.send_confession(inter)

    self.send_button.label = self.parent.babel(inter, 'channelprompt_button_sent')
    self.channel_selector.disabled = True
    self.send_button.disabled = True
    self.done = True
    await inter.edit_original_message(
      content=self.parent.babel(
        inter, 'confession_sent_channel', channel=self.selection.mention
      ),
      view=self
    )

  def change_page(self, pagediff:int):
    """ Add or remove pagediff to self.page and trigger on_page_change event """
    async def action(inter):
      self.page += pagediff
      await self.on_page_change(inter)
    return action

  async def on_page_change(self, inter:disnake.MessageInteraction):
    """ Update view based on current page number """
    if self.page <= 0:
      self.page = 0
      self.page_decrement_button.disabled = True
    else:
      self.page_decrement_button.disabled = False

    if self.page >= len(self.matches) // 25:
      self.page = len(self.matches) // 25
      self.page_increment_button.disabled = True
    else:
      self.page_increment_button.disabled = False

    self.send_button.disabled = True

    self.update_list()

    await inter.response.edit_message(
      content=(
        self.parent.babel(inter, 'channelprompt') + ' ' +
        self.parent.babel(inter, 'channelprompt_pager', page=self.page + 1)
      ),
      view=self
    )

  async def disable(self, inter:disnake.MessageInteraction):
    """ Prevent further input """

    self.channel_selector.disabled = True
    self.send_button.disabled = True
    self.done = True
    await inter.message.edit(view=self)

  async def on_timeout(self):
    if isinstance(self.origin, disnake.Interaction):
      raise Exception("This function is not designed for Interactions!")
    try:
      if not self.done:
        await self.origin.reply(
          self.parent.babel(self.origin.author, 'timeouterror')
        )
      async for msg in self.origin.channel.history(after=self.origin):
        if (
          isinstance(msg.reference, disnake.MessageReference) and
          msg.reference.message_id == self.origin.id
        ):
          await msg.delete()
          return
    except disnake.HTTPException:
      pass

# Data classes


class Crypto:
  """ Handles encryption and decryption of sensitive data """
  _key = None

  @property
  def key(self) -> str:
    """ Key getter """
    return self._key

  @key.setter
  def key(self, value:str):
    """ Key setter """
    self._key = base64.decodebytes(bytes(value, encoding='ascii'))

  def setup(self, nonce:bytes = b'\xae[Et\xcd\n\x01\xf4\x95\x9c|No\x03\x81\x98'):
    """ Initializes the AES-256 scheme """
    backend = default_backend()
    cipher = Cipher(algorithms.AES(self._key), modes.CTR(nonce), backend=backend)
    return (cipher.encryptor(), cipher.decryptor())

  def keygen(self, length:int = 32) -> str:
    """ Generates a key for storage """
    return base64.encodebytes(os.urandom(length)).decode('ascii')

  def encrypt(self, data:bytes) -> bytes:
    """ Encodes data and returns a base64 string ready for storage """
    encryptor, _ = self.setup()
    encrypted = encryptor.update(data) + encryptor.finalize()
    encodedata = base64.b64encode(encrypted)
    return encodedata

  def decrypt(self, data:str) -> bytes:
    """ Read encoded data and return the raw bytes that created it """
    _, decryptor = self.setup()
    encrypted = base64.b64decode(data)
    rawdata = decryptor.update(encrypted) + decryptor.finalize()
    return rawdata


class ConfessionData:
  """ Dataclass for Confessions """
  SCOPE = 'confessions' # exists to keep babel happy
  anonid:str | None

  def __init__(
    self,
    parent:Union["Confessions", "ConfessionsModeration"],
    rawdata:Optional[str] = None,
    *,
    author:Optional[disnake.User] = None,
    targetchannel:Optional[disnake.TextChannel] = None,
    embed:Optional[disnake.Embed] = None,
    reference:Optional[disnake.Message] = None
  ):

    if rawdata:
      self.offline = True

      binary = parent.crypto.decrypt(rawdata)
      if len(binary) == 24: # TODO: Legacy format, remove eventually
        self.author_id = int.from_bytes(binary[0:8], 'big')
        self.targetchannel_id = int.from_bytes(binary[16:24], 'big')
        self.marketplace_button = False
        self.reference_id = 0
      elif len(binary) == 25:
        self.author_id = int.from_bytes(binary[0:8], 'big')
        self.targetchannel_id = int.from_bytes(binary[8:16], 'big')
        # from_bytes won't take a single byte, so this hack is needed.
        self.marketplace_button = bool.from_bytes(bytes((binary[16],)), 'big')
        self.reference_id = int.from_bytes(binary[17:25], 'big')
      else:
        raise CorruptConfessionDataException()
    else:
      self.offline = False
      self.author = author
      self.author_id = author.id
      self.targetchannel = targetchannel
      self.targetchannel_id = targetchannel.id
      self.marketplace_button = False
      self.reference_id = reference.id if reference else 0

    self.parent = parent
    self.embed = embed
    self.attachment = None
    self.image_url = None

    if embed and embed.description:
      # TODO: Legacy feature for older confessions, delete someday
      if embed.description.startswith('**[Anon-'):
        self.content = embed.description[20:]
      else:
        self.content = embed.description
      self.image_url = embed.image.url if embed.image else None

  def store(self) -> str:
    """ Encrypt data for secure storage """
    # Size limit: ~100 bytes
    if self.offline:
      bauthor = self.author_id.to_bytes(8, 'big')
      btarget = self.targetchannel_id.to_bytes(8, 'big')
    else:
      bauthor = self.author.id.to_bytes(8, 'big')
      btarget = self.targetchannel.id.to_bytes(8, 'big')
    bmarket = self.marketplace_button.to_bytes(1, 'big')
    breference = self.reference_id.to_bytes(8, 'big')

    binary = bauthor + btarget + bmarket + breference
    return self.parent.crypto.encrypt(binary).decode('ascii')

  async def fetch(self):
    """ Fetches referenced Discord elements for use """
    if self.offline:
      self.author = await self.parent.bot.fetch_user(self.author_id)
      self.targetchannel = await self.parent.bot.fetch_channel(self.targetchannel_id)
      self.offline = False

  async def download_image(self, image:str):
    async with aiohttp.ClientSession() as session:
      async with session.get(image) as res:
        if res.status == 200:
          filename = 'file.'+res.content_type.replace('image/','')
          self.attachment = disnake.File(
            io.BytesIO(await res.read()),
            filename
          )
        else:
          raise Exception("Failed to download image!")

  async def generate_embed(self, anonid:str, lead:bool, content:str):
    """ Generate the confession embed """
    if lead:
      self.anonid = anonid
      embed = disnake.Embed(colour=disnake.Colour(int(anonid,16)), description=content)
      embed.set_author(name=f'Anon-{anonid}')
    else:
      self.anonid = None
      embed = disnake.Embed(description=content if content else '')
    if self.attachment:
      embed.set_image(url='attachment://'+self.attachment.filename)
    elif self.image_url:
      embed.set_image(url=self.image_url)
    self.embed = embed
    self.content = content

  async def handle_send_errors(self, ctx:Union[disnake.DMChannel, disnake.Interaction], func):
    """
    Wraps around functions that send confessions to channels
    Adds copious amounts of error handling
    """
    kwargs = {'ephemeral':True} if isinstance(ctx, disnake.Interaction) else {}
    try:
      await func
      return True
    except disnake.Forbidden:
      try:
        await self.targetchannel.send(
          self.parent.babel(self.targetchannel.guild, 'missingperms', perm='Embed Links')
        )
        await ctx.send(self.parent.babel(ctx, 'embederr'), **kwargs)
      except disnake.Forbidden:
        await ctx.send(
          self.parent.babel(ctx, 'missingchannelerr') + ' (403 Forbidden)',
          **kwargs
        )
    except disnake.NotFound:
      await ctx.send(
        self.parent.babel(ctx, 'missingchannelerr') + ' (404 Not Found)',
        **kwargs
      )
    return False

  async def send_confession(self, ctx:disnake.DMChannel | disnake.Interaction, smsg=False):
    """ Send confession to the destination channel """
    preface = self.parent.config.get(f'{self.targetchannel.guild.id}_preface', fallback='')
    kwargs = {}
    if self.attachment:
      kwargs['file'] = self.attachment
    if self.marketplace_button:
      kwargs['components'] = [disnake.ui.Button(
        label=self.parent.babel(ctx.guild, 'button_offer', listing=None),
        custom_id='confessionmarketplace_offer',
        emoji='💵',
        style=disnake.ButtonStyle.blurple
      )]
    if self.reference_id:
      kwargs['reference'] = disnake.MessageReference(
        message_id=self.reference_id,
        channel_id=self.targetchannel.id,
        guild_id=self.targetchannel.guild.id
      )

    if self.parent.config.get(f'{self.targetchannel.guild.id}_webhook', None) == 'True':
      if webhook := await self.find_or_create_webhook(self.targetchannel):
        botcolour = self.parent.bot.config['main']['themecolor'][2:]
        username = (
          (preface + ' - ' if preface else '') +
          ('[Anon]' if self.anonid is None else '[Anon-' + self.anonid + ']')
        )
        pfp = (
          self.parent.config.get('pfpgen_url', '')
          .replace('{}', botcolour if self.anonid is None else self.anonid)
        )
        func = webhook.send(self.content, username=username, avatar_url=pfp, **kwargs)
        #TODO: add support for custom PFPs
      else:
        return
    else:
      func = self.targetchannel.send(preface, embed=self.embed, **kwargs)

    if hasattr(ctx, 'response') and not ctx.response.is_done():
      await ctx.response.defer(ephemeral=True)
    success = await self.handle_send_errors(ctx, func)

    if success and smsg:
      #BABEL: confession_sent_below,confession_sent_channel
      await ctx.send(
        self.parent.babel(ctx, (
          'confession_sent_below' if ctx.channel == self.targetchannel else 'confession_sent_channel'
        ), channel=self.targetchannel.mention),
        ephemeral=True
      )

  async def find_or_create_webhook(self, channel:disnake.TextChannel) -> disnake.Webhook | None:
    """ Tries to find a webhook, or create it, or complain about missing permissions """
    webhook:disnake.Webhook
    try:
      for webhook in await channel.webhooks():
        if webhook.application_id == self.parent.bot.application_id:
          return webhook
      return await channel.create_webhook(name=self.parent.bot.config['main']['botname'])
    except disnake.Forbidden:
      await channel.send(self.parent.babel(channel.guild, 'missingperms', perm='Manage Webhooks'))
      return None


def setup(_):
  """ Refuse to bind this cog to the bot """
  raise Exception("This module is not meant to be imported as an extension!")

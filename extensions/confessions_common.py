"""
  Confessions Common - Classes shared by multiple confessions submodules
  Note: Do not enable as an extension, code in here is used implicitly
  To reload, reload each of the enabled confessions modules
"""
from __future__ import annotations

import io, os, base64, hashlib, re
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from typing import Optional, Union, TYPE_CHECKING
from collections import OrderedDict
import discord
from discord.ext import commands
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
  """ Anonymous channel types and their properties """
  name:str
  value:int
  icon:str
  anonid:bool
  vetted:bool
  dep:str
  swap:ChannelType | None = None

  _lookup:dict[int, ChannelType]

  unset:ChannelType
  untraceable:ChannelType
  traceable:ChannelType
  vetting:ChannelType
  feedback:ChannelType
  untraceablefeedback:ChannelType
  marketplace:ChannelType

  NAMES = None
  ICONS = None
  ANONIDS = None
  VETTED = None
  DEPS = None

  def __init__(self, name:str, value:int, icon:str, anonid:bool, vetted:bool, dep:str | None = None):
    """
      Create a Confessions Channel Type

      Parameters
      ----------
      name: The internal name of a channeltype, before babel
      value: The number a channeltype is stored as internally
      icon: The emoji that represents a channeltype
      anonid: If anonids are shown in this channeltype
      vetted: If messages headed to this channel can be intercepted by vetting channels
      dep: Any modules that must be loaded in order for this channeltype to work
    """
    self.name = name
    self.value = value
    self.icon = icon
    self.anonid = anonid
    self.vetted = vetted
    self.dep = dep

    ChannelType._lookup[value] = self

  @classmethod
  def walk(cls) -> tuple[ChannelType]:
    return (c for c in cls._lookup.values())

  @classmethod
  def from_value(cls, i) -> ChannelType:
    return cls._lookup[int(i)]

  def __int__(self):
    return self.value

  def __eq__(self, other):
    return isinstance(other, ChannelType) and other.value == self.value

  def localname(self, babel:Babel, target:Resolvable, long:bool = True) -> str:
    """ Find name of the current ChannelType in Babel """
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
    if long and self.swap:
      if self.anonid:
        ext = babel(target, 'confessions', 'channeltype_traceable')
      else:
        ext = babel(target, 'confessions', 'channeltype_untraceable')
    return name + (' ' + ext if ext else '')


# Declare all possible channeltypes
ChannelType._lookup = {}

ChannelType.unset = ChannelType('unset', -1, '❓', False, False)

ChannelType.untraceable = ChannelType('untraceable', 0, '👻', False, True)
ChannelType.traceable = ChannelType('traceable', 1, '💬', True, True)
ChannelType.untraceable.swap = ChannelType.traceable
ChannelType.traceable.swap = ChannelType.untraceable

ChannelType.vetting = ChannelType('vetting', 2, '🧑‍⚖️', True, False, 'ConfessionsModeration')

ChannelType.feedback = ChannelType('feedback', 3, '📢', True, False)
ChannelType.untraceablefeedback = ChannelType('untraceablefeedback', 4, '💨', False, False)
ChannelType.feedback.swap = ChannelType.untraceablefeedback
ChannelType.untraceablefeedback.swap = ChannelType.feedback

ChannelType.marketplace = ChannelType('marketplace', 5, '🛒', True, True, 'ConfessionsMarketplace')


# Utility functions

def get_channeltypes(cogs:Mapping[str, commands.Cog]) -> list[ChannelType]:
  """ Provide a selection of ChannelTypes based on the currently active modules """
  return [c for c in ChannelType.walk() if c.dep is None or c.dep in cogs]


def findvettingchannel(guildchannels:dict[int, ChannelType]) -> Optional[int]:
  """ Check if guild has a vetting channel and return it """
  for channel_id in guildchannels:
    if guildchannels[channel_id] == ChannelType.vetting:
      return channel_id
  return None


def get_guildchannels(config:SectionProxy, guild_id:int) -> dict[int, ChannelType]:
  """ Returns a dictionary of {channel_id: channel_type} for the provided guild """
  return {int(k):ChannelType.from_value(v) for k,v in (
    e.split('=') for e in config.get(f'{guild_id}_channels', fallback='').split(',') if e
  )}


def set_guildchannels(config:SectionProxy, guild_id:int, guildchannels:dict[int, ChannelType] | None):
  """ Writes a dictionary of {channel_id: channel_type} to the config """
  if guildchannels:
    config[f'{guild_id}_channels'] = ','.join(f'{k}={int(v)}' for k,v in guildchannels.items())
  else:
    config.pop(f'{guild_id}_channels')


async def safe_fetch_channel(
  parent:Confessions | ConfessionsModeration,
  inter:discord.Interaction,
  channel_id:int
) -> Optional[discord.TextChannel]:
  """ Gracefully handles whenever a confession target isn't available """
  try:
    return await parent.bot.fetch_channel(channel_id)
  except discord.Forbidden:
    await inter.response.send_message(
      parent.babel(inter, 'missingchannelerr') + ' (fetch)',
      ephemeral=True
    )
    return None


# Exceptions

class CorruptConfessionDataException(Exception):
  """ Thrown when decrypted ConfessionData doesn't fit the required format """


class NoMemberCacheError(Exception):
  """ Unable to continue without a member cache """


# Views

class ChannelSelectView(discord.ui.View):
  """ View for selecting a target interactively """
  page: int = 0
  selection: Optional[discord.TextChannel] = None
  done: bool = False

  def __init__(
      self,
      origin:discord.Message | discord.Interaction,
      parent:Confessions | ConfessionsSetup,
      matches:list[tuple[discord.TextChannel, ChannelType]],
      confession:ConfessionData | None = None
    ):
    super().__init__()
    self.origin = origin
    self.parent = parent
    self.matches = matches
    self.selection = matches[0][0]
    self.confession = confession
    self.soleguild = matches[0][0].guild if all((m.guild for m,_ in matches)) else None
    self.update_list()
    self.channel_selector.placeholder = self.parent.babel(origin, 'channelprompt_placeholder')
    self.send_button.label = self.parent.babel(origin, 'channelprompt_button_send')

    if len(matches) > 25:
      # Add pagination only when needed
      self.page_decrement_button = discord.ui.Button(
        disabled=True,
        style=discord.ButtonStyle.secondary,
        label=self.parent.babel(origin, 'channelprompt_button_prev')
      )
      self.page_decrement_button.callback = self.change_page(-1)
      self.add_item(self.page_decrement_button)

      self.page_increment_button = discord.ui.Button(
        disabled=False,
        style=discord.ButtonStyle.secondary,
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
      discord.SelectOption(
        label='#' + channel.name + ('' if self.soleguild else f' (from {channel.guild.name})'),
        value=channel.id,
        emoji=channeltype.icon,
        default=channel.id == self.selection.id if self.selection else False
      ) for channel,channeltype in self.matches[start:start+25]
    ]

  @discord.ui.select()
  async def channel_selector(self, inter:discord.Interaction, this:discord.ui.Select):
    """ Update the message to preview the selected target """
    originuser = (self.origin.author if isinstance(self.origin,discord.Message) else self.origin.user)
    if inter.user != originuser:
      await inter.response.send_message(self.parent.bot.babel(inter, 'error', 'wronguser'))
      return
    self.send_button.disabled = False
    self.selection = self.parent.bot.get_channel(int(this.values[0]))
    self.update_list()
    guildchannels = get_guildchannels(self.parent.config, self.selection.guild.id)
    vetting = findvettingchannel(guildchannels)
    channeltype = guildchannels[self.selection.id]
    await inter.response.edit_message(
      content=self.parent.babel(
        inter, 'channelprompted', channel=self.selection.mention,
        vetting=vetting and 'feedback' not in channeltype.name
      ),
      view=self)

  @discord.ui.button(disabled=False, style=discord.ButtonStyle.primary, emoji='📨')
  async def send_button(self, inter:discord.Interaction, _:discord.Button):
    """ Send the confession """
    if self.selection is None or self.done:
      self.disable(inter)
      return

    if self.confession is None:
      self.confession = ConfessionData(self.parent)
      self.confession.create(author=inter.user, targetchannel=self.selection)
      self.confession.set_content(self.origin.content)

      if self.origin.attachments:
        await inter.response.defer(ephemeral=True)
        await self.confession.add_image(attachment=self.origin.attachments[0])
    else:
      # Override targetchannel as this has changed
      self.confession.create(targetchannel=self.selection)

    if vetting := await self.confession.check_vetting(inter):
      await self.parent.bot.cogs['ConfessionsModeration'].send_vetting(
        inter, self.confession, vetting
      )
      await inter.delete_original_response()
      return
    if vetting is False:
      return

    if await self.confession.send_confession(inter):
      self.send_button.label = self.parent.babel(inter, 'channelprompt_button_sent')
      self.channel_selector.disabled = True
      self.send_button.disabled = True
      self.done = True
      await inter.edit_original_response(
        content=self.parent.babel(
          inter, 'confession_sent_channel', channel=self.selection.mention
        ),
        view=None
      )

  def change_page(self, pagediff:int):
    """ Add or remove pagediff to self.page and trigger on_page_change event """
    async def action(inter):
      self.page += pagediff
      await self.on_page_change(inter)
    return action

  async def on_page_change(self, inter:discord.Interaction):
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

  async def disable(self, inter:discord.Interaction):
    """ Prevent further input """

    self.channel_selector.disabled = True
    self.send_button.disabled = True
    self.done = True
    if inter.response.is_done():
      await inter.message.edit(view=self)
    else:
      await inter.response.edit_message(view=self)

  async def on_timeout(self):
    originuser = (self.origin.author if isinstance(self.origin,discord.Message) else self.origin.user)
    try:
      if isinstance(self.origin, discord.Interaction):
        if not self.done:
          for component in self.children:
            if isinstance(component, (discord.ui.Button, discord.ui.Select)):
              component.disabled = True
          await self.origin.edit_original_response(
            content=self.parent.babel(self.origin.user, 'timeouterror'),
            view=self
          )
        else:
          await self.origin.delete_original_response()
        return
      if not self.done:
        await self.origin.reply(self.parent.babel(originuser, 'timeouterror'))
      async for msg in self.origin.channel.history(after=self.origin):
        if (
          isinstance(msg.reference, discord.MessageReference) and
          msg.reference.message_id == self.origin.id
        ):
          await msg.delete()
          return
    except discord.HTTPException:
      pass # Message was probably dismissed, don't worry about it


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


referenced_message_cache:OrderedDict[int, discord.Message] = {}


class ConfessionData:
  """ Dataclass for Confessions """
  SCOPE = 'confessions' # exists to keep babel happy
  anonid:str | None
  author:discord.User
  targetchannel:discord.TextChannel
  channeltype_flags:int = 0
  content:str | None = None
  reference:discord.Message | discord.PartialMessage | None = None
  attachment:discord.Attachment | None = None
  file:discord.File | None = None
  embed:discord.Embed | None = None
  channeltype:ChannelType

  def __init__(self, parent:Union[Confessions, ConfessionsModeration]):
    """ Creates a ConfessionData class, from here, either use from_binary() or create() """
    # Aliases to shorten code
    self.parent = parent
    self.config = parent.config
    self.babel = parent.babel
    self.bot = parent.bot

  # Data retreival

  async def from_binary(self, crypto:Crypto, rawdata:str):
    """ Creates ConfessionData from an encrypted binary string """
    binary = crypto.decrypt(rawdata)
    if len(binary) == 24: # TODO: Legacy format, remove eventually
      author_id = int.from_bytes(binary[0:8], 'big')
      targetchannel_id = int.from_bytes(binary[16:24], 'big')
    elif len(binary) == 25:
      author_id = int.from_bytes(binary[0:8], 'big')
      targetchannel_id = int.from_bytes(binary[8:16], 'big')
      # from_bytes won't take a single byte, so this hack is needed.
      self.channeltype_flags = int.from_bytes(bytes((binary[16],)), 'big')
      reference_id = int.from_bytes(binary[17:25], 'big')
    else:
      raise CorruptConfessionDataException()
    self.author = await self.bot.fetch_user(author_id)
    self.targetchannel = await self.bot.fetch_channel(targetchannel_id)
    self.anonid = self.get_anonid(self.targetchannel.guild.id, self.author.id)
    guildchannels = get_guildchannels(self.config, self.targetchannel.guild.id)
    self.channeltype = guildchannels.get(self.targetchannel.id, ChannelType.unset)
    # References must exist in the cache, meaning confession replies will not survive a restart
    # Note: this assumes the data will only be retreived once
    self.reference = referenced_message_cache.pop(reference_id, None)

  def create(
    self,
    *,
    author:discord.User | None = None,
    targetchannel:discord.TextChannel | None = None,
    reference:discord.Message | None = None
  ):
    if author:
      self.author = author
    if targetchannel:
      self.targetchannel = targetchannel
      self.anonid = self.get_anonid(targetchannel.guild.id, self.author.id)
      guildchannels = get_guildchannels(self.config, targetchannel.guild.id)
      self.channeltype = guildchannels.get(targetchannel.id, ChannelType.unset)
    if reference:
      self.reference = reference

  def set_content(self, content:Optional[str] = '', *, embed:Optional[discord.Embed] = None):
    self.content = content
    if embed:
      self.embed = embed
      if embed.description:
        if not content:
          self.content = embed.description
        # TODO: Legacy feature for older confessions, delete someday
        if embed.description.startswith('**[Anon-'):
          self.content = embed.description[20:]
        else:
          self.content = embed.description

  async def add_image(self, *, attachment:discord.Attachment | None = None, url:str | None = None):
    """ Download image so it can be reuploaded with message """
    async with aiohttp.ClientSession() as session:
      async with session.get(attachment.url if attachment else url) as res:
        if res.status == 200:
          filename = 'file.'+res.content_type.replace('image/','')
          self.file = discord.File(
            io.BytesIO(await res.read()),
            filename
          )
          if self.embed:
            self.embed.set_image(url='attachment://'+self.file.filename)
          if attachment:
            self.attachment = attachment
        else:
          raise Exception("Failed to download image!")

  # Data storage

  def store(self) -> str:
    """ Encrypt data for secure storage """
    # Size limit: ~100 bytes
    bauthor = self.author.id.to_bytes(8, 'big')
    btarget = self.targetchannel.id.to_bytes(8, 'big')
    bmarket = self.channeltype_flags.to_bytes(1, 'big')
    if self.reference:
      breference = self.reference.id.to_bytes(8, 'big')
      # Store in cache so it can be restored
      referenced_message_cache[self.reference.id] = self.reference
      # Prevent a memory leak
      if len(referenced_message_cache) > 100:
        # Chances are older items in this list are not going to be approved or denied
        # It's also possible the vet message is deleted
        referenced_message_cache.popitem(last=False)
    else:
      breference = int(0).to_bytes(8, 'big')

    binary = bauthor + btarget + bmarket + breference
    return self.parent.crypto.encrypt(binary).decode('ascii')

  # Data rehydration

  def get_anonid(self, guildid:int, userid:int) -> str:
    """ Calculates the current anon-id for a user """
    offset = int(self.config.get(f"{guildid}_shuffle", fallback=0))
    encrypted = self.parent.crypto.encrypt(
      guildid.to_bytes(8, 'big') + userid.to_bytes(8, 'big') + offset.to_bytes(2, 'big')
    )
    return hashlib.sha256(encrypted).hexdigest()[-6:]

  def generate_embed(self):
    """ Generate or add anonid to the confession embed """
    if self.embed is None:
      self.embed = discord.Embed(description=self.content)
    if self.channeltype.anonid:
      self.embed.colour = discord.Colour(int(self.anonid,16))
      self.embed.set_author(name=f'Anon-{self.anonid}')
    else:
      self.embed.set_author(name='[Anon]')
    if self.file:
      self.embed.set_image(url='attachment://'+self.file.filename)

  # Checks

  def check_banned(self) -> bool:
    """ Verify the user hasn't been banned """
    guild_id = self.targetchannel.guild.id
    if self.anonid in self.config.get(f"{guild_id}_banned", fallback='').split(','):
      return False
    return True

  def check_image(self) -> bool:
    """ Only allow images to be sent if imagesupport is enabled and the image is valid """
    image = self.attachment
    guild_id = self.targetchannel.guild.id
    if image and image.content_type.startswith('image') and image.size < 25_000_000:
      # Discord size limit
      if bool(self.config.get(f"{guild_id}_imagesupport", fallback=True)):
        return True
      return False
    raise commands.BadArgument()

  def check_spam(self):
    """ Verify message doesn't contain spam as defined in [confessions] spam_flags """
    for spamflag in self.config.get('spam_flags', fallback=None).splitlines():
      if self.content and re.match(spamflag, self.content):
        return False
    return True

  async def check_vetting(
    self,
    inter:discord.Interaction,
  ) -> discord.TextChannel | bool | None:
    """ Check if vetting is required, this is not a part of check_all """
    send = (inter.followup.send if inter.response.is_done() else inter.response.send_message)
    guildchannels = get_guildchannels(self.config, self.targetchannel.guild.id)
    vetting = findvettingchannel(guildchannels)
    if vetting and self.channeltype.vetted:
      if 'ConfessionsModeration' not in self.bot.cogs:
        await send(self.babel(inter, 'no_moderation'), ephemeral=True)
        return False
      return self.targetchannel.guild.get_channel(vetting)
    return None

  async def check_all(self, inter:discord.Interaction) -> bool:
    """
      Run all pre-send checks on this confession
      In the event that a check fails, return the relevant babel key
    """
    send = (inter.followup.send if inter.response.is_done() else inter.response.send_message)
    kwargs = {'ephemeral':True}

    if (
      self.channeltype in get_channeltypes(self.bot.cogs) and self.channeltype != ChannelType.unset
    ):
      if self.channeltype == ChannelType.marketplace and self.embed is None:
        await send(self.babel(
          inter, 'wrongcommand', cmd='sell', channel=self.targetchannel.mention
        ), **kwargs)
        return False
    else:
      await send(self.babel(inter, 'nosendchannel'), **kwargs)
      return False

    if not self.check_banned():
      await send(self.babel(inter, 'nosendbanned'), **kwargs)
      return False

    if self.attachment:
      try:
        if not self.check_image():
          await send(self.babel(inter, 'nosendimages'), **kwargs)
          return False
      except commands.BadArgument:
        await send(self.babel(inter, 'invalidimage'), **kwargs)
        return False

    if not self.check_spam():
      await send(self.babel(inter, 'nospam'), **kwargs)
      return False

    return True

  # Sending

  async def handle_send_errors(self, inter:discord.Interaction, func):
    """
    Wraps around functions that send confessions to channels
    Adds copious amounts of error handling
    """
    send = (inter.followup.send if inter.response.is_done() else inter.response.send_message)
    kwargs = {'ephemeral':True}
    try:
      await func
      return True
    except discord.Forbidden:
      try:
        await self.targetchannel.send(
          self.babel(self.targetchannel.guild, 'missingperms', perm='Embed Links')
        )
        await send(self.babel(inter, 'embederr'), **kwargs)
      except discord.Forbidden:
        await send(self.babel(inter, 'missingchannelerr') + ' (403 Forbidden)', **kwargs)
    except discord.NotFound:
      await send(self.babel(inter, 'missingchannelerr') + ' (404 Not Found)', **kwargs)
    return False

  async def send_confession(
    self,
    inter:discord.Interaction,
    success_message:bool = False,
    perform_checks:bool = True,
    *,
    channel:discord.TextChannel | None = None,
    webhook_override:bool | None = None,
    preface_override:str | None = None,
    **kwargs
  ) -> bool:
    """ Send confession to the destination channel """
    # Defer now in case it takes a while
    if not inter.response.is_done():
      await inter.response.defer(ephemeral=True)

    # Flag-based behaviour
    if channel is None:
      channel = self.targetchannel
    # Update channeltype, in case this channel is different
    guildchannels = get_guildchannels(self.config, channel.guild.id)
    self.channeltype = guildchannels.get(channel.id, ChannelType.unset)
    if perform_checks:
      if not await self.check_all(inter):
        return False
    preface = (
      preface_override if preface_override is not None
      else self.config.get(f'{channel.guild.id}_preface', fallback='')
    )
    use_webhook = (
      webhook_override if webhook_override is not None
      else self.config.getboolean(f'{channel.guild.id}_webhook', False)
    )

    # Allow external modules to modify the message before sending
    if channel == self.targetchannel:
      # ...as long as it's not being intercepted by another mechanism - like vetting
      if dep := self.channeltype.dep:
        if dep not in self.bot.cogs:
          await inter.followup.send(self.babel(inter, 'vet_error_module', module=dep), ephemeral=True)
          return False
        special_function = getattr(self.bot.cogs[dep], 'on_channeltype_send', None)
        if callable(special_function):
          result = await special_function(inter, self)
          if result is False:
            return False
          if 'use_webhook' in result:
            use_webhook = result['use_webhook']
          if 'view' in result:
            kwargs['view'] = result['view']

    # Create kwargs based on state
    if self.file:
      kwargs['file'] = self.file
    if self.reference:
      # A best effort to always show replies, even if Discord's API doesn't allow for it
      # Discord does not allow webhooks to reply, disable it
      use_webhook = False
      if self.reference.channel == channel:
        kwargs['reference'] = discord.MessageReference(
          message_id=self.reference.id, channel_id=channel.id, fail_if_not_exists=False
        )
      else:
        # Discord does not allow replies to span multiple channels, reference in plaintext instead
        preface += '\n' + self.babel(channel.guild, 'reply_to', reference=self.reference.jump_url)

    # Send the confession
    if use_webhook:
      if webhook := await self.find_or_create_webhook(channel):
        botcolour = self.bot.config['main']['themecolor'][2:]
        username = (
          (preface + ' - ' if preface else '') +
          (f'[Anon-{self.anonid}]' if self.channeltype.anonid else '[Anon]')
        )
        pfp = (
          self.config.get('pfpgen_url', '')
          .replace('{}', self.anonid if self.channeltype.anonid else botcolour)
        )
        func = webhook.send(self.content, username=username, avatar_url=pfp, **kwargs)
        #TODO: add support for custom PFPs
      else:
        return False
    else:
      self.generate_embed()
      func = channel.send(preface, embed=self.embed, **kwargs)
    success = await self.handle_send_errors(inter, func)

    if 'Log' in self.bot.cogs and channel == self.targetchannel:
      logentry = (
        f'{inter.guild.name}/{self.anonid}: {self.bot.utilities.truncate(self.content)}' +
        (' (attachment)' if self.file else '')
      )
      await self.bot.cogs['Log'].log_misc_str(content=logentry)

    # Mark the command as complete by sending a success message
    if success and success_message:
      if inter.channel != self.targetchannel: # confess-to
        await inter.followup.send(
          self.babel(inter, 'confession_sent_channel', channel=channel.mention),
          ephemeral=True
        )
      else: # confess
        await inter.followup.send(self.babel(inter, 'confession_sent_below'), ephemeral=True)
    return success

  async def find_or_create_webhook(self, channel:discord.TextChannel) -> discord.Webhook | None:
    """ Tries to find a webhook, or create it, or complain about missing permissions """
    webhook:discord.Webhook
    try:
      for webhook in await channel.webhooks():
        if webhook.user == self.bot.user:
          return webhook
      return await channel.create_webhook(name=self.bot.config['main']['botname'])
    except discord.Forbidden:
      await channel.send(self.babel(channel.guild, 'missingperms', perm='Manage Webhooks'))
      return None


async def setup(_):
  """ Refuse to bind this cog to the bot """
  raise Exception("This module is not meant to be imported as an extension!")

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
import disnake
from disnake.ext import commands
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
  vetted:bool

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

  VETTED = {
    -1: False,
    0: True,
    1: True,
    2: True,
    3: False,
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
    self.vetted = self.VETTED[i]

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
      matches:list[tuple[disnake.TextChannel, ChannelType]],
      confession:ConfessionData | None = None
    ):
    super().__init__()
    self.origin = origin
    self.parent = parent
    self.matches = matches
    self.confession = confession
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
        emoji=channeltype.icon,
        default=channel.id == self.selection.id if self.selection else False
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

  @disnake.ui.button(disabled=True, style=disnake.ButtonStyle.primary)
  async def send_button(self, _:disnake.Button, inter:disnake.MessageInteraction):
    """ Send the confession """
    if self.selection is None or self.done:
      self.disable(inter)
      return

    if self.confession is None:
      self.confession = ConfessionData(self.parent)
      self.confession.create(author=inter.author, targetchannel=self.selection)
      self.confession.set_content(self.origin.content)

      if self.origin.attachments:
        await inter.response.defer(ephemeral=True)
        await self.confession.add_image(attachment=self.origin.attachments[0])
    else:
      # Override targetchannel as this has changed
      self.confession.create(author=inter.author, targetchannel=self.selection)

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
      await inter.edit_original_message(
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
    if inter.response.is_done():
      await inter.message.edit(view=self)
    else:
      await inter.response.edit_message(view=self)

  async def on_timeout(self):
    try:
      if isinstance(self.origin, disnake.Interaction):
        if not self.done:
          for component in self.children:
            if isinstance(component, (disnake.ui.Button, disnake.ui.Select)):
              component.disabled = True
          await self.origin.edit_original_response(
            content=self.parent.babel(self.origin.author, 'timeouterror'),
            view=self
          )
        else:
          await self.origin.delete_original_response()
        return
      if not self.done:
        await self.origin.reply(self.parent.babel(self.origin.author, 'timeouterror'))
      async for msg in self.origin.channel.history(after=self.origin):
        if (
          isinstance(msg.reference, disnake.MessageReference) and
          msg.reference.message_id == self.origin.id
        ):
          await msg.delete()
          return
    except disnake.HTTPException:
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


class ConfessionData:
  """ Dataclass for Confessions """
  SCOPE = 'confessions' # exists to keep babel happy
  anonid:str | None
  author:disnake.User
  targetchannel:disnake.TextChannel
  channeltype_flags:int = 0
  content:str
  reference_id:int = 0
  attachment:disnake.Attachment | None = None
  file:disnake.File | None = None
  embed:disnake.Embed | None = None
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
      self.reference_id = int.from_bytes(binary[17:25], 'big')
    else:
      raise CorruptConfessionDataException()
    self.author = await self.bot.fetch_user(author_id)
    self.targetchannel = await self.bot.fetch_channel(targetchannel_id)
    self.anonid = self.get_anonid(self.targetchannel.guild.id, self.author.id)
    guildchannels = get_guildchannels(self.config, self.targetchannel.guild.id)
    self.channeltype = guildchannels.get(self.targetchannel.id, ChannelType.unset())

  def create(
    self,
    author:disnake.User,
    targetchannel:disnake.TextChannel,
    reference:Optional[disnake.Message] = None
  ):
    self.author = author
    self.targetchannel = targetchannel
    self.anonid = self.get_anonid(targetchannel.guild.id, self.author.id)
    guildchannels = get_guildchannels(self.config, self.targetchannel.guild.id)
    self.channeltype = guildchannels.get(self.targetchannel.id, ChannelType.unset())
    self.reference_id = reference.id if reference else 0

  def set_content(self, content:Optional[str] = '', *, embed:Optional[disnake.Embed] = None):
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

  async def add_image(self, *, attachment:disnake.Attachment | None = None, url:str | None = None):
    """ Download image so it can be reuploaded with message """
    async with aiohttp.ClientSession() as session:
      async with session.get(attachment.url if attachment else url) as res:
        if res.status == 200:
          filename = 'file.'+res.content_type.replace('image/','')
          self.file = disnake.File(
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
    breference = self.reference_id.to_bytes(8, 'big')

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

  def generate_embed(self, vetting:bool = False):
    """ Generate or add anonid to the confession embed """
    if self.embed is None:
      self.embed = disnake.Embed(description=self.content)
    if (self.channeltype.anonid or vetting):
      self.embed.colour = disnake.Colour(int(self.anonid,16))
      self.embed.set_author(name=f'Anon-{self.anonid}')
    else:
      self.anonid = None
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
    inter:disnake.Interaction,
  ) -> disnake.TextChannel | bool | None:
    """ Check if vetting is required, this is not a part of check_all """
    guildchannels = get_guildchannels(self.config, self.targetchannel.guild.id)
    vetting = findvettingchannel(guildchannels)
    if vetting and self.channeltype.vetted:
      if 'ConfessionsModeration' not in self.bot.cogs:
        await inter.send(self.babel(inter, 'no_moderation'), ephemeral=True)
        return False
      return self.targetchannel.guild.get_channel(vetting)
    return None

  async def check_all(self, inter:disnake.Interaction) -> bool:
    """
      Run all pre-send checks on this confession
      In the event that a check fails, return the relevant babel key
    """
    kwargs = {'ephemeral':True}

    if (
      self.channeltype in get_channeltypes(self.bot.cogs) and self.channeltype != ChannelType.unset()
    ):
      if self.channeltype == ChannelType.marketplace() and self.embed is None:
        await inter.send(self.babel(
          inter, 'wrongcommand', cmd='sell', channel=self.targetchannel.mention
        ), **kwargs)
        return False
    else:
      await inter.send(self.babel(inter, 'nosendchannel'), **kwargs)
      return False

    if not self.check_banned():
      await inter.send(self.babel(inter, 'nosendbanned'), **kwargs)
      return False

    if self.attachment:
      try:
        if not self.check_image():
          await inter.send(self.babel(inter, 'nosendimages'), **kwargs)
          return False
      except commands.BadArgument:
        await inter.send(self.babel(inter, 'invalidimage'), **kwargs)
        return False

    if not self.check_spam():
      await inter.send(self.babel(inter, 'nospam'), **kwargs)
      return False

    return True

  # Sending

  async def handle_send_errors(self, inter:disnake.Interaction, func):
    """
    Wraps around functions that send confessions to channels
    Adds copious amounts of error handling
    """
    kwargs = {'ephemeral':True}
    try:
      await func
      return True
    except disnake.Forbidden:
      try:
        await self.targetchannel.send(
          self.babel(self.targetchannel.guild, 'missingperms', perm='Embed Links')
        )
        await inter.send(self.babel(inter, 'embederr'), **kwargs)
      except disnake.Forbidden:
        await inter.send(self.babel(inter, 'missingchannelerr') + ' (403 Forbidden)', **kwargs)
    except disnake.NotFound:
      await inter.send(self.babel(inter, 'missingchannelerr') + ' (404 Not Found)', **kwargs)
    return False

  async def send_confession(
    self,
    inter:disnake.Interaction,
    success_message:bool = False,
    perform_checks:bool = True,
    *,
    channel:disnake.TextChannel | None = None,
    webhook_override:bool | None = None,
    preface_override:str | None = None,
    **kwargs
  ) -> bool:
    """ Send confession to the destination channel """

    # Flag-based behaviour
    if perform_checks:
      if not await self.check_all(inter):
        return False
    if channel is None:
      channel = self.targetchannel
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
      if dep := self.channeltype.DEPS[self.channeltype.value]:
        special_function = getattr(self.bot.cogs[dep], 'on_channeltype_send', None)
        if callable(special_function):
          result = await special_function(inter, self)
          if result is False:
            return False
          if 'use_webhook' in result:
            use_webhook = result['use_webhook']
          if 'components' in result:
            kwargs['components'] = result['components']

    # Create kwargs based on state
    if self.file:
      kwargs['file'] = self.file
    if self.reference_id and channel == self.targetchannel:
      use_webhook = False
      kwargs['reference'] = disnake.MessageReference(
        message_id=self.reference_id,
        channel_id=channel.id,
        guild_id=channel.guild.id
      )

    # Send the confession
    if use_webhook:
      if webhook := await self.find_or_create_webhook(channel):
        botcolour = self.bot.config['main']['themecolor'][2:]
        username = (
          (preface + ' - ' if preface else '') +
          ('[Anon]' if self.anonid is None else '[Anon-' + self.anonid + ']')
        )
        pfp = (
          self.config.get('pfpgen_url', '')
          .replace('{}', botcolour if self.anonid is None else self.anonid)
        )
        func = webhook.send(self.content, username=username, avatar_url=pfp, **kwargs)
        #TODO: add support for custom PFPs
      else:
        return False
    else:
      self.generate_embed()
      func = channel.send(preface, embed=self.embed, **kwargs)

    if hasattr(inter, 'response') and not inter.response.is_done():
      await inter.response.defer(ephemeral=True)
    success = await self.handle_send_errors(inter, func)

    # Mark the command as complete by sending a success message
    if success and success_message:
      if inter.channel != self.targetchannel: # confess-to
        await inter.send(
          self.babel(inter, 'confession_sent_channel', channel=channel.mention),
          ephemeral=True
        )
      else: # confess
        await inter.send(self.babel(inter, 'confession_sent_below'), ephemeral=True)
    return success

  async def find_or_create_webhook(self, channel:disnake.TextChannel) -> disnake.Webhook | None:
    """ Tries to find a webhook, or create it, or complain about missing permissions """
    webhook:disnake.Webhook
    try:
      for webhook in await channel.webhooks():
        if webhook.application_id == self.bot.application_id:
          return webhook
      return await channel.create_webhook(name=self.bot.config['main']['botname'])
    except disnake.Forbidden:
      await channel.send(self.babel(channel.guild, 'missingperms', perm='Manage Webhooks'))
      return None


def setup(_):
  """ Refuse to bind this cog to the bot """
  raise Exception("This module is not meant to be imported as an extension!")

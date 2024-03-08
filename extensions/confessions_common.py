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
from enum import Enum
import disnake
import aiohttp

if TYPE_CHECKING:
  from overlay.extensions.confessions import Confessions
  from overlay.extensions.confessions_moderation import ConfessionsModeration
  from configparser import SectionProxy


def findvettingchannel(config:"SectionProxy", guild:disnake.Guild) -> Optional[disnake.TextChannel]:
  """ Check if guild has a vetting channel and return it """

  for channel in guild.channels:
    if int(config.get(f'{guild.id}_{channel.id}', ChannelType.none)) == ChannelType.vetting:
      return channel
  return None


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


class ChannelType(int, Enum):
  """ Channel Types as they are stored """
  none = -1
  untraceable = 0
  traceable = 1
  vetting = 2
  feedback = 3
  untraceablefeedback = 4


class CorruptConfessionDataException(Exception):
  """ Thrown when decrypted ConfessionData doesn't fit the required format """


class NoMemberCacheError(Exception):
  """ Unable to continue without a member cache """


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
    origin:Optional[Union[disnake.Message, disnake.Interaction]] = None,
    targetchannel:Optional[disnake.TextChannel] = None,
    embed:Optional[disnake.Embed] = None
  ):

    if rawdata:
      self.offline = True

      binary = parent.crypto.decrypt(rawdata)
      if len(binary) != 24:
        raise CorruptConfessionDataException()

      self.author_id = int.from_bytes(binary[0:8], 'big')
      self.origin_id = int.from_bytes(binary[8:16], 'big')
      self.targetchannel_id = int.from_bytes(binary[16:24], 'big')
    else:
      self.offline = False
      self.author = author
      self.origin = origin
      self.targetchannel = targetchannel

    self.parent = parent
    self.embed = embed
    self.attachment = None

    if embed:
      if embed.description.startswith('**[Anon-'):
        self.content = embed.description[20:]
      else:
        self.content = embed.description
      self.image = embed.image.url if embed.image else None

  def store(self) -> str:
    """ Encrypt data for secure storage """

    if self.offline:
      bauthor = self.author_id.to_bytes(8, 'big')
      borigin = (self.origin_id if self.origin_id else 0).to_bytes(8, 'big')
      btarget = self.targetchannel_id.to_bytes(8, 'big')
    else:
      bauthor = self.author.id.to_bytes(8, 'big')
      borigin = (self.origin.id if self.origin else 0).to_bytes(8, 'big')
      btarget = self.targetchannel.id.to_bytes(8, 'big')

    binary = bauthor + borigin + btarget
    return self.parent.crypto.encrypt(binary).decode('ascii')

  async def fetch(self):
    """ Fetches referenced Discord elements for use """
    if self.offline:
      self.author = await self.parent.bot.fetch_user(self.author_id)
      self.origin = None
      if self.origin_id > 0:
        try:
          self.origin = await self.author.fetch_message(self.origin_id)
        except (disnake.NotFound, disnake.Forbidden):
          pass
      self.targetchannel = await self.parent.bot.fetch_channel(self.targetchannel_id)
      self.offline = False

  async def generate_embed(self, anonid:str, lead:str, content:str, image:Optional[str] = None):
    """ Generate the confession embed """
    if lead:
      self.anonid = anonid
      embed = disnake.Embed(colour=disnake.Colour(int(anonid,16)),description=lead+' '+content)
    else:
      self.anonid = None
      embed = disnake.Embed(description=content if content else '')
    if image:
      async with aiohttp.ClientSession() as session:
        async with session.get(image) as res:
          if res.status == 200:
            filename = 'file.'+res.content_type.replace('image/','')
            self.attachment = disnake.File(
              io.BytesIO(await res.read()),
              filename
            )
            embed.set_image(url='attachment://'+filename)
          else:
            if 'Log' in self.parent.bot.cogs:
              await self.parent.bot.cogs['Log'].log_misc_message(
                f"WARN: Failed to upload embedded image ({res.status})"
              )
            embed.set_image(url=image)
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
        #BABEL: confessions/missingperms
        await self.targetchannel.send(
          self.parent.babel(self.targetchannel.guild, 'missingperms', perm='Embed Links')
        )
        await ctx.send(self.parent.babel(ctx, 'embederr'), **kwargs)
      except disnake.Forbidden:
        #BABEL: confessions/missingchannelerr
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
    if self.parent.config.get(f'{self.targetchannel.guild.id}_webhook', None) == 'True':
      if webhook := await self.find_or_create_webhook(self.targetchannel):
        kwargs = {'file': self.attachment} if self.attachment else {}
        botcolour = self.parent.bot.config['main']['themecolor'][2:]
        func = webhook.send(
          self.content,
          username=(
            (preface + ' - ' if preface else '') +
            ('[Anon]' if self.anonid is None else '[Anon-' + self.anonid + ']')
          ),
          avatar_url=(
            self.parent.config.get('pfpgen_url', '')
            .replace('{}', botcolour if self.anonid is None else self.anonid)
          ),
          **kwargs
        )
        #TODO: add support for custom PFPs
    else:
      func = self.targetchannel.send(preface, embed=self.embed, file=self.attachment)

    if hasattr(ctx, 'response'):
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
      await channel.send(self.parent.babel(channel.guild, 'missingperms', perm='MANAGE_WEBHOOKS'))
      return None


def setup(_):
  """ Refuse to bind this cog to the bot """
  raise Exception("This module is not meant to be imported as an extension!")

"""
  Confessions - Anonymous messaging cog
  Features: botmod, bot banning, vetting, image support
  Dependencies: Auth, Help
  Notes: Contains generic command names like set, list, botmod, imagesupport, and ban
    As a result, this only really suits a singlular purpose bot
"""

from __future__ import annotations

import io, os, asyncio, re, time, base64, hashlib
from enum import Enum
from typing import Optional, Union, TYPE_CHECKING
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import disnake
from disnake.ext import commands
import aiohttp

from extensions.controlpanel import Toggleable, Stringable

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy


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
  anonid:str | None

  def __init__(
    self,
    parent:Confessions,
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

  async def send_vetting(
    self,
    ctx:Union[disnake.DMChannel, disnake.Interaction],
    confessions:Confessions,
    vettingchannel:disnake.TextChannel
  ):
    """ Send confession to a vetting channel for approval """
    success = await self.handle_send_errors(ctx, vettingchannel.send(
      self.parent.babel(vettingchannel.guild, 'vetmessagecta', channel=self.targetchannel.mention),
      embed=self.embed,
      file=self.attachment,
      view=confessions.PendingConfessionView(confessions, self)
    ))

    if success:
      await ctx.send(
        self.parent.babel(ctx, 'confession_vetting', channel=self.targetchannel.mention),
        ephemeral=True
      )

  async def send_confession(self, ctx:disnake.TextChannel | disnake.Interaction, smsg=False):
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
    success = await self.handle_send_errors(ctx, func)

    if success and smsg:
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


class Confessions(commands.Cog):
  """ Enable anonymous messaging with moderation on your server """
  SCOPE = 'confessions'

  @property
  def config(self) -> SectionProxy:
    """ Shorthand for self.bot.config[scope] """
    return self.bot.config[self.SCOPE]

  def babel(self, target:Resolvable, key:str, **values: dict[str, str | bool]) -> list[str]:
    """ Shorthand for self.bot.babel(scope, key, **values) """
    return self.bot.babel(target, self.SCOPE, key, **values)

  channel_icons = {
    ChannelType.untraceable: '🙈',
    ChannelType.traceable: '👁',
    ChannelType.feedback: '📢',
    ChannelType.untraceablefeedback: '🙈📢'
  }

  def __init__(self, bot:MerelyBot):
    self.bot = bot
    self.crypto = Crypto()

    # ensure config file has required data
    if not bot.config.has_section(self.SCOPE):
      bot.config.add_section(self.SCOPE)
    if 'confession_cooldown' not in self.config:
      self.config['confession_cooldown'] = '1'
    if 'report_channel' not in self.config:
      self.config['report_channel'] = ''
    if 'secret' not in self.config or self.config['secret'] == '':
      self.config['secret'] = self.crypto.keygen(32)
      print(
        "WARNING: Your security key has been regenerated. Old confessions are now incompatible."
      )
    if 'spam_flags' not in self.config:
      self.config['spam_flags'] = ''
    if 'pfpgen_url' not in self.config or self.config['pfpgen_url'] == '':
      self.config['pfpgen_url'] = ''
      print(
        "WARNING: You don't have a pfp generator. Profile pictures in webhook mode will be blank."
      )

    self.crypto.key = self.config['secret']

    # self.initiated = set()
    self.ignore = set()
    self.confession_cooldown = dict()

  def controlpanel_settings(self, inter:disnake.Interaction):
    # ControlPanel integration
    if inter.guild is None:
      return []
    out = []
    if inter.permissions.moderate_members:
      out.append(Stringable(self.SCOPE, f'{inter.guild_id}_banned', 'guild_banlist'))
    if inter.permissions.administrator:
      out += [
        Toggleable(self.SCOPE, f'{inter.guild_id}_imagesupport', 'image_support', default=True),
        Toggleable(self.SCOPE, f'{inter.guild_id}_webhook', 'enable_webhooks', default=False),
        Stringable(self.SCOPE, f'{inter.guild_id}_preface', 'confession_preface')
        #TODO: Add custom pfp stringable, Anon-ID usernames, Anon-Colour pfps
      ]
    return out

  def controlpanel_theme(self) -> tuple[str, disnake.ButtonStyle]:
    # Controlpanel custom theme for buttons
    return (self.SCOPE, disnake.ButtonStyle.blurple)

  #	Utility functions

  def get_anonid(self, guildid:int, userid:int) -> str:
    """ Calculates the current anon-id for a user """
    offset = int(self.config.get(f"{guildid}_shuffle", fallback=0))
    encrypted = self.crypto.encrypt(
      guildid.to_bytes(8, 'big') + userid.to_bytes(8, 'big') + offset.to_bytes(2, 'big')
    )
    return hashlib.sha256(encrypted).hexdigest()[-6:]

  def generate_list(
    self,
    user:disnake.User,
    matches:list[tuple],
    vetting:bool,
    enum:bool = False
  ) -> str:
    """ Returns a formatted list of available confession targets """

    targets = []
    for i, match in enumerate(matches):
      targets.append(
        (str(i+1)+':' if enum else '') +
        f'{self.channel_icons[match[1]]}<#{match[0].id}>' +
        (' ('+match[0].guild.name+')' if not isinstance(user, disnake.Member) else '')
      )
    vettingwarning = ('\n\n'+self.babel(user, 'vetting') if vetting else '')

    return '\n'.join(targets) + vettingwarning

  def scanguild(self, member:disnake.Member) -> tuple[disnake.TextChannel]:
    """ Scans a guild for any targets that a member can use for confessions """

    matches = []
    vetting = False
    for channel in member.guild.channels:
      if f"{member.guild.id}_{channel.id}" in self.config:
        chtype = int(self.config.get(f"{member.guild.id}_{channel.id}"))
        if chtype == ChannelType.vetting:
          vetting = True
          continue
        channel.name = channel.name[:40] + ('...' if len(channel.name) > 40 else '')
        channel.guild.name = channel.guild.name[:40]+('...' if len(channel.guild.name) > 40 else '')
        if chtype in (ChannelType.feedback, ChannelType.untraceablefeedback):
          matches.append((channel, chtype))
          continue
        if channel.permissions_for(member).read_messages:
          matches.append((channel, chtype))
          continue

    matches.sort(key=lambda m: m[0].position)

    return matches, vetting

  def listavailablechannels(
      self,
      user:Union[disnake.User, disnake.Member]
    ) -> tuple[disnake.TextChannel]:
    """
      List all available targets on a server for a member
      List all available targets on all mutual servers for a user
    """

    if isinstance(user, disnake.Member):
      matches,vetting = self.scanguild(user)
    else:
      if not self.bot.intents.members:
        raise NoMemberCacheError()
      matches = []
      vetting = False
      for guild in self.bot.guilds:
        if member := guild.get_member(user.id):
          newmatches, newvetting = self.scanguild(member)
          matches += newmatches
          vetting = vetting or newvetting

    return matches, vetting

  def findvettingchannel(self, guild) -> Optional[disnake.TextChannel]:
    """ Check if guild has a vetting channel and return it """

    for channel in guild.channels:
      if int(self.config.get(f'{guild.id}_{channel.id}', ChannelType.none)) == ChannelType.vetting:
        return channel
    return None

  async def safe_fetch_channel(
    self,
    ctx:Union[commands.Context, disnake.CommandInteraction],
    channel_id:int
  ) -> Optional[disnake.TextChannel]:
    """ Gracefully handles whenever a confession target isn't available """
    try:
      return await self.bot.fetch_channel(channel_id)
    except disnake.Forbidden:
      await ctx.send(
        self.babel(ctx, 'missingchannelerr') + ' (fetch)',
        **{'ephemeral':True} if isinstance(ctx, disnake.Interaction) else {}
      )
      return None

  #	Checks

  def check_channel(self, guild_id:int, channel_id:int) -> bool:
    """ Verifies channel is currently in the config """

    channeltype = int(self.config.get(f"{guild_id}_{channel_id}", fallback=ChannelType.none))
    if channeltype in [
      ChannelType.traceable,
      ChannelType.untraceable,
      ChannelType.feedback,
      ChannelType.untraceablefeedback
    ]:
      return True
    return False

  def check_banned(self, guild_id:int, anonid:str) -> bool:
    """ Verify the user hasn't been banned """

    if anonid in self.config.get(f"{guild_id}_banned", fallback='').split(','):
      return False
    return True

  def check_image(self, guild_id:int, image:disnake.Attachment) -> bool:
    """ Only allow images to be sent if imagesupport is enabled and the image is valid """

    if image and image.content_type.startswith('image') and image.size < 8_000_000:
      if bool(self.config.get(f"{guild_id}_imagesupport", fallback=True)):
        return True
      return False
    raise commands.BadArgument

  def check_spam(self, content:str):
    """ Verify message doesn't contain spam as defined in [confessions] spam_flags """

    for spamflag in self.config.get('spam_flags', fallback=None).splitlines():
      if re.match(spamflag, content):
        return False
    return True

  def check_promoted(self, member:disnake.Member):
    """ Verify provided member has been promoted """

    promoted_raw = self.config.get(f'{member.guild.id}_promoted', fallback='')
    promoted = [int(p) for p in promoted_raw.split(',') if p != '']
    return member.id in promoted or bool([r for r in member.roles if r.id in promoted])

  #	Views

  class ChannelSelectView(disnake.ui.View):
    """ View for selecting a target interactively """
    origin: disnake.Message
    confessions: Confessions
    matches: tuple[disnake.TextChannel]
    page: int = 0
    selection: Optional[disnake.TextChannel] = None
    done: bool = False

    def __init__(
        self,
        origin:disnake.Message,
        confessions: Confessions,
        matches: tuple[disnake.TextChannel]
      ):
      super().__init__(timeout=30)
      self.origin = origin
      self.confessions = confessions
      self.matches = matches
      self.update_list()
      self.channel_selector.placeholder = self.confessions.babel(origin, 'channelprompt_placeholder')
      self.send_button.label = self.confessions.babel(origin, 'channelprompt_button_send')

      if len(matches) > 25:
        # Add pagination only when needed
        self.page_decrement_button = disnake.ui.Button(
          disabled=True,
          style=disnake.ButtonStyle.secondary,
          label=self.confessions.babel(origin, 'channelprompt_button_prev')
        )
        self.page_decrement_button.callback = self.change_page(-1)
        self.add_item(self.page_decrement_button)

        self.page_increment_button = disnake.ui.Button(
          disabled=False,
          style=disnake.ButtonStyle.secondary,
          label=self.confessions.babel(origin, 'channelprompt_button_next')
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
          label=f'{channel.name} (from {channel.guild.name})',
          value=str(channel.id),
          emoji=Confessions.channel_icons[channeltype]
        ) for channel,channeltype in self.matches[start:start+25]
      ]

    @disnake.ui.select(min_values=1, max_values=1)
    async def channel_selector(self, _:disnake.ui.Select, inter:disnake.MessageInteraction):
      """ Update the message to preview the selected target """

      self.send_button.disabled = False
      try:
        self.selection = await self.confessions.bot.fetch_channel(int(inter.values[0]))
      except disnake.Forbidden:
        self.send_button.disabled = True
        await inter.response.edit_message(
          content=self.confessions.babel(inter, 'missingchannelerr')+' (select)',
          view=self
        )
        return
      vetting = self.confessions.findvettingchannel(self.selection.guild)
      channeltype = int(self.confessions.config.get(
        f"{self.selection.guild.id}_{self.selection.id}"
      ))
      await inter.response.edit_message(
        content=self.confessions.babel(
          inter, 'channelprompted', channel=self.selection.mention,
          vetting=vetting and channeltype not in (
            ChannelType.feedback, ChannelType.untraceablefeedback
          )
        ),
        view=self)

    @disnake.ui.button(disabled=True, style=disnake.ButtonStyle.primary)
    async def send_button(self, _:disnake.Button, inter:disnake.MessageInteraction):
      """ Send the confession """

      if self.selection is None:
        self.disable(inter)
        return

      anonid = self.confessions.get_anonid(self.selection.guild.id, inter.author.id)
      lead = f"**[Anon-*{anonid}*]**"
      channeltype = int(self.confessions.config.get(f"{self.selection.guild.id}_{self.selection.id}"))

      if not self.confessions.check_banned(self.selection.guild.id, anonid):
        await inter.send(self.confessions.babel(inter, 'nosendbanned'))
        await self.disable(inter)
        return

      pendingconfession = ConfessionData(
        self.confessions, author=inter.author, origin=self.origin, targetchannel=self.selection
      )
      if self.origin.attachments:
        if not self.confessions.check_image(self.selection.guild.id, self.origin.attachments[0]):
          await inter.send(self.confessions.babel(inter, 'nosendimages'))
          await self.disable(inter)
          return

      image = None
      if self.origin.attachments:
        image = self.origin.attachments[0].url
        await inter.response.defer(ephemeral=True)

      vetting = self.confessions.findvettingchannel(self.selection.guild)
      await pendingconfession.generate_embed(
        anonid,
        lead if vetting or channeltype != ChannelType.untraceable else '',
        self.origin.content,
        image
      )

      if vetting and channeltype not in (ChannelType.feedback, ChannelType.untraceablefeedback):
        await pendingconfession.send_vetting(inter, self.confessions, vetting)
        await self.disable(inter)
        return

      await pendingconfession.send_confession(inter)

      self.send_button.label = self.confessions.babel(inter, 'channelprompt_button_sent')
      self.channel_selector.disabled = True
      self.send_button.disabled = True
      self.done = True
      await inter.response.edit_message(
        content=self.confessions.babel(
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
          self.confessions.babel(inter, 'channelprompt') + ' ' +
          self.confessions.babel(inter, 'channelprompt_pager', page=self.page + 1)
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
      try:
        if not self.done:
          await self.origin.reply(
            self.confessions.babel(self.origin.author, 'timeouterror')
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

  class PendingConfessionView(disnake.ui.View):
    """ Asks moderators to approve or deny a confession as a part of vetting """
    def __init__(self, confessions:Confessions, pendingconfession:ConfessionData):
      self.confessions = confessions
      self.pendingconfession = pendingconfession
      super().__init__(timeout=None)

      data = self.pendingconfession.store()
      self.add_item(disnake.ui.Button(
        label=confessions.babel(
          self.pendingconfession.targetchannel.guild, 'vetting_approve_button'
        ),
        emoji='✅',
        style=disnake.ButtonStyle.blurple,
        custom_id=f"pendingconfession_approve_{data}"
      ))

      self.add_item(disnake.ui.Button(
        label=confessions.babel(self.pendingconfession.targetchannel.guild, 'vetting_deny_button'),
        emoji='❎',
        style=disnake.ButtonStyle.danger,
        custom_id=f"pendingconfession_deny_{data}"
      ))

  class ReportView(disnake.ui.View):
    """ Provides all the guidance needed before a user reports a confession """
    def __init__(
        self,
        confessions:"Confessions",
        message: disnake.Message,
        origin: disnake.Interaction
    ):
      super().__init__(timeout=300)

      self.confessions = confessions
      self.message = message
      self.origin = origin

      self.report_button.label = confessions.babel(origin, 'report_button')

      asyncio.ensure_future(self.enable_button())

    async def enable_button(self):
      """ Waits 5 seconds before enabling the report button to encourage the user to read """
      await asyncio.sleep(5)
      self.report_button.disabled = False
      await self.origin.edit_original_message(view=self, suppress_embeds=True)

    @disnake.ui.button(disabled=True, style=disnake.ButtonStyle.gray, emoji='➡️')
    async def report_button(self, _:disnake.Button, inter:disnake.MessageInteraction):
      """ On click of continue button """
      await inter.response.send_modal(
        self.confessions.ReportModal(self.confessions, self.message, self.origin)
      )
      await inter.delete_original_response()

  # Modals

  class ReportModal(disnake.ui.Modal):
    """ Confirm user input before sending a report """
    def __init__(
        self,
        confessions:"Confessions",
        message: disnake.Message,
        origin: disnake.Interaction
    ):
      super().__init__(
        title=confessions.babel(origin, 'report_title'),
        custom_id=f'report_{message.id}',
        components=[
          disnake.ui.TextInput(
            label=confessions.babel(origin, 'report_field'),
            placeholder=confessions.babel(origin, 'report_placeholder'),
            custom_id='report_reason',
            style=disnake.TextInputStyle.paragraph,
            min_length=1
          )
        ],
        timeout=600
      )

      self.confessions = confessions
      self.message = message
      self.origin = origin

    async def callback(self, inter: disnake.ModalInteraction):
      """ Send report to mod channel as configured """
      if self.confessions.config['report_channel']:
        reportchannel = await self.confessions.safe_fetch_channel(
          inter, int(self.confessions.config.get('report_channel'))
        )
        if reportchannel is None:
          await inter.response.send_message(
            self.confessions.babel(inter, 'report_failed')
          )
          return
        embed:disnake.Embed
        if len(self.message.embeds) > 0:
          embed = self.message.embeds[0]
        else:
          embed = disnake.Embed(description=f'**{self.message.author.name}** {self.message.content}')
        await reportchannel.send(
          self.confessions.babel(
            reportchannel.guild, 'new_report',
            server=f'{inter.guild.name} ({inter.guild.id})',
            user=f'{inter.author.mention} ({inter.author.name}#{inter.author.discriminator})',
            reason=inter.text_values['report_reason']
          ),
          embed=embed,
        )
        await inter.response.send_message(
          self.confessions.babel(inter, 'report_success'),
          ephemeral=True,
          suppress_embeds=True
        )

  class ConfessionModal(disnake.ui.Modal):
    """ Modal for completing an incomplete confession """
    def __init__(
      self,
      confessions:"Confessions",
      origin:disnake.Interaction,
      pendingconfession:ConfessionData
    ):
      super().__init__(
        title=confessions.babel(origin, 'editor_title'),
        custom_id="confession_modal",
        components=[
          disnake.ui.TextInput(
            label=confessions.babel(origin, 'editor_message_label'),
            placeholder=confessions.babel(origin, 'editor_message_placeholder'),
            custom_id="content",
            style=disnake.TextInputStyle.paragraph,
            min_length=1
          )
        ]
      )

      self.confessions = confessions
      self.origin = origin
      self.pendingconfession = pendingconfession

    async def callback(self, inter:disnake.ModalInteraction):
      """ Send the completed confession """

      if 'Log' in self.confessions.bot.cogs:
        await self.confessions.bot.cogs['Log'].log_misc_str(inter, inter.text_values['content'])

      if not self.confessions.check_spam(inter.text_values['content']):
        await inter.send(
          self.confessions.babel(inter, 'nospam'),
          ephemeral=True
        )
        return

      anonid = self.confessions.get_anonid(inter.guild.id, inter.author.id)
      channeltype = int(self.confessions.config.get(
        f"{self.pendingconfession.targetchannel.guild.id}_{self.pendingconfession.targetchannel.id}"
      ))
      lead = f"**[Anon-*{anonid}*]**"

      vetting = self.confessions.findvettingchannel(inter.guild)
      await self.pendingconfession.generate_embed(
        anonid,
        lead if vetting or channeltype not in (
          ChannelType.untraceable, ChannelType.untraceablefeedback
        ) else '',
        inter.text_values['content']
      )

      if vetting and channeltype != ChannelType.vetting:
        await self.pendingconfession.send_vetting(inter, self.confessions, vetting)
        return

      await self.pendingconfession.send_confession(inter, True)

  #	Events

  @commands.Cog.listener('on_button_click')
  async def on_confession_review(self, inter:disnake.MessageInteraction):
    """ Handle approving and denying confessions """
    await inter.response.defer()
    if inter.data.custom_id.startswith('pendingconfession_'):
      vetmessage = inter.message

      try:
        if inter.data.custom_id.startswith('pendingconfession_approve_'):
          pendingconfession = ConfessionData(
            self, inter.data.custom_id[26:], embed=vetmessage.embeds[0]
          )
          accepted = True

        elif inter.data.custom_id.startswith('pendingconfession_deny_'):
          pendingconfession = ConfessionData(self, inter.data.custom_id[23:])
          accepted = False
        else:
          print(f"WARN: Unknown button action '{inter.data.custom_id}'!")
          return
      except CorruptConfessionDataException:
        await inter.response.send_message(self.babel(inter, 'vetcorrupt'))
        return

      try:
        await pendingconfession.fetch()
      except (disnake.NotFound, disnake.Forbidden):
        if accepted:
          await inter.response.send_message(self.babel(
            inter, 'vettingrequiredmissing', channel=f"<#{pendingconfession.targetchannel_id}>"
          ))
          return

      if accepted:
        anonid = self.get_anonid(inter.guild.id, pendingconfession.author.id)
        lead = f"**[Anon-*{anonid}*]**"
        channeltype = int(self.config.get(f"{inter.guild.id}_{pendingconfession.targetchannel_id}"))

        await pendingconfession.generate_embed(
          anonid,
          lead if channeltype not in (
            ChannelType.untraceable,
            ChannelType.untraceablefeedback
          ) else '',
          pendingconfession.content,
          pendingconfession.image
        )

        if not pendingconfession.author.dm_channel:
          await pendingconfession.author.create_dm()
        await pendingconfession.send_confession(inter)

      await vetmessage.edit(view=None)
      await inter.response.send_message(self.babel(
        inter.guild,
        'vetaccepted' if accepted else 'vetdenied',
        user=inter.author.mention,
        channel=f"<#{pendingconfession.targetchannel_id}>"
      ))

      content = self.babel(
        pendingconfession.author,
        'confession_vetting_accepted' if accepted else 'confession_vetting_denied',
        channel=f"<#{pendingconfession.targetchannel_id}>"
      )
      if isinstance(pendingconfession.origin, disnake.Message):
        await pendingconfession.origin.reply(content)
      elif isinstance(pendingconfession.origin, disnake.Interaction):
        await pendingconfession.origin.send(content, ephemeral=True)
      else:
        await pendingconfession.author.send(content)

  @commands.Cog.listener('on_message')
  async def confession_request(self, msg:disnake.Message):
    """ Handle plain DM messages as confessions """
    ctx = await self.bot.get_context(msg)
    if ctx.prefix is not None:
      return
    if isinstance(msg.channel, disnake.DMChannel) and\
       msg.author != self.bot.user:
      if msg.channel in self.ignore:
        self.ignore.remove(msg.channel)
        return
      if msg.author in self.confession_cooldown and\
         self.confession_cooldown[msg.author] > time.time():
        return
      else:
        self.confession_cooldown[msg.author] = time.time() +\
          int(self.config.get('confession_cooldown', fallback=1))

      if 'Log' in self.bot.cogs:
        await self.bot.cogs['Log'].log_misc_message(msg)

      if not self.bot.member_cache:
        await msg.reply(self.babel(msg, 'dmconfessiondisabled'))
        return
      matches,_ = self.listavailablechannels(msg.author)

      if not self.bot.is_ready():
        await msg.reply(self.babel(msg, 'cachebuilding'))
        if not matches:
          return

      if not matches:
        await msg.reply(self.babel(msg, 'inaccessible'))
        return

      if not self.check_spam(msg.content):
        await msg.reply(self.babel(msg, 'nospam'))
        return

      await msg.reply(
        self.babel(msg, 'channelprompt') +
        (' ' + self.babel(msg, 'channelprompt_pager', page=1) if len(matches) > 25 else ''),
        view=self.ChannelSelectView(msg, self, matches))

  # Clear config when the bot is removed from a guild
  @commands.Cog.listener('on_guild_leave')
  async def guild_cleanup(self, guild:disnake.Guild):
    """ Automatically remove data related to a guild on removal """
    for option in self.config:
      if option.startswith(str(guild.id)+'_'):
        self.bot.config.remove_option(self.SCOPE, option)
    self.bot.config.save()

  # Clear config when a channel is deleted
  @commands.Cog.listener('on_guild_channel_delete')
  async def channel_cleanup(self, channel:disnake.TextChannel):
    """ Automatically remove data related to a channel on delete """
    for option in self.config:
      if option == str(channel.guild.id)+'_'+str(channel.id):
        self.bot.config.remove_option(self.SCOPE, option)
        break
    self.bot.config.save()

  # Context menu commands

  @commands.cooldown(1, 60)
  @commands.message_command(name="Report confession", dm_permission=False)
  async def report(self, inter:disnake.MessageCommandInteraction):
    """ Reports a confession to the bot owners """
    if (
      (
        inter.target.author == self.bot.user and
        len(inter.target.embeds) > 0 and
        inter.target.embeds[0].title is None
      ) or (
        inter.target.application_id == self.bot.application_id and
        ('[Anon-' in inter.target.author.name or '[Anon]' in inter.target.author.name)
      )
    ):
      await inter.response.send_message(
        content=self.babel(inter, 'report_prep', msgurl=inter.target.jump_url),
        view=self.ReportView(self, inter.target, inter),
        ephemeral=True,
        suppress_embeds=True
      )
      return

    await inter.response.send_message(
      self.babel(inter, 'report_invalid_message'),
      ephemeral=True
    )

  @commands.cooldown(1, 1)
  @commands.message_command(name="Confess here", dm_permission=False)
  async def confess_message(self, inter:disnake.MessageCommandInteraction):
    """ Shorthand to start a confession modal in this channel """
    await self.confess(inter)

  #	Slash commands

  @commands.cooldown(1, 1)
  @commands.slash_command()
  async def confess(
    self,
    inter: disnake.GuildCommandInteraction,
    content:Optional[str] = None,
    image:Optional[disnake.Attachment] = None,
    **kwargs
  ):
    """
    Send an anonymous message to this channel

    Parameters
    ----------
    content: The text of your anonymous message, leave blank for a paragraph editor
    image: An optional image that appears below the text
    """

    if 'channel' in kwargs:
      channel = kwargs['channel']
    else:
      channel = inter.channel

    if not self.check_channel(inter.guild_id, channel.id):
      await inter.send(self.babel(inter, 'nosendchannel'), ephemeral=True)
      return

    anonid = self.get_anonid(inter.guild_id, inter.author.id)
    lead = f"**[Anon-*{anonid}*]**"
    channeltype = int(self.config.get(f"{inter.guild_id}_{channel.id}"))

    if not self.check_banned(inter.guild_id, anonid):
      await inter.send(self.babel(inter, 'nosendbanned'), ephemeral=True)
      return

    if image:
      if not self.check_image(inter.guild_id, image):
        await inter.send(self.babel(inter, 'nosendimages'), ephemeral=True)
        return

    pendingconfession = ConfessionData(self, author=inter.author, targetchannel=channel)

    if content or image:
      if content is None:
        content = ''

      if not self.check_spam(content):
        await inter.send(self.babel(inter, 'nospam'), ephemeral=True)
        return

      vetting = self.findvettingchannel(inter.guild)

      if image:
        await inter.response.defer(ephemeral=True)

      await pendingconfession.generate_embed(
        anonid,
        lead if vetting or channeltype not in (
          ChannelType.untraceable,
          ChannelType.untraceablefeedback
         ) else '',
        content,
        image.url if image else None
      )

      if (
        (vetting := self.findvettingchannel(inter.guild)) and
        channeltype not in (ChannelType.feedback, ChannelType.untraceablefeedback)
        ):
        await pendingconfession.send_vetting(inter, self, vetting)
        return

      await pendingconfession.send_confession(inter, True)

    else:
      await inter.response.send_modal(
        modal=self.ConfessionModal(self, inter, pendingconfession)
      )

  @commands.cooldown(1, 1)
  @commands.slash_command(name='confess-to')
  async def confess_to(
    self,
    inter:disnake.GuildCommandInteraction,
    channel:str,
    content:Optional[str] = None,
    image:Optional[disnake.Attachment] = None
  ):
    """
    Send an anonymous message to a specified channel

    Parameters
    ----------
    channel: The target channel, can include anonymous feedback channels that you can't see
    content: The text of your anonymous message, leave blank for a paragraph editor
    image: An optional image that appears below the text
    """

    search = re.search(r".*\((\d+)\)$", channel)
    if search:
      channel_id = search.groups()[0]
      targetchannel = await self.safe_fetch_channel(inter, channel_id)
      if targetchannel is None:
        return
      await self.confess(inter, content, image, channel=targetchannel)
    else:
      raise commands.BadArgument("Channel must be selected from the list")

  @confess_to.autocomplete('channel')
  async def channel_ac(self, inter:disnake.GuildCommandInteraction, search:str):
    """ Lists available channels, allows searching by name """
    if not isinstance(inter.author, disnake.Member):
      return [self.bot.babel(inter, 'error', 'noprivatemessage').replace('*','')]

    results = []
    matches, _ = self.scanguild(inter.author)
    for match in matches:
      if search in match[0].name:
        results.append(f"{self.channel_icons[match[1]]} #{match[0].name} ({match[0].id})")
    return results[0:24] + (
      ['this list is incomplete, use /list to see all'] if len(results) > 25 else []
    )

  @commands.slash_command(dm_permission=False)
  async def set(
    self,
    inter:disnake.GuildCommandInteraction,
    mode:ChannelType = commands.Param(None, ge=ChannelType.none)
  ):
    """
    Set a channel for use with ConfessionBot

    Parameters
    ----------
    mode: The channel type, use `/help set` for an explaination of types
    """
    self.bot.auth.admins(inter)
    if mode is None:
      raise commands.BadArgument()
    elif mode == ChannelType.none:
      wastype = int(self.config.get(
        f'{inter.guild.id}_{inter.channel.id}', fallback=ChannelType.none
      ))
      if wastype == ChannelType.none:
        await inter.send(self.babel(inter, 'unsetfailure'))
        return
      self.bot.config.remove_option(self.SCOPE, str(inter.guild.id)+'_'+str(inter.channel.id))
    else:
      self.config[str(inter.guild.id)+'_'+str(inter.channel.id)] = str(mode)
    self.bot.config.save()

    modestring = (
      'setsuccess'+str(mode) if mode > ChannelType.none else 'unsetsuccess'+str(wastype)
    )
    await inter.send(
      self.babel(inter, modestring) + ' ' +
      self.babel(inter, 'setundo' if mode > ChannelType.none else 'unsetundo') +
      ('\n'+self.babel(inter, 'setcta') if mode > ChannelType.none else '')
    )

  @commands.slash_command()
  async def list(self, inter:disnake.CommandInteraction):
    """
    List all anonymous channels available here
    """
    try:
      matches, vetting = self.listavailablechannels(inter.author)
    except NoMemberCacheError:
      await inter.send(self.babel(inter, 'dmconfessiondisabled'))
      return

    # warn users when the channel list isn't complete
    local = isinstance(inter.author, disnake.Member)
    if not self.bot.is_ready() and not local:
      await inter.send(self.babel(inter, 'cachebuilding'), ephemeral=True)
    elif len(matches) == 0:
      await inter.send(
        self.babel(inter, 'inaccessiblelocal' if local else 'inaccessible'),
        ephemeral=True
      )
    # send the list of channels, complete or not
    if len(matches) > 0:
      await inter.send((
        self.babel(inter, 'listtitlelocal' if local else 'listtitle') + '\n' +
        self.generate_list(inter.author, matches, vetting) +
        (
          '\n\n' + self.babel(inter, 'confess_to_feedback')
          if [m for m in matches if m[1] in (
            ChannelType.feedback, ChannelType.untraceablefeedback
          )] else ''
        )
      ), ephemeral=True)

  @commands.slash_command(dm_permission=False)
  async def shuffle(self, inter:disnake.GuildCommandInteraction):
    """
    Change all anon-ids on a server
    """
    if not self.check_promoted(inter.author):
      self.bot.auth.mods(inter)
    if str(inter.guild.id)+'_banned' in self.config:
      await inter.send(self.babel(inter, 'shufflebanresetwarning'))

      def check(m):
        return m.channel == inter.channel and\
               m.author == inter.author and\
               m.content.lower() == 'yes'
      try:
        await self.bot.wait_for('message', check=check, timeout=30)
      except asyncio.TimeoutError:
        await inter.send(self.babel(inter, 'timeouterror'))
      else:
        self.bot.config.remove_option(self.SCOPE, str(inter.guild.id)+'_banned')

    shuffle = int(self.config.get(f'{inter.guild.id}_shuffle', fallback=0))
    self.bot.config.set(self.SCOPE, str(inter.guild.id)+'_shuffle', str(shuffle + 1))
    self.bot.config.save()

    await inter.send(self.babel(inter, 'shufflesuccess'))

  @commands.slash_command(dm_permission=False)
  async def imagesupport(self, inter:disnake.GuildCommandInteraction):
    """
      Enable or disable images in confessions
    """
    #TODO: delete this in time as users adjust
    if 'Help' in self.bot.cogs:
      await self.bot.cogs['Help'].slash_help(inter, 'imagesupport', ephemeral=True)

  @commands.slash_command(aliases=['ban'], dm_permission=False)
  async def block(
    self,
    inter:disnake.GuildCommandInteraction,
    anonid:Optional[str] = commands.Param(None),
    unblock:Optional[bool] = False
  ):
    """
    Block or unblock anon-ids from confessing

    Parameters
    ----------
    anonid: The anonymous id found next to any traceable anonymous message
    unblock: Set to true if you want to unblock this id instead
    """
    if not self.check_promoted(inter.author):
      self.bot.auth.mods(inter)

    banlist = self.config.get(f'{inter.guild.id}_banned', fallback='')
    banlist_split = banlist.split(',')
    if anonid is None:
      if banlist_split:
        printedlist = '\n```'+'\n'.join(banlist_split)+'```'
        await inter.send(self.babel(inter, 'banlist') + printedlist)
      else:
        await inter.send(self.babel(inter, 'emptybanlist'))
      return

    anonid = anonid.lower()
    if len(anonid) > 6:
      anonid = anonid[-6:]
    try:
      int(anonid, 16)
    except ValueError:
      await inter.send(self.babel(inter, 'invalidanonid'))
      return
    if anonid in banlist_split and not unblock:
      await inter.send(self.babel(inter, 'doublebananonid'))
      return

    if unblock:
      fullid = [i for i in banlist_split if anonid in i][0]
      self.config[str(inter.guild.id)+'_banned'] = banlist.replace(fullid+',','')
    else:
      self.config[str(inter.guild.id)+'_banned'] = banlist + anonid + ','
    self.bot.config.save()

    await inter.send(
      self.babel(inter, ('un' if unblock else '')+'bansuccess', user=anonid)
    )

  @commands.slash_command(dm_permission=False)
  async def botmod(
    self,
    inter:disnake.GuildCommandInteraction,
    target:Optional[Union[disnake.Member, disnake.Role]] = None,
    revoke:Optional[bool] = False
  ):
    """
    Grant or take away botmod powers from a user

    Parameters
    ----------
    target: The user or role which will be affected by this command
    revoke: Set to true if you want to revoke botmod powers
    """
    self.bot.auth.admins(inter)

    modlist = self.config.get(f'{inter.guild.id}_promoted', fallback='')
    if target is None:
      if modlist:
        printedlist = '\n```\n' + '\n'.join(modlist.split(',')) + '```'
        await inter.send(self.babel(inter, 'botmodlist') + printedlist)
      else:
        await inter.send(self.babel(inter, 'botmodemptylist'))
    elif target:
      if isinstance(target, disnake.Member):
        if target.bot:
          await inter.send(self.babel(inter, 'botmodboterr'))
          return
        if target.guild_permissions.ban_members:
          await inter.send(self.babel(inter, 'botmodmoderr'))
          return
      else:
        if target.permissions.ban_members:
          await inter.send(self.babel(inter, 'botmodmoderr'))
          return

      if revoke:
        if str(target.id) in modlist.split(','):
          modlist = modlist.replace(str(target.id)+',','')
          self.config[str(inter.guild.id)+'_promoted'] = modlist
          self.bot.config.save()
          await inter.send(
            self.babel(inter, 'botmoddemotesuccess', user=target.name)
          )
        else:
          await inter.send(self.babel(inter, 'botmoddemoteerr'))
      else:
        if str(target.id) not in modlist.split(','):
          modlist += str(target.id)+','
          self.config[str(inter.guild.id)+'_promoted'] = modlist
          self.bot.config.save()
          await inter.send(self.babel(inter, 'botmodsuccess', user=target.name))
        else:
          await inter.send(self.babel(inter, 'rebotmoderr'))
    else:
      raise commands.BadArgument()


def setup(bot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(Confessions(bot))

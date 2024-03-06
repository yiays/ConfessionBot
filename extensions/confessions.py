"""
  Confessions - Anonymous messaging cog
  Features: bot banning, vetting, image support
  Dependencies: Auth, Help
  Note: Contains generic command names like setup, list, and block
    As a result, this only really suits a singlular purpose bot
"""

from __future__ import annotations

import re, time, hashlib
from typing import Optional, Union, TYPE_CHECKING
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy

from overlay.extensions.confessions_common\
  import ChannelType, ConfessionData, NoMemberCacheError, Crypto, findvettingchannel


class Confessions(commands.Cog):
  """ Facilitates anonymous messaging with moderation on your server """
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

    if not bot.config.getboolean('extensions', 'confessions_setup', fallback=False):
      print("WARN: Without `confessions_setup` enabled, users won't be able to change settings!")
    if not bot.config.getboolean('extensions', 'confessions_moderation', fallback=False):
      print("WARN: Without `confessions_moderation` enabled, vetting channels won't work!")

    self.crypto.key = self.config['secret']
    self.ignore = set()
    self.confession_cooldown = dict()

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

  #	Views

  class ChannelSelectView(disnake.ui.View):
    """ View for selecting a target interactively """
    origin: disnake.Message
    parent: Confessions
    matches: tuple[disnake.TextChannel]
    page: int = 0
    selection: Optional[disnake.TextChannel] = None
    done: bool = False

    def __init__(
        self,
        origin:disnake.Message,
        parent: Confessions,
        matches: tuple[disnake.TextChannel]
      ):
      super().__init__(timeout=30)
      self.origin = origin
      self.parent = parent
      self.matches = matches
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
        self.selection = await self.parent.bot.fetch_channel(int(inter.values[0]))
      except disnake.Forbidden:
        self.send_button.disabled = True
        await inter.response.edit_message(
          content=self.parent.babel(inter, 'missingchannelerr')+' (select)',
          view=self
        )
        return
      vetting = findvettingchannel(self.parent.config, self.selection.guild)
      channeltype = int(self.parent.config.get(
        f"{self.selection.guild.id}_{self.selection.id}"
      ))
      await inter.response.edit_message(
        content=self.parent.babel(
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

      anonid = self.parent.get_anonid(self.selection.guild.id, inter.author.id)
      lead = f"**[Anon-*{anonid}*]**"
      channeltype = int(self.parent.config.get(f"{self.selection.guild.id}_{self.selection.id}"))

      if not self.parent.check_banned(self.selection.guild.id, anonid):
        await inter.send(self.parent.babel(inter, 'nosendbanned'))
        await self.disable(inter)
        return

      pendingconfession = ConfessionData(
        self.parent, author=inter.author, origin=self.origin, targetchannel=self.selection
      )
      if self.origin.attachments:
        if not self.parent.check_image(self.selection.guild.id, self.origin.attachments[0]):
          await inter.send(self.parent.babel(inter, 'nosendimages'))
          await self.disable(inter)
          return

      image = None
      if self.origin.attachments:
        image = self.origin.attachments[0].url
        await inter.response.defer(ephemeral=True)

      vetting = findvettingchannel(self.parent.config, self.selection.guild)
      await pendingconfession.generate_embed(
        anonid,
        lead if vetting or channeltype != ChannelType.untraceable else '',
        self.origin.content,
        image
      )

      if vetting and channeltype not in (ChannelType.feedback, ChannelType.untraceablefeedback):
        if 'ConfessionsModeration' in self.parent.bot.cogs:
          await self.parent.bot.cogs['ConfessionModeration'].send_vetting(
            inter, pendingconfession, vetting
          )
        else:
          await inter.response.send_message(
            self.parent.babel(inter, 'no_moderation'),
            ephemeral=True
          )
        await self.disable(inter)
        return

      await pendingconfession.send_confession(inter)

      self.send_button.label = self.parent.babel(inter, 'channelprompt_button_sent')
      self.channel_selector.disabled = True
      self.send_button.disabled = True
      self.done = True
      await inter.response.edit_message(
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

  # Modals

  class ConfessionModal(disnake.ui.Modal):
    """ Modal for completing an incomplete confession """
    def __init__(
      self,
      parent:"Confessions",
      origin:disnake.Interaction,
      pendingconfession:ConfessionData
    ):
      super().__init__(
        title=parent.babel(origin, 'editor_title'),
        custom_id="confession_modal",
        components=[
          disnake.ui.TextInput(
            label=parent.babel(origin, 'editor_message_label'),
            placeholder=parent.babel(origin, 'editor_message_placeholder'),
            custom_id="content",
            style=disnake.TextInputStyle.paragraph,
            min_length=1
          )
        ]
      )

      self.parent = parent
      self.origin = origin
      self.pendingconfession = pendingconfession

    async def callback(self, inter:disnake.ModalInteraction):
      """ Send the completed confession """

      if 'Log' in self.parent.bot.cogs:
        await self.parent.bot.cogs['Log'].log_misc_str(inter, inter.text_values['content'])

      if not self.parent.check_spam(inter.text_values['content']):
        await inter.send(
          self.parent.babel(inter, 'nospam'),
          ephemeral=True
        )
        return

      anonid = self.parent.get_anonid(inter.guild.id, inter.author.id)
      channeltype = int(self.parent.config.get(
        f"{self.pendingconfession.targetchannel.guild.id}_{self.pendingconfession.targetchannel.id}"
      ))
      lead = f"**[Anon-*{anonid}*]**"

      vetting = findvettingchannel(self.parent.config, inter.guild)

      await self.pendingconfession.generate_embed(
        anonid,
        lead if vetting or channeltype not in (
          ChannelType.untraceable, ChannelType.untraceablefeedback
        ) else '',
        inter.text_values['content']
      )
      if vetting and channeltype != ChannelType.vetting:
        if 'ConfessionsModeration' in self.parent.bot.cogs:
          await self.parent.bot.cogs['ConfessionModeration'].send_vetting(
            inter, self.pendingconfession, vetting
          )
        else:
          await inter.response.send_message(
            self.parent.babel(inter, 'no_moderation'),
            ephemeral=True
          )
        return

      await self.pendingconfession.send_confession(inter, True)

  #	Events

  @commands.Cog.listener('on_button_click')
  async def on_confession_review(self, inter:disnake.MessageInteraction):
    """ Handle approving and denying confessions """
    if (
      inter.data.custom_id.startswith('pendingconfession_') and
      'ConfessionsModeration' not in self.bot.cogs
    ):
      await inter.response.send_message(self.babel(inter, 'no_moderation'))

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

  # Context menu commands

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

      vetting = findvettingchannel(self.config, inter.guild)

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

      if vetting and channeltype not in (ChannelType.feedback, ChannelType.untraceablefeedback):
        if 'ConfessionsModeration' in self.bot.cogs:
          await self.bot.cogs['ConfessionsModeration'].send_vetting(
            inter, pendingconfession, vetting
          )
        else:
          await inter.response.send_message(self.babel(inter, 'no_moderation'), ephemeral=True)
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


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(Confessions(bot))

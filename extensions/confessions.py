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

from overlay.extensions.confessions_common import (
  ChannelType, ChannelSelectView, ConfessionData, NoMemberCacheError, Crypto,
  findvettingchannel, get_guildchannels, check_channel
)


class Confessions(commands.Cog):
  """ Facilitates anonymous messaging with moderation on your server """
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
      if not bot.quiet:
        print(
          " - WARN: Your security key has been regenerated. Old confessions are now incompatible"
        )
    if 'spam_flags' not in self.config:
      self.config['spam_flags'] = ''

    if not bot.config.getboolean('extensions', 'confessions_setup', fallback=False):
      if not bot.quiet:
        print(" - WARN: Without `confessions_setup` enabled, users won't be able to change settings")
    if not bot.config.getboolean('extensions', 'confessions_moderation', fallback=False):
      if not bot.quiet:
        print(" - WARN: Without `confessions_moderation` enabled, vetting channels won't work")

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
    matches:list[tuple[disnake.TextChannel, ChannelType]],
    vetting:bool
  ) -> str:
    """ Returns a formatted list of available confession targets """

    targets = []
    for match in matches:
      targets.append(
        f'{match[1].icon} <#{match[0].id}>' +
        (' ('+match[0].guild.name+')' if not isinstance(user, disnake.Member) else '')
      )
    vettingwarning = ('\n\n'+self.babel(user, 'vetting') if vetting else '')

    return '\n'.join(targets) + vettingwarning

  def scanguild(
    self, member:disnake.Member
  ) -> tuple[list[tuple[disnake.TextChannel, ChannelType]], bool]:
    """ Scans a guild for any targets that a member can use for confessions """

    matches:list[tuple[disnake.TextChannel, ChannelType]] = []
    vetting = False
    guildchannels = get_guildchannels(self.config, member.guild.id)
    for channel in member.guild.channels:
      if channel.id in guildchannels:
        if guildchannels[channel.id] == ChannelType.vetting():
          vetting = True
          continue
        channel.name = channel.name[:40] + ('...' if len(channel.name) > 40 else '')
        channel.guild.name = channel.guild.name[:40]+('...' if len(channel.guild.name) > 40 else '')
        if 'feedback' in guildchannels[channel.id].name:
          matches.append((channel, guildchannels[channel.id]))
          continue
        if channel.permissions_for(member).read_messages:
          matches.append((channel, guildchannels[channel.id]))
          continue

    matches.sort(key=lambda t: (t[0].category.position if t[0].category else 0, t[0].position))

    return matches, vetting

  def listavailablechannels(
      self,
      user:Union[disnake.User, disnake.Member]
    ) -> tuple[list[tuple[disnake.TextChannel, ChannelType]], bool]:
    """
      List all available targets on a server for a member
      List all available targets on all mutual servers for a user
    """

    if isinstance(user, disnake.Member):
      matches, vetting = self.scanguild(user)
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
    inter:disnake.CommandInteraction,
    channel_id:int
  ) -> Optional[disnake.TextChannel]:
    """ Gracefully handles whenever a confession target isn't available """
    try:
      return await self.bot.fetch_channel(channel_id)
    except disnake.Forbidden:
      await inter.send(
        self.babel(inter, 'missingchannelerr') + ' (fetch)',
        ephemeral=True
      )
      return None

  #	Checks

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

  def check_spam(self, content:str | None):
    """ Verify message doesn't contain spam as defined in [confessions] spam_flags """

    for spamflag in self.config.get('spam_flags', fallback=None).splitlines():
      if content and re.match(spamflag, content):
        return False
    return True

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
            min_length=1,
            max_length=3900
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
      guildchannels = get_guildchannels(self.parent.config, inter.guild.id)
      channeltype = guildchannels[self.pendingconfession.targetchannel_id]

      vetting = findvettingchannel(guildchannels)

      await self.pendingconfession.generate_embed(
        anonid,
        vetting or channeltype.anonid,
        inter.text_values['content']
      )
      if vetting and channeltype != ChannelType.vetting():
        if 'ConfessionsModeration' in self.parent.bot.cogs:
          await self.parent.bot.cogs['ConfessionsModeration'].send_vetting(
            inter, self.pendingconfession, inter.guild.get_channel(vetting)
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
    """ Notify users when handling vetting is not possible """
    if (
      inter.data.custom_id.startswith('pendingconfession_') and
      'ConfessionsModeration' not in self.bot.cogs
    ):
      await inter.response.send_message(self.babel(inter, 'no_moderation'))

  @commands.Cog.listener('on_message')
  async def confession_request(self, msg:disnake.Message):
    """ Handle plain DM messages as confessions """
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
        view=ChannelSelectView(msg, self, matches))

  # Context menu commands

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  @commands.message_command(name="Confess here", dm_permission=False)
  async def confess_message(self, inter:disnake.MessageCommandInteraction):
    """ Shorthand to start a confession modal in this channel """
    await self.confess(inter)

  #	Slash commands

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  @commands.slash_command()
  async def confess(
    self,
    inter: disnake.GuildCommandInteraction,
    content: Optional[str] = commands.Param(default=None, max_length=3900),
    image: Optional[disnake.Attachment] = None,
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

    if channeltype := check_channel(self.config, inter.guild_id, channel.id):
      if channeltype == ChannelType.marketplace() and 'marketplace' not in kwargs:
        await inter.send(self.babel(inter, 'wrongcommand', cmd='sell'), ephemeral=True)
        return
    else:
      await inter.send(self.babel(inter, 'nosendchannel'), ephemeral=True)
      return

    anonid = self.get_anonid(inter.guild_id, inter.author.id)
    guildchannels = get_guildchannels(self.config, inter.guild_id)
    channeltype = guildchannels[channel.id]

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

      vetting = findvettingchannel(guildchannels)

      await inter.response.defer(ephemeral=True)

      await pendingconfession.generate_embed(
        anonid,
        vetting or channeltype.anonid,
        content,
        image.url if image else None
      )

      if vetting and 'feedback' in channeltype.name:
        if 'ConfessionsModeration' in self.bot.cogs:
          await self.bot.cogs['ConfessionsModeration'].send_vetting(
            inter, pendingconfession, inter.guild.get_channel(vetting)
          )
        else:
          await inter.response.send_message(self.babel(inter, 'no_moderation'), ephemeral=True)
        return

      await pendingconfession.send_confession(inter, True)

    else:
      await inter.response.send_modal(
        modal=self.ConfessionModal(self, inter, pendingconfession)
      )

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  @commands.slash_command(name='confess-to')
  async def confess_to(
    self,
    inter:disnake.GuildCommandInteraction,
    channel:str,
    content:Optional[str] = commands.Param(default=None, max_length=3900),
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
        results.append(f"{match[1].icon} #{match[0].name} ({match[0].id})")
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

    # Warn users when the channel list isn't complete
    local = isinstance(inter.author, disnake.Member)
    if not self.bot.is_ready() and not local:
      await inter.send(self.babel(inter, 'cachebuilding'), ephemeral=True)
    elif len(matches) == 0:
      await inter.send(
        self.babel(inter, 'inaccessiblelocal' if local else 'inaccessible'),
        ephemeral=True
      )
    # Send the list of channels, complete or not
    if len(matches) > 0:
      #BABEL: listtitlelocal,listtitle
      await inter.send((
        self.babel(inter, 'listtitlelocal' if local else 'listtitle') + '\n' +
        self.generate_list(inter.author, matches, vetting) +
        (
          # Hint on how to confess to a feedback channel
          '\n\n' + self.babel(inter, 'confess_to_feedback')
          if [m for m in matches if 'feedback' in m[1].name] else ''
        )
      ), ephemeral=True)


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(Confessions(bot))

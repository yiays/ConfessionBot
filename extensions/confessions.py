"""
  Confessions - Anonymous messaging cog
  Features: bot banning, vetting, image support
  Dependencies: Auth, Help
  Note: Contains generic command names like setup, list, and block
    As a result, this only really suits a singlular purpose bot
"""

from __future__ import annotations

import re, time
from typing import Optional, Union, TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy

from overlay.extensions.confessions_common import (
  ChannelType, ChannelSelectView, ConfessionData, NoMemberCacheError, Crypto, get_guildchannels
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
    if 'dm_notifications' not in self.config:
      self.config['dm_notifications'] = ''

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

  def generate_list(
    self,
    user:discord.User,
    matches:list[tuple[discord.TextChannel, ChannelType]],
    vetting:bool
  ) -> str:
    """ Returns a formatted list of available confession targets """

    targets = []
    for match in matches:
      targets.append(
        f'{match[1].icon} <#{match[0].id}>' +
        (' ('+match[0].guild.name+')' if not isinstance(user, discord.Member) else '')
      )
    vettingwarning = ('\n\n'+self.babel(user, 'vetting') if vetting else '')

    return '\n'.join(targets) + vettingwarning

  def scanguild(
    self, member:discord.Member
  ) -> tuple[list[tuple[discord.TextChannel, ChannelType]], bool]:
    """ Scans a guild for any targets that a member can use for confessions """

    matches:list[tuple[discord.TextChannel, ChannelType]] = []
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
      user:Union[discord.User, discord.Member]
    ) -> tuple[list[tuple[discord.TextChannel, ChannelType]], bool]:
    """
      List all available targets on a server for a member
      List all available targets on all mutual servers for a user
    """

    if isinstance(user, discord.Member):
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
    inter:discord.Interaction,
    channel_id:int
  ) -> Optional[discord.TextChannel]:
    """ Gracefully handles whenever a confession target isn't available """
    try:
      return await self.bot.fetch_channel(channel_id)
    except discord.Forbidden:
      await inter.response.send_message(
        self.babel(inter, 'missingchannelerr') + ' (fetch)',
        ephemeral=True
      )
      return None

  # Modals

  class ConfessionModal(discord.ui.Modal):
    """ Modal for completing an incomplete confession """
    def __init__(
      self,
      parent:"Confessions",
      origin:discord.Interaction,
      data:ConfessionData
    ):
      super().__init__(
        title=parent.babel(origin, 'editor_title'),
        custom_id="confession_modal",
        components=[
          discord.ui.TextInput(
            label=parent.babel(origin, 'editor_message_label'),
            placeholder=parent.babel(origin, 'editor_message_placeholder'),
            custom_id="content",
            style=discord.TextStyle.paragraph,
            min_length=1,
            max_length=3900
          )
        ]
      )

      self.parent = parent
      self.confession = data

    async def callback(self, inter:discord.Interaction):
      """ Send the completed confession """
      self.confession.set_content(inter.text_values['content'])

      #TODO: This is copy-pasted from /confess. Maybe this check should be in common?
      matches,_ = self.parent.listavailablechannels(inter.user)
      if self.confession.channeltype == ChannelType.unset():
        # User used /confess in the wrong channel, give them a chance to choose another
        await inter.response.send_message(
          self.parent.babel(inter, 'channelprompt') +
          (' '+self.parent.babel(inter, 'channelprompt_pager', page=1) if len(matches) > 25 else ''),
          view=ChannelSelectView(inter, self.parent, matches, confession=self.confession),
          ephemeral=True
        )
        return

      if vetting := await self.confession.check_vetting(inter):
        await inter.bot.cogs['ConfessionsModeration'].send_vetting(inter, self.confession, vetting)
        return
      if vetting is False:
        return
      await self.confession.send_confession(inter, success_message=True)

  #	Events

  @commands.Cog.listener('on_button_click')
  async def on_confession_review(self, inter:discord.Interaction):
    """ Notify users when handling vetting is not possible """
    if (
      inter.data.custom_id.startswith('pendingconfession_') and
      'ConfessionsModeration' not in self.bot.cogs
    ):
      await inter.response.send_message(self.babel(inter, 'no_moderation'))

  @commands.Cog.listener('on_message')
  async def confession_request(self, msg:discord.Message):
    """ Handle plain DM messages as confessions """
    if isinstance(msg.channel, discord.DMChannel) and msg.author != self.bot.user:
      if msg.channel in self.ignore:
        self.ignore.remove(msg.channel)
        return
      if msg.author in self.confession_cooldown and\
         self.confession_cooldown[msg.author] > time.time():
        return
      else:
        self.confession_cooldown[msg.author] = time.time() +\
          int(self.config.get('confession_cooldown', fallback=1))

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

      await msg.reply(
        self.babel(msg, 'channelprompt') +
        (' ' + self.babel(msg, 'channelprompt_pager', page=1) if len(matches) > 25 else ''),
        view=ChannelSelectView(msg, self, matches)
      )

  # Context menu commands

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  @commands.message_command(name="Confession Reply", dm_permission=False)
  async def confess_message(self, inter:discord.Interaction):
    """ Shorthand to start a confession modal in this channel """
    if inter.target.is_system():
      await inter.response.send_message(self.babel(inter, 'confession_reply_failed'), ephemeral=True)
      return
    await self.confess(inter, None, None, reference=inter.target)

  #	Slash commands

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  )
  async def confess(
    self,
    inter:discord.Interaction,
    content:Optional[str] = commands.Param(default=None, max_length=3900),
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
    channel = inter.channel
    if 'channel' in kwargs:
      channel = kwargs['channel']
    reference = None
    if 'reference' in kwargs:
      reference = kwargs['reference']

    pendingconfession = ConfessionData(self)
    pendingconfession.create(inter.user, channel, reference=reference)
    pendingconfession.set_content(content)
    if image:
      await inter.response.defer(ephemeral=True)
      await pendingconfession.add_image(attachment=image)

    # --- From here, all state should be in pendingconfession, not in parameters ---
    matches,_ = self.listavailablechannels(inter.user)
    if not matches:
      await inter.response.send_message(self.babel(inter, 'inaccessiblelocal'), ephemeral=True)
      return

    if pendingconfession.content or pendingconfession.file:
      if pendingconfession.channeltype == ChannelType.unset():
        # User used /confess in the wrong channel, give them a chance to choose another
        await inter.response.send_message(
          self.babel(inter, 'channelprompt') +
          (' ' + self.babel(inter, 'channelprompt_pager', page=1) if len(matches) > 25 else ''),
          view=ChannelSelectView(inter, self, matches, confession=pendingconfession),
          ephemeral=True
        )
        return
      if vetting := await pendingconfession.check_vetting(inter):
        await self.bot.cogs['ConfessionsModeration'].send_vetting(inter, pendingconfession, vetting)
        return
      if vetting is False:
        return
      await pendingconfession.send_confession(inter, success_message=True)

    else:
      await inter.response.send_modal(
        modal=self.ConfessionModal(self, inter, pendingconfession)
      )

  @commands.cooldown(1, 1, type=commands.BucketType.user)
  name='confess-to')
  async def confess_to(
    self,
    inter:discord.Interaction,
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
      if targetchannel := await self.safe_fetch_channel(inter, channel_id):
        await self.confess(inter, content, image, channel=targetchannel)
        return
    raise commands.BadArgument("Channel must be selected from the list")

  @confess_to.autocomplete('channel')
  async def channel_ac(self, inter:discord.Interaction, search:str):
    """ Lists available channels, allows searching by name """
    if not isinstance(inter.user, discord.Member):
      return [self.bot.babel(inter, 'error', 'noprivatemessage').replace('*','')]

    results = []
    matches, _ = self.scanguild(inter.user)
    for match in matches:
      if search in match[0].name:
        results.append(f"{match[1].icon} #{match[0].name} ({match[0].id})")
    return results[0:24] + (
      ['this list is incomplete, use /list to see all'] if len(results) > 25 else []
    )

  )
  async def list(self, inter:discord.Interaction):
    """
    List all anonymous channels available here
    """
    try:
      matches, vetting = self.listavailablechannels(inter.user)
    except NoMemberCacheError:
      await inter.response.send_message(self.babel(inter, 'dmconfessiondisabled'))
      return

    # Warn users when the channel list isn't complete
    local = isinstance(inter.user, discord.Member)
    if not self.bot.is_ready() and not local:
      await inter.response.send_message(self.babel(inter, 'cachebuilding'), ephemeral=True)
    elif len(matches) == 0:
      await inter.response.send_message(
        self.babel(inter, 'inaccessiblelocal' if local else 'inaccessible'),
        ephemeral=True
      )
    # Send the list of channels, complete or not
    if len(matches) > 0:
      #BABEL: listtitlelocal,listtitle
      await inter.response.send_message((
        self.babel(inter, 'listtitlelocal' if local else 'listtitle') + '\n' +
        self.generate_list(inter.user, matches, vetting) +
        (
          # Hint on how to confess to a feedback channel
          '\n\n' + self.babel(inter, 'confess_to_feedback')
          if [m for m in matches if 'feedback' in m[1].name] else ''
        )
      ), ephemeral=True)


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(Confessions(bot))

"""
  Confessions Setup - Easy setup experience for anonymous messaging
  Note: Contains generic command names like setup, list, and block
    As a result, this only really suits a singlular purpose bot
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
import disnake
from disnake.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy

from extensions.controlpanel import Toggleable, Stringable
from overlay.extensions.confessions_common import \
  ChannelType, ChannelSelectView, findvettingchannel, CHANNEL_ICONS


class ConfessionsSetup(commands.Cog):
  """ Configure anonymous messaging on your server """
  SCOPE = 'confessions'

  @property
  def config(self) -> SectionProxy:
    """ Shorthand for self.bot.config[scope] """
    return self.bot.config[self.SCOPE]

  def babel(self, target:Resolvable, key:str, **values: dict[str, str | bool]) -> list[str]:
    """ Shorthand for self.bot.babel(scope, key, **values) """
    return self.bot.babel(target, self.SCOPE, key, **values)

  def __init__(self, bot:MerelyBot):
    self.bot = bot

    # ensure config file has required data
    if not bot.config.has_section(self.SCOPE):
      bot.config.add_section(self.SCOPE)
    if 'pfpgen_url' not in self.config or self.config['pfpgen_url'] == '':
      self.config['pfpgen_url'] = ''
      print(
        "WARNING: You don't have a pfp generator. Profile pictures in webhook mode will be blank."
      )
    if 'confessions' not in bot.config['extensions']:
      raise Warning("Without Confessions enabled, users won't be able to confess!")

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

  class SetupView(ChannelSelectView):
    """ Configure channels and shortcuts to configure guild settings """
    current_channel: disnake.TextChannel | None = None
    current_mode: ChannelType | None = None

    def __init__(
      self,
      inter:disnake.GuildCommandInteraction,
      parent:ConfessionsSetup
    ):
      # Find channel types in config
      matches = self.regenerate_matches(parent, inter.guild)
      super().__init__(inter, parent, matches)
      self.channel_selector.callback = self.channel_selector_override
      self.channel_selector.placeholder = self.parent.babel(inter, 'setup_placeholder')
      self.mode_selector.options = [
        disnake.SelectOption(
          label=mode.name,
          value=mode.value,
          emoji=CHANNEL_ICONS[mode.value]
        )
        for mode in ChannelType
      ]
      self.remove_item(self.send_button)
      if 'ControlPanel' in parent.bot.cogs:
        linkbutton = disnake.ui.Button(
          custom_id='controlpanel',
          label=parent.babel(inter, 'setup_controlpanel'),
          style=disnake.ButtonStyle.grey,
          emoji='💡',
          row=4
        )
        linkbutton.callback = self.controlpanel_shortcut
        self.add_item(linkbutton)

    def regenerate_matches(
      self, parent:ConfessionsSetup, guild:disnake.Guild
    ) -> tuple[disnake.TextChannel, ChannelType]:
      if len(guild.channels) == 0:
        return []
      botmember = guild.get_member(parent.bot.user.id)
      confid = f'{guild.id}_'
      out = [
        (c, ChannelType(parent.config.getint(confid + str(c.id), fallback=ChannelType.unset.value)))
        for c in guild.channels if isinstance(c, disnake.TextChannel)
        and c.permissions_for(botmember).read_messages
      ]
      out.sort(key=lambda t: (t[0].category.position if t[0].category else 0, t[0].position))
      return out

    async def controlpanel_shortcut(self, inter:disnake.MessageInteraction):
      if 'ControlPanel' not in self.parent.bot.cogs:
        raise Exception("ControlPanel was unloaded")
      await self.parent.bot.cogs['ControlPanel'].controlpanel(inter)

    async def set(
      self, inter:disnake.MessageInteraction, channel:disnake.TextChannel, mode:ChannelType
    ) -> bool:
      """ Tries to change settings as requested and handles all rules and requirements """
      configkey = f'{channel.guild.id}_{channel.id}'
      wastype = self.parent.config.getint(configkey, fallback=ChannelType.unset.value)
      if mode == ChannelType.unset:
        if wastype == ChannelType.unset:
          await inter.send(self.parent.babel(inter, 'unsetfailure'), ephemeral=True)
          return False
        self.parent.bot.config.remove_option(self.SCOPE, configkey)
      elif mode == ChannelType.vetting:
        if 'ConfessionsModeration' not in self.parent.bot.cogs:
          await inter.send(self.parent.babel(inter, 'no_moderation'), ephemeral=True)
          return False
        if findvettingchannel(self.parent.config, channel.guild):
          await inter.send(self.parent.babel(inter, 'singlechannel'), ephemeral=True)
          return False
      if wastype == mode:
        await inter.send(self.parent.babel(inter, 'no_change'), ephemeral=True)
        return False
      self.parent.config[configkey] = str(mode.value)
      self.parent.bot.config.save()

      #BABEL: setsuccess#,unsetsuccess#
      modestring = (
        f'setsuccess{mode.value}' if mode > ChannelType.unset else f'unsetsuccess{wastype}'
      )
      #BABEL: setundo,unsetundo
      await channel.send(
        self.parent.babel(inter.guild, modestring) + ' ' +
        self.parent.babel(inter.guild, 'setundo' if mode > ChannelType.unset else 'unsetundo') +
        ('\n'+self.parent.babel(inter.guild, 'setcta') if mode > ChannelType.unset else '')
      )
      return True

    async def update_state(self, inter:disnake.MessageInteraction):
      #BABEL: state_desc_unset,state_desc_#
      modename = self.current_mode.name if isinstance(self.current_mode, ChannelType) else 'unset'
      modeval = (
        self.current_mode.value if isinstance(self.current_mode, ChannelType) else ChannelType.unset
      )
      for option in self.channel_selector.options:
        option.default = bool(
          int(option.value) == self.current_channel.id if self.current_channel else False
        )
      for option in self.mode_selector.options:
        option.default = (
          int(option.value) == modeval if isinstance(self.current_mode, ChannelType) else False
        )
      if self.current_channel is None:
        await inter.response.edit_message(self.parent.babel(inter, 'setup_start'))
        return
      self.timeout = 180
      descmode = 'state_desc_' + (str(modeval) if modeval != ChannelType.unset else 'unset')
      await inter.response.edit_message((
        self.parent.babel(inter, 'setup_state',
                          channel=self.current_channel.mention if self.current_channel else None,
                          state=modename)
        + '\n' + self.parent.babel(inter, descmode)
        + '\n' + self.parent.babel(inter, 'state_cta')
      ), view=self)

    async def channel_selector_override(self, inter:disnake.MessageInteraction):
      """ Update the message to preview the selected target """
      if inter.user != self.origin.author:
        await inter.send(self.parent.bot.babel(inter, 'error', 'wronguser'))
        return
      self.send_button.disabled = False
      try:
        self.current_channel = await self.parent.bot.fetch_channel(int(inter.values[0]))
      except disnake.Forbidden:
        self.current_channel = None
        self.current_mode = None
        await self.update_state(inter)
        await inter.send(
          content=self.parent.babel(inter, 'setup_state_missing', channel_id=inter.values[0]),
          ephemeral=True
        )
        return
      c = self.current_channel
      self.current_mode = ChannelType(
        self.parent.config.getint(f'{c.guild.id}_{c.id}', fallback=ChannelType.unset)
      )
      await self.update_state(inter)

    @disnake.ui.select()
    async def mode_selector(self, _:disnake.ui.Select, inter:disnake.MessageInteraction):
      if inter.user != self.origin.author:
        await inter.send(self.parent.bot.babel(inter, 'error', 'wronguser'))
        return
      if not self.current_channel:
        await inter.send(
          self.parent.babel(inter, 'setup_channel_required'), ephemeral=True
        )
        return

      if await self.set(inter, self.current_channel, ChannelType(int(inter.values[0]))):
        self.current_mode = ChannelType(int(inter.values[0]))
        self.matches = self.regenerate_matches(self.parent, inter.guild)
        self.update_list()
        await self.update_state(inter)

    async def on_timeout(self):
      for component in self.children:
        if isinstance(component, (disnake.ui.Button, disnake.ui.Select)):
          component.disabled = True
      msg = await self.origin.original_message()
      await msg.edit(view=self)

  # Events

  @commands.Cog.listener('on_guild_leave')
  async def guild_cleanup(self, guild:disnake.Guild):
    """ Automatically remove data related to a guild on removal """
    for option in self.config:
      if option.startswith(str(guild.id)+'_'):
        self.bot.config.remove_option(self.SCOPE, option)
    self.bot.config.save()

  @commands.Cog.listener('on_guild_channel_delete')
  async def channel_cleanup(self, channel:disnake.TextChannel):
    """ Automatically remove data related to a channel on delete """
    for option in self.config:
      if option == str(channel.guild.id)+'_'+str(channel.id):
        self.bot.config.remove_option(self.SCOPE, option)
        break
    self.bot.config.save()

  # Commands

  @commands.default_member_permissions(manage_channels=True)
  @commands.slash_command(dm_permission=False)
  async def setup(self, inter:disnake.GuildCommandInteraction):
    """
      Change confessions settings on this server
    """
    await inter.response.send_message(
      self.babel(inter, 'setup_start'), view=self.SetupView(inter, self), ephemeral=True
    )

  @commands.default_member_permissions(moderate_members=True)
  @commands.slash_command(dm_permission=False)
  async def shuffle(self, inter:disnake.GuildCommandInteraction):
    """
      Change all anon-ids on a server
    """
    if str(inter.guild.id)+'_banned' in self.config:
      await inter.send(self.babel(inter, 'shufflebanresetwarning'))

      def check(m:disnake.Message):
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

  @commands.default_member_permissions(administrator=True)
  @commands.slash_command(dm_permission=False)
  async def imagesupport(self, inter:disnake.GuildCommandInteraction):
    """
      Enable or disable images in confessions
    """
    #TODO: delete this in time as users adjust
    if 'Help' in self.bot.cogs:
      await self.bot.cogs['Help'].help(inter, 'imagesupport', ephemeral=True)

  @commands.default_member_permissions(administrator=True)
  @commands.slash_command(dm_permission=False)
  async def botmod(self, inter:disnake.GuildCommandInteraction):
    """
      Grant or take away botmod powers from a user
    """
    #TODO: delete this in time as users adjust
    await inter.response.send_message(self.babel(inter, 'botmod_removed'))


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(ConfessionsSetup(bot))

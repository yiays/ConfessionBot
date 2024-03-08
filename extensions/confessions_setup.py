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
from overlay.extensions.confessions_common import ChannelType, findvettingchannel


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

  @commands.default_member_permissions(administrator=True)
  @commands.slash_command(dm_permission=False)
  async def set(
    self,
    inter:disnake.GuildCommandInteraction,
    mode:ChannelType
  ):
    """
      Set a channel for use with ConfessionBot

      Parameters
      ----------
      mode: The channel type, use `/help set` for an explaination of types
    """
    if mode == ChannelType.none:
      wastype = int(self.config.get(
        f'{inter.guild.id}_{inter.channel.id}', fallback=ChannelType.none
      ))
      if wastype == ChannelType.none:
        await inter.send(self.babel(inter, 'unsetfailure'))
        return
      self.bot.config.remove_option(self.SCOPE, str(inter.guild.id)+'_'+str(inter.channel.id))
    elif mode == ChannelType.vetting:
      if 'ConfessionsModeration' not in self.bot.cogs:
        await inter.send(self.babel(inter, 'no_moderation'))
        return
      if findvettingchannel(self.config, inter.guild):
        await inter.send(self.babel(inter, 'singlechannel'))
        return
      self.config[str(inter.guild.id)+'_'+str(inter.channel.id)] = str(mode)
    else:
      self.config[str(inter.guild.id)+'_'+str(inter.channel.id)] = str(mode)
    self.bot.config.save()

    #BABEL: setsuccess#,unsetsuccess#
    modestring = (
      'setsuccess'+str(mode) if mode > ChannelType.none else 'unsetsuccess'+str(wastype)
    )
    #BABEL: setundo,unsetundo
    await inter.send(
      self.babel(inter, modestring) + ' ' +
      self.babel(inter, 'setundo' if mode > ChannelType.none else 'unsetundo') +
      ('\n'+self.babel(inter, 'setcta') if mode > ChannelType.none else '')
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
      await self.bot.cogs['Help'].slash_help(inter, 'imagesupport', ephemeral=True)

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

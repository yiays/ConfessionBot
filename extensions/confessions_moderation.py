"""
  Confessions Moderation - Easy mod tools for anonymous messaging
  Note: Contains generic command names like block
    As a result, this only really suits a singlular purpose bot
"""
from __future__ import annotations

import asyncio, re
from typing import Optional, TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

if TYPE_CHECKING:
  from main import MerelyBot
  from babel import Resolvable
  from configparser import SectionProxy
  from overlay.extensions.confessions import Confessions
  from overlay.extensions.confessions_common import Crypto

from overlay.extensions.confessions_common import (
  ConfessionData, CorruptConfessionDataException, safe_fetch_channel
)


class ConfessionsModeration(commands.Cog):
  """ Moderate anonymous messaging on your server """
  SCOPE = 'confessions'

  @property
  def config(self) -> SectionProxy:
    """ Shorthand for self.bot.config[scope] """
    return self.bot.config[self.SCOPE]

  def babel(self, target:Resolvable, key:str, **values: dict[str, str | bool]) -> str:
    """ Shorthand for self.bot.babel(scope, key, **values) """
    return self.bot.babel(target, self.SCOPE, key, **values)

  @property
  def crypto(self) -> "Crypto":
    if 'Confessions' not in self.bot.cogs:
      raise Exception(
        "Module `confessions` was unloaded when it's still required by `confessions_moderation`!"
      )
    return self.bot.cogs['Confessions'].crypto

  def __init__(self, bot:MerelyBot):
    self.bot = bot
    self.button_lock:list[str] = []
    self.jump_url_pattern = re.compile(r"https://discord\.com/channels/(\d+)/(\d+)/(\d+)")

    if not bot.config.getboolean('extensions', 'confessions', fallback=False):
      raise Exception("Module `confessions` must be enabled!")

    self.report = app_commands.ContextMenu(
      name=app_commands.locale_str('command_Confession_Report', scope=self.SCOPE),
      allowed_contexts=app_commands.AppCommandContext(guild=True, private_channel=False),
      allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
      callback=self.report_callback
    )
    bot.tree.add_command(self.report)

  def cog_unload(self):
    self.bot.tree.remove_command(self.report.qualified_name, type=self.report.type)

  # Context menu commands

  @commands.cooldown(1, 60)
  async def report_callback(self, inter:discord.Interaction, message:discord.Message):
    """ Reports a confession to the bot owners """
    if (
      (
        message.author == self.bot.user and
        len(message.embeds) > 0 and
        message.embeds[0].author is not None and
        message.embeds[0].author.name.startswith('Anon')
      ) or (
        message.application_id == self.bot.application_id and
        ('[Anon-' in message.author.name or '[Anon]' in message.author.name)
      )
    ):
      await inter.response.send_message(
        content=self.babel(inter, 'report_prep', msgurl=message.jump_url),
        view=self.ReportView(self, message, inter),
        ephemeral=True,
        suppress_embeds=True
      )
      return

    await inter.response.send_message(
      self.babel(inter, 'report_invalid_message'),
      ephemeral=True
    )

  # Utility functions

  async def send_vetting(
    self,
    inter:discord.Interaction,
    data:"ConfessionData",
    vettingchannel:discord.TextChannel
  ):
    """
      Send confession to a vetting channel for approval
      Checks are performed at this stage
    """
    preface = self.babel(vettingchannel.guild, 'vetmessagecta', channel=data.targetchannel.mention)
    view = self.PendingConfessionView(self, data)
    success = await data.send_confession(
      inter,
      channel=vettingchannel,
      webhook_override=False,
      preface_override=preface,
      view=view
    )

    if success:
      await inter.followup.send(
        self.babel(inter, 'confession_vetting', channel=data.targetchannel.mention),
        ephemeral=True
      )

  # Views

  class PendingConfessionView(discord.ui.View):
    """ Asks moderators to approve or deny a confession as a part of vetting """
    def __init__(self, parent:ConfessionsModeration, pendingconfession:"ConfessionData"):
      super().__init__(timeout=None)

      guild = pendingconfession.targetchannel.guild
      data = pendingconfession.store()
      self.add_item(discord.ui.Button(
        label=parent.babel(guild, 'vetting_approve_button'),
        emoji='✅',
        style=discord.ButtonStyle.blurple,
        custom_id=f"pendingconfession_approve_{data}"
      ))

      self.add_item(discord.ui.Button(
        label=parent.babel(guild, 'vetting_deny_button'),
        emoji='❎',
        style=discord.ButtonStyle.danger,
        custom_id=f"pendingconfession_deny_{data}"
      ))

  class ReportView(discord.ui.View):
    """ Provides all the guidance needed before a user reports a confession """
    def __init__(
        self,
        parent:ConfessionsModeration,
        message: discord.Message,
        origin: discord.Interaction
    ):
      super().__init__(timeout=300)

      self.parent = parent
      self.message = message
      self.origin = origin

      self.report_button.label = parent.babel(origin, 'report_button')

      asyncio.ensure_future(self.enable_button())

    async def enable_button(self):
      """ Waits 5 seconds before enabling the report button to encourage the user to read """
      await asyncio.sleep(5)
      self.report_button.disabled = False
      await self.origin.edit_original_response(view=self)

    @discord.ui.button(
      disabled=True, style=discord.ButtonStyle.gray, emoji='➡️', custom_id='confessionreport_confirm'
    )
    async def report_button(self, inter:discord.Interaction, _:discord.Button):
      """ On click of continue button """
      await inter.response.send_modal(
        self.parent.ReportModal(self.parent, self.message, self.origin)
      )
      await inter.delete_original_response()

    async def on_timeout(self):
      try:
        await self.origin.delete_original_response()
      except discord.HTTPException:
        pass # Message was probably dismissed, don't worry about it

  # Modals

  class ReportModal(discord.ui.Modal):
    """ Confirm user input before sending a report """
    def __init__(
        self,
        parent:"Confessions",
        message: discord.Message,
        origin: discord.Interaction
    ):
      super().__init__(
        title=parent.babel(origin, 'report_title'),
        custom_id=f'report_{message.id}',
        timeout=600
      )
      self.report_reason = discord.ui.TextInput(
        label=parent.babel(origin, 'report_field'),
        placeholder=parent.babel(origin, 'report_placeholder'),
        custom_id='report_reason',
        style=discord.TextStyle.paragraph,
        min_length=1
      )
      self.add_item(self.report_reason)

      self.parent = parent
      self.message = message
      self.origin = origin

    async def on_submit(self, inter: discord.Interaction):
      """ Send report to mod channel as configured """
      if self.parent.config['report_channel']:
        reportchannel = await safe_fetch_channel(
          self.parent, inter, int(self.parent.config.get('report_channel'))
        )
        if reportchannel is None:
          await inter.response.send_message(
            self.parent.babel(inter, 'report_failed')
          )
          return
        embed:discord.Embed
        if len(self.message.embeds) > 0:
          embed = self.message.embeds[0]
        else:
          embed = discord.Embed(description=f'**{self.message.author.name}** {self.message.content}')
        await reportchannel.send(
          self.parent.babel(
            reportchannel.guild, 'new_report',
            server=f'{inter.guild.name} ({inter.guild.id})',
            user=f'{inter.user.mention} ({inter.user.name}#{inter.user.discriminator})',
            reason=self.report_reason.value
          ),
          embed=embed,
        )
        await inter.response.send_message(
          self.parent.babel(inter, 'report_success'),
          ephemeral=True,
          suppress_embeds=True
        )

  # Events

  @commands.Cog.listener('on_interaction')
  async def on_confession_review(self, inter:discord.Interaction):
    """ Handle approving and denying confessions """
    if inter.type != discord.InteractionType.component:
      return
    custom_id = inter.data.get('custom_id')
    if not custom_id.startswith('pendingconfession_'):
      return
    if custom_id in self.button_lock:
      await inter.response.send_message(
        "Somebody else has already pressed this button!", ephemeral=True
      )
      return

    await inter.response.defer()
    self.button_lock.append(custom_id)
    accepted = False
    try:
      if custom_id.startswith('pendingconfession_approve_'):
        accepted = True
        pendingconfession = ConfessionData(self)
        await pendingconfession.from_binary(self.crypto, custom_id[26:])
        pendingconfession.set_content(embed=inter.message.embeds[0])
        if pendingconfession.reference is None:
          # Try and recover reference if it's lost
          if match := self.jump_url_pattern.search(inter.message.content):
            _, channel_id, message_id = map(int, match.groups())
            channel = inter.guild.get_channel(channel_id)
            reference = channel.get_partial_message(message_id)
            pendingconfession.create(reference=reference)
      elif custom_id.startswith('pendingconfession_deny_'):
        pendingconfession = ConfessionData(self)
        await pendingconfession.from_binary(self.crypto, custom_id[23:])
      else:
        self.button_lock.remove(custom_id)
        raise Exception("Unknown button action", custom_id)
    except CorruptConfessionDataException:
      await inter.followup.send(self.babel(inter, 'vetcorrupt'))
      self.button_lock.remove(custom_id)
      return
    except (discord.NotFound, discord.Forbidden):
      if accepted:
        await inter.followup.send(self.babel(inter, 'vettingrequiredmissing'))
      self.button_lock.remove(custom_id)
      return

    if accepted:
      try:
        if inter.message.embeds[0].image:
          await pendingconfession.add_image(url=inter.message.embeds[0].image.url)
        elif (
          len(inter.message.attachments) and
          inter.message.attachments[0].content_type.startswith('image')
        ):
          await pendingconfession.add_image(attachment=inter.message.attachments[0])
        if not await pendingconfession.send_confession(inter, perform_checks=False):
          self.button_lock.remove(custom_id)
          return
      except Exception as e:
        self.button_lock.remove(custom_id)
        raise e

    metadata = {'user':inter.user.mention, 'channel':pendingconfession.targetchannel.mention}
    if accepted:
      msg = self.babel(inter.guild, 'vetaccepted', **metadata)
    else:
      msg = self.babel(inter.guild, 'vetdenied', **metadata)
    try:
      await inter.message.edit(content=msg, view=None)
    except Exception as e:
      self.button_lock.remove(custom_id)
      raise e
    self.button_lock.remove(custom_id)

    #BABEL: confession_vetting_accepted,confession_vetting_denied
    content = self.babel(
      pendingconfession.author,
      'confession_vetting_accepted' if accepted else 'confession_vetting_denied',
      channel=f"<#{pendingconfession.targetchannel.id}>"
    )
    if str(pendingconfession.author.id) not in self.config.get('dm_notifications', '').split(','):
      try:
        if not pendingconfession.author.dm_channel:
          await pendingconfession.author.create_dm()
        await pendingconfession.author.send(content)
      except discord.Forbidden:
        pass

  # Commands

  @app_commands.command(
    name=app_commands.locale_str('command_block', scope=SCOPE),
    description=app_commands.locale_str('command_block_desc', scope=SCOPE)
  )
  @app_commands.describe(
    anonid=app_commands.locale_str('command_block_anonid_desc', scope=SCOPE),
    unblock=app_commands.locale_str('command_block_unblock_desc', scope=SCOPE)
  )
  @app_commands.allowed_contexts(guilds=True, private_channels=False)
  @app_commands.default_permissions(moderate_members=True)
  async def block(
    self,
    inter:discord.Interaction,
    anonid:Optional[app_commands.Range[str, 6, 6]] = None,
    unblock:Optional[bool] = False
  ):
    """
      Block or unblock anon-ids from confessing
    """
    banlist_raw = self.config.get(f'{inter.guild.id}_banned', fallback='')
    banlist = banlist_raw.split(',')
    if anonid is None:
      if not banlist_raw:
        await inter.response.send_message(self.babel(inter, 'emptybanlist'))
        return
      printedlist = '\n```\n' + ('\n'.join(banlist)) + '```'
      await inter.response.send_message(self.babel(inter, 'banlist') + printedlist)
      return

    anonid = anonid.lower()
    try:
      int(anonid, 16)
    except ValueError:
      await inter.response.send_message(self.babel(inter, 'invalidanonid'))
      return
    if anonid in banlist and not unblock:
      await inter.response.send_message(self.babel(inter, 'doublebananonid'))
      return
    #BABEL: nomatchanonid
    #TODO: keeping this string around in case a new way to check is found
    # will probably involve storing / retreiving recent anon-ids

    if unblock:
      fullid = [i for i in banlist if anonid in i][0]
      self.config[str(inter.guild.id)+'_banned'] = banlist_raw.replace(fullid+',','')
    else:
      self.config[str(inter.guild.id)+'_banned'] = banlist_raw + anonid + ','
    self.bot.config.save()

    #BABEL: unbansuccess,bansuccess
    await inter.response.send_message(
      self.babel(inter, ('un' if unblock else '')+'bansuccess', user=anonid)
    )


async def setup(bot:MerelyBot):
  """ Bind this cog to the bot """
  await bot.add_cog(ConfessionsModeration(bot))

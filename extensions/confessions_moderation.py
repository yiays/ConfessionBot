"""
  Confessions Moderation - Easy mod tools for anonymous messaging
  Note: Contains generic command names like block
    As a result, this only really suits a singlular purpose bot
"""
from __future__ import annotations

import asyncio
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

from overlay.extensions.confessions_common import ConfessionData, CorruptConfessionDataException


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

    if 'confessions' not in bot.config['extensions']:
      raise Exception("Module `confessions` must be enabled!")

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
      await inter.response.send_message(
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
      await self.origin.edit_original_response(view=self, suppress_embeds=True)

    @discord.ui.button(disabled=True, style=discord.ButtonStyle.gray, emoji='➡️')
    async def report_button(self, _:discord.Button, inter:discord.Interaction):
      """ On click of continue button """
      await inter.response.send_modal(
        self.parent.ReportModal(self.parent, self.message, self.origin)
      )
      await inter.delete_original_response()

  # Modals

  class ReportModal(discord.ui.Modal):
    """ Confirm user input before sending a report """
    def __init__(
        self,
        confessions:"Confessions",
        message: discord.Message,
        origin: discord.Interaction
    ):
      super().__init__(
        title=confessions.babel(origin, 'report_title'),
        custom_id=f'report_{message.id}',
        components=[
          discord.ui.TextInput(
            label=confessions.babel(origin, 'report_field'),
            placeholder=confessions.babel(origin, 'report_placeholder'),
            custom_id='report_reason',
            style=discord.TextStyle.paragraph,
            min_length=1
          )
        ],
        timeout=600
      )

      self.confessions = confessions
      self.message = message
      self.origin = origin

    async def callback(self, inter: discord.Interaction):
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
        embed:discord.Embed
        if len(self.message.embeds) > 0:
          embed = self.message.embeds[0]
        else:
          embed = discord.Embed(description=f'**{self.message.author.name}** {self.message.content}')
        await reportchannel.send(
          self.confessions.babel(
            reportchannel.guild, 'new_report',
            server=f'{inter.guild.name} ({inter.guild.id})',
            user=f'{inter.user.mention} ({inter.user.name}#{inter.user.discriminator})',
            reason=inter.text_values['report_reason']
          ),
          embed=embed,
        )
        await inter.response.send_message(
          self.confessions.babel(inter, 'report_success'),
          ephemeral=True,
          suppress_embeds=True
        )

  # Events

  @commands.Cog.listener('on_button_click')
  async def on_confession_review(self, inter:discord.Interaction):
    """ Handle approving and denying confessions """
    if not inter.data.custom_id.startswith('pendingconfession_'):
      return
    if inter.data.custom_id in self.button_lock:
      # The button was double-pressed. Ignore.
      return

    await inter.response.defer()
    self.button_lock.append(inter.data.custom_id)
    try:
      if inter.data.custom_id.startswith('pendingconfession_approve_'):
        pendingconfession = ConfessionData(self)
        await pendingconfession.from_binary(self.crypto, inter.data.custom_id[26:])
        pendingconfession.set_content(embed=inter.message.embeds[0])
        accepted = True
      elif inter.data.custom_id.startswith('pendingconfession_deny_'):
        pendingconfession = ConfessionData(self)
        await pendingconfession.from_binary(self.crypto, inter.data.custom_id[23:])
        accepted = False
      else:
        self.button_lock.remove(inter.data.custom_id)
        print(f"WARN: Unknown button action '{inter.data.custom_id}'!")
        return
    except CorruptConfessionDataException:
      await inter.response.send_message(self.babel(inter, 'vetcorrupt'))
      self.button_lock.remove(inter.data.custom_id)
      return
    except (discord.NotFound, discord.Forbidden):
      self.button_lock.remove(inter.data.custom_id)
      if accepted:
        await inter.response.send_message(self.babel(
          inter, 'vettingrequiredmissing', channel=f"<#{pendingconfession.targetchannel.id}>"
        ))
        return

    if accepted:
      if inter.message.embeds[0].image:
        await pendingconfession.add_image(url=inter.message.embeds[0].image.url)
      elif (
        len(inter.message.attachments) and
        inter.message.attachments[0].content_type.startswith('image')
      ):
        await pendingconfession.add_image(attachment=inter.message.attachments[0])
      await pendingconfession.send_confession(inter, perform_checks=False)

    metadata = {'user':inter.user.mention, 'channel':pendingconfession.targetchannel.mention}
    if accepted:
      msg = self.babel(inter.guild, 'vetaccepted', **metadata)
    else:
      msg = self.babel(inter.guild, 'vetdenied', **metadata)
    await inter.message.edit(content=msg, view=None)
    self.button_lock.remove(inter.data.custom_id)

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

  # Context menu commands

  @commands.cooldown(1, 60)
  @commands.message_command(name="Report confession", dm_permission=False)
  async def report(self, inter:discord.Interaction):
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

  # Commands

  @app_commands.command()
  @app_commands.allowed_contexts(guilds=True, private_channels=False)
  @app_commands.default_permissions(moderate_members=True)
  async def block(
    self,
    inter:discord.Interaction,
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
    banlist = self.config.get(f'{inter.guild.id}_banned', fallback='')
    banlist_split = banlist.split(',')
    if anonid is None:
      if banlist_split:
        printedlist = '\n```'+'\n'.join(banlist_split)+'```'
        await inter.response.send_message(self.babel(inter, 'banlist') + printedlist)
      else:
        await inter.response.send_message(self.babel(inter, 'emptybanlist'))
      return

    anonid = anonid.lower()
    if len(anonid) > 6:
      anonid = anonid[-6:]
    try:
      int(anonid, 16)
    except ValueError:
      await inter.response.send_message(self.babel(inter, 'invalidanonid'))
      return
    if anonid in banlist_split and not unblock:
      await inter.response.send_message(self.babel(inter, 'doublebananonid'))
      return
    #BABEL: nomatchanonid
    #TODO: keeping this string around in case a new way to check is found
    # will probably involve storing / retreiving recent anon-ids

    if unblock:
      fullid = [i for i in banlist_split if anonid in i][0]
      self.config[str(inter.guild.id)+'_banned'] = banlist.replace(fullid+',','')
    else:
      self.config[str(inter.guild.id)+'_banned'] = banlist + anonid + ','
    self.bot.config.save()

    #BABEL: unbansuccess,bansuccess
    await inter.response.send_message(
      self.babel(inter, ('un' if unblock else '')+'bansuccess', user=anonid)
    )


def setup(bot:MerelyBot) -> None:
  """ Bind this cog to the bot """
  bot.add_cog(ConfessionsModeration(bot))

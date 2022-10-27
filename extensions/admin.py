"""
  Admin - Powerful commands for administrators
  Features: clean, purge, and autodelete
  Dependancies: Auth
"""

from enum import Enum
from typing import Optional
import disnake, asyncio
from disnake.ext import commands

class JanitorAction(int, Enum):
  enable = 0
  disable = 1

class Admin(commands.Cog):
  """ Admin tools """
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'admin'")
    # ensure config file has required data
    if not bot.config.has_section('admin'):
      bot.config.add_section('admin')

  def check_delete(self, message:disnake.Message, strict:bool=False):
    """ Criteria for message deletion """
    return (
      strict or
      (
        message.author==self.bot.user or
        message.content.startswith('<@'+str(self.bot.user.id)+'>') or
        message.type == disnake.MessageType.pins_add
      )
    )

  @commands.Cog.listener("on_message")
  async def janitor_autodelete(self, message):
    """janitor service, deletes messages after 30 seconds"""
    if f"{message.channel.id}_janitor" in self.bot.config['admin']:
      strict = self.bot.config.getint('admin', f"{message.channel.id}_janitor")
      if self.check_delete(message, strict):
        await asyncio.sleep(30)
        await message.delete()

  @commands.slash_command()
  async def janitor(self, inter:disnake.GuildCommandInteraction, action:JanitorAction, strict:bool=False):
    """
      Add or remove janitor from this channel. Janitor deletes messages after 30 seconds

      Parameters:
      -----------
      action: Choose whether to have janitor enabled or disabled in this channel
      strict: A strict janitor, when enabled, deletes all messages by all users
    """

    self.bot.cogs['Auth'].admins(inter)

    if action == JanitorAction.enable:
      self.bot.config['admin'][f'{inter.channel.id}_janitor'] = '1' if strict else '0'
      self.bot.config.save()
      await inter.send(self.bot.babel(inter, 'admin', 'janitor_set_success'))
      
    if action == JanitorAction.disable:
      self.bot.config.remove_option('admin', f'{inter.channel.id}_janitor')
      self.bot.config.save()
      await inter.send(self.bot.babel(inter, 'admin', 'janitor_unset_success'))

  @commands.slash_command()
  async def clean(
    self,
    inter:disnake.GuildCommandInteraction,
    number:Optional[int]=commands.Param(None, gt=0, le=10000),
    clean_to:Optional[disnake.Message]=None,
    strict:bool=False
  ):
    """
      Clean messages from this channel. By default, this only deletes messages to and from this bot.

      Parameters:
      -----------
      number: The number of messages to search through, defaults to 50
      clean_to: Searches through message history until this message is reached
      strict: A strict clean, when enabled, deletes all messages by all users
    """

    self.bot.cogs['Auth'].mods(inter)

    try:
      await inter.response.defer(with_message=True)
      if clean_to:
        deleted = await inter.channel.purge(
          limit=number if number else 1000,
          check=lambda m: self.check_delete(m, strict),
          before=await inter.original_message(),
          after=clean_to
        )
      else:
        deleted = await inter.channel.purge(
          limit=number if number else 50,
          check=lambda m: self.check_delete(m, strict),
          before=await inter.original_message()
        )
      await inter.send(self.bot.babel(inter, 'admin', 'clean_success', n=len(deleted)))
    except disnake.errors.Forbidden:
      await inter.send(self.bot.babel(inter, 'admin', 'clean_failed'))

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Admin(bot))

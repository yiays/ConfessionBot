"""
  System - Bot management commands
  Dependancies: Auth
"""
from enum import Enum
from glob import glob
import asyncio
from typing import Optional
import disnake
from disnake.ext import commands

class Actions(int, Enum):
  """ Actions that can be performed on an option """
  list = 0
  load = 1
  unload = 2
  reload = 3
  enable = 4
  disable = 5

class System(commands.Cog):
  """commands involved in working with a discord bot"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'admin'")

    guilds = bot.config['auth']['botadmin_guilds']
    botadmin_guilds = [int(guild) for guild in guilds.split(' ')]
    self.module.guild_ids = botadmin_guilds
    self.die.guild_ids = botadmin_guilds

  @commands.slash_command()
  async def module(
    self,
    inter:disnake.ApplicationCommandInteraction,
    action:Actions,
    module:Optional[str] = None
  ):
    """
    Manage modules of the bot in real time

    Parameters
    ----------
    Action: The action you want to perform
    Module: The target cog which will be affected, leave empty for a list of loaded Cogs
    """

    self.bot.cogs['Auth'].superusers(inter)

    if not self.bot.config.getboolean('extensions', 'allow_reloading'):
      await inter.send("Reloading of cogs has been disabled in the config.", ephemeral=True)
      return

    active_extensions = [
      e.replace('extensions.','').strip('_') for e in self.bot.extensions.keys()
    ] + ['config', 'babel']
    if module is None:
      await inter.send(
        self.bot.babel(inter, 'main', 'extensions_list', list='\n'.join(active_extensions)),
        ephemeral=True
      )
      return
    module = module.lower()

    ext = None
    if module in active_extensions or action==Actions.load:
      if module=='config':
        self.bot.config.reload()
        await inter.send(
          self.bot.babel(inter, 'main', 'extension_reload_success', extension=module),
          ephemeral=True
        )
        return
      elif module=='babel':
        self.bot.babel.reload()
        await inter.send(
          self.bot.babel(inter, 'main', 'extension_reload_success', extension=module),
          ephemeral=True
        )
        return

      if action == Actions.load:
        for f in glob('extensions/*.py'):
          if f[11:-3].strip('_') == module:
            ext = f[:-3].replace('/','.')
      else:
        extcandidate = [
          ext for ext in self.bot.extensions.keys()
          if ext.replace('extensions.','').strip('_') == module
        ]
        if extcandidate:
          ext = extcandidate[0]

      if ext:
        if action == Actions.enable:
          self.bot.config['extensions'][module] = 'True'
          self.bot.config.save()
          await inter.send(
            self.bot.babel(inter, 'main', 'extension_enable_success', extension=module),
            ephemeral=True
          )
        elif action == Actions.disable:
          self.bot.config['extensions'][module] = 'False'
          self.bot.config.save()
          await inter.send(
            self.bot.babel(inter, 'main', 'extension_disable_success', extension=module),
            ephemeral=True
          )
        elif action == Actions.load:
          self.bot.load_extension(ext)
          await inter.send(
            self.bot.babel(inter, 'main', 'extension_load_success', extension=module),
            ephemeral=True
          )
        elif action == Actions.unload:
          self.bot.unload_extension(ext)
          await inter.send(
            self.bot.babel(inter, 'main', 'extension_unload_success', extension=module),
            ephemeral=True
          )
        elif action == Actions.reload:
          self.bot.reload_extension(ext)
          await inter.send(
            self.bot.babel(inter, 'main', 'extension_reload_success', extension=module),
            ephemeral=True
          )
        else:
          raise commands.BadArgument
        if module.capitalize() in self.bot.cogs:
          for listener in self.bot.cogs[module.capitalize()].get_listeners():
            if listener[0] == 'on_ready':
              asyncio.ensure_future(listener[1]())
      else:
        await inter.send(self.bot.babel(inter, 'main', 'extension_file_missing'), ephemeral=True)
    else:
      await inter.send(self.bot.babel(inter, 'main', 'extension_not_found'), ephemeral=True)
  @module.autocomplete('module')
  async def module_ac(self, inter:disnake.ApplicationCommandInteraction, search:str):
    """ Suggests modules based on the list in config """
    extension_list = (f[11:-3].strip('_') for f in glob('extensions/*.py'))
    if 'action' in inter.filled_options:
      if inter.filled_options['action'] in [Actions.reload, Actions.unload]:
        extension_list = (
          e.replace('extensions.','').strip('_') for e in self.bot.extensions.keys()
        )
      elif inter.filled_options['action'] == Actions.list:
        return []
    return (
      [x for x in extension_list if search in x] +
      [e for e in ['config', 'babel'] if search in e]
    )

  @commands.slash_command()
  @commands.cooldown(1, 1)
  async def die(self, inter:disnake.ApplicationCommandInteraction, saveconfig:bool=False):
    """
    Log out and shut down

    Parameters
    ----------
    saveconfig: Write the last known state of the config file on shutdown
    """
    self.bot.cogs['Auth'].superusers(inter)
    await inter.send(self.bot.babel(inter, 'admin', 'die_success'))
    if saveconfig:
      self.bot.config.save()
    await self.bot.close()

def setup(bot):
  """ Bind this cog to the bot """
  bot.add_cog(System(bot))

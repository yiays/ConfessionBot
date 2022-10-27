"""
  Auth - One-liner authorization checks for commands
  Throws AuthError to quickly exit the command
  From there, Error can tell the users why the command failed
  Recommended cogs: Error
"""

from typing import Union
import disnake
from disnake.ext import commands

class Auth(commands.Cog):
  """custom auth rules for merely framework"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('auth'):
      bot.config.add_section('auth')
    if 'botadmin_guilds' not in bot.config['auth']:
      bot.config['auth']['botadmin_guilds'] = ''
    if 'superusers' not in bot.config['auth']:
      bot.config['auth']['superusers'] = ''
    if 'authusers' not in bot.config['auth']:
      bot.config['auth']['authusers'] = ''

  class AuthError(Exception):
    """Errors to be sent to a user that failed an auth test"""

  def owners(self, msg:Union[disnake.Message, disnake.GuildCommandInteraction]):
    """ Verify this user owns this guild """
    if msg.author == msg.guild.owner or\
        str(str(msg.author.id)) in self.bot.config['auth']['superusers']:
      return True
    raise self.AuthError(self.bot.babel(msg, 'auth', 'unauthorized'))

  def admins(self, msg:Union[disnake.Message, disnake.GuildCommandInteraction]):
    """ Verify this user is an admin """
    if msg.author == msg.guild.owner or\
        msg.channel.permissions_for(msg.author).administrator or\
        str(msg.author.id) in self.bot.config['auth']['superusers']:
      return True
    raise self.AuthError(self.bot.babel(msg, 'auth', 'not_admin'))

  def mods(self, msg:Union[disnake.Message, disnake.GuildCommandInteraction]):
    """ Verify this user is a moderator """
    if msg.author == msg.guild.owner or\
      msg.channel.permissions_for(msg.author).administrator or\
      msg.channel.permissions_for(msg.author).ban_members or\
      str(msg.author.id) in self.bot.config['auth']['superusers'] or\
      str(msg.author.id) in self.bot.config['auth']['authusers']:
      return True
    raise self.AuthError(self.bot.babel(msg, 'auth', 'not_mod'))

  def superusers(self, msg:Union[disnake.Message, disnake.ApplicationCommandInteraction]):
    """ Verify this user is a superuser """
    if str(msg.author.id) in self.bot.config['auth']['superusers']:
      return True
    raise self.AuthError(self.bot.babel(msg, 'auth', 'not_superuser'))

  def authusers(self, msg:Union[disnake.Message, disnake.ApplicationCommandInteraction]):
    """ Verify this user is an authuser """
    if str(msg.author.id) in self.bot.config['auth']['superusers'] or\
        str(msg.author.id) in self.bot.config['auth']['authusers']:
      return True
    raise self.AuthError(self.bot.babel(msg, 'auth', 'not_authuser'))

def setup(bot:commands.Bot):
  """ Bind this cog to the bot """
  bot.add_cog(Auth(bot))

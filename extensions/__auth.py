import nextcord
from nextcord.ext import commands

class Auth(commands.Cog):
  """custom auth rules for merely framework"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    # ensure config file has required data
    if not bot.config.has_section('auth'):
      bot.config.add_section('auth')
    if 'superusers' not in bot.config['auth']:
      bot.config['auth']['superusers'] = ''
    if 'authusers' not in bot.config['auth']:
      bot.config['auth']['authusers'] = ''
  
  #TODO: figure out why this isn't working
  @commands.Cog.listener("on_command_error")
  async def check_autherror(self, ctx:commands.Context, error):
    if isinstance(error, commands.errors.CommandInvokeError):
      if error.original is AuthError:
        await ctx.reply(str(error.original))

  def owners(self, ctx:commands.Context):
      if ctx.message.author == ctx.message.guild.owner or\
         str(str(ctx.message.author.id)) in self.bot.config['auth']['superusers']:
        return True
      else:
        raise AuthError(self.bot.babel(ctx, 'auth', 'unauthorized'))

  def admins(self, ctx:commands.Context):
      if ctx.message.author == ctx.message.guild.owner or\
         ctx.channel.permissions_for(ctx.message.author).administrator or\
         str(ctx.message.author.id) in self.bot.config['auth']['superusers']:
        return True
      else:
        raise AuthError(self.bot.babel(ctx, 'auth', 'not_admin'))

  def mods(self, ctx:commands.Context):
      if ctx.message.author == ctx.message.guild.owner or\
         ctx.channel.permissions_for(ctx.message.author).administrator or\
         ctx.channel.permissions_for(ctx.message.author).ban_members or\
         str(ctx.message.author.id) in self.bot.config['auth']['superusers'] or\
         str(ctx.message.author.id) in self.bot.config['auth']['authusers']:
        return True
      else:
        raise AuthError(self.bot.babel(ctx, 'auth', 'not_mod'))

  def superusers(self, ctx:commands.Context):
      if str(ctx.message.author.id) in self.bot.config['auth']['superusers']:
        return True
      else:
        raise AuthError(self.bot.babel(ctx, 'auth', 'not_superuser'))

  def authusers(self, ctx:commands.Context):
      if str(ctx.message.author.id) in self.bot.config['auth']['superusers'] or\
         str(ctx.message.author.id) in self.bot.config['auth']['authusers']:
        return True
      else:
        raise AuthError(self.bot.babel(ctx, 'auth', 'not_authuser'))

class AuthError(Exception):
  """Errors to be sent to a user that failed an auth test"""
  pass

def setup(bot):
  bot.add_cog(Auth(bot))
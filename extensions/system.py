import nextcord
from nextcord.ext import commands
from glob import glob
import asyncio

class System(commands.Cog):
  """commands involved in working with a discord bot"""
  def __init__(self, bot:commands.Bot):
    self.bot = bot
    if not bot.config.getboolean('extensions', 'auth', fallback=False):
      raise Exception("'auth' must be enabled to use 'admin'")

  @commands.command()
  async def module(self, ctx:commands.Context, module:str=None, action:str=None):
    if not self.bot.config.getboolean('extensions', 'allow_reloading'):
      return
    self.bot.cogs['Auth'].superusers(ctx)

    extensions = [e.replace('extensions.','').strip('_') for e in self.bot.extensions.keys()] + ['config', 'babel']
    if module is None:
      await ctx.reply(self.bot.babel(ctx, 'main', 'extensions_list', list='\n'.join(extensions)))
      return
    module = module.lower()

    ext = None
    if module in extensions or action=='load':
      if module=='config':
        self.bot.config.reload()
        await ctx.reply(self.bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
        return
      elif module=='babel':
        self.bot.babel.reload()
        await ctx.reply(self.bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
        return

      if action == 'load':
        for f in glob('extensions/*.py'):
          if f[11:-3].strip('_') == module: ext = f[:-3].replace('/','.')
      else:
        extcandidate = [ext for ext in self.bot.extensions.keys() if ext.replace('extensions.','').strip('_') == module]
        if extcandidate:
          ext = extcandidate[0]
    
      if ext:
        if action == 'enable':
          self.bot.config['extensions'][module] = 'True'
          self.bot.config.save()
          await ctx.reply(self.bot.babel(ctx, 'main', 'extension_enable_success', extension=module))
        elif action == 'disable':
          self.bot.config['extensions'][module] = 'False'
          self.bot.config.save()
          await ctx.reply(self.bot.babel(ctx, 'main', 'extension_disable_success', extension=module))
        elif action == 'load':
          self.bot.load_extension(ext)
          await ctx.reply(self.bot.babel(ctx, 'main', 'extension_load_success', extension=module))
        elif action == 'unload':
          self.bot.unload_extension(ext)
          await ctx.reply(self.bot.babel(ctx, 'main', 'extension_unload_success', extension=module))
        elif action == 'reload':
          self.bot.reload_extension(ext)
          await ctx.reply(self.bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
        else:
          raise commands.BadArgument
        if module.capitalize() in self.bot.cogs:
          for listener in self.bot.cogs[module.capitalize()].get_listeners():
            if listener[0] == 'on_ready':
              asyncio.ensure_future(listener[1]())
      else:
        await ctx.reply(self.bot.babel(ctx, 'main', 'extension_file_missing'))
    else:
      await ctx.reply(self.bot.babel(ctx, 'main', 'extension_not_found'))
        

  @commands.command()
  @commands.cooldown(1, 1)
  async def die(self, ctx:commands.Context, saveconfig=False):
    self.bot.cogs['Auth'].superusers(ctx)
    await ctx.reply(self.bot.babel(ctx, 'admin', 'die_success'))
    if saveconfig:
      self.bot.config.save()
    await self.bot.close()

def setup(bot):
  bot.add_cog(System(bot))
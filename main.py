import discord
from discord.ext import commands 
from config import Config
from babel import Babel
import sys, time, os
from itertools import groupby

class merelybot(commands.AutoShardedBot):
	"""this is the core of the merely framework."""
	config = Config()
	babel = Babel(config)
	verbose = False

	intents = discord.Intents.none()
	intents.guilds = config.getboolean('intents', 'guilds')
	intents.members = config.getboolean('intents', 'members')
	intents.bans = config.getboolean('intents', 'bans')
	intents.emojis = config.getboolean('intents', 'emojis')
	intents.integrations = config.getboolean('intents', 'integrations')
	intents.webhooks = config.getboolean('intents', 'webhooks')
	intents.invites = config.getboolean('intents', 'invites')
	intents.voice_states = config.getboolean('intents', 'voice_states')
	intents.presences = config.getboolean('intents', 'presences')
	intents.messages = config.getboolean('intents', 'messages')
	intents.guild_messages = config.getboolean('intents', 'guild_messages')
	intents.dm_messages = config.getboolean('intents', 'dm_messages')
	intents.reactions = config.getboolean('intents', 'reactions')
	intents.guild_reactions = config.getboolean('intents', 'guild_reactions')
	intents.dm_reactions = config.getboolean('intents', 'dm_reactions')
	intents.typing = config.getboolean('intents', 'typing')
	intents.guild_typing = config.getboolean('intents', 'guild_typing')
	intents.dm_typing = config.getboolean('intents', 'dm_typing')

	case_insensitive = True

	def __init__(self, **kwargs):
		print(f"""
		merely framework{' beta' if self.config.getboolean('main', 'beta') else ''} v{self.config['main']['ver']}
		currently named {self.config['main']['botname']} by config, uses {self.config['main']['prefix_short']}
		created by Yiays#5930. https://github.com/yiays/merelybot
		""")

		#stdout to file
		if not os.path.exists('logs'): os.makedirs('logs')

		sys.stdout = Logger()
		sys.stderr = Logger(err=True)

		if 'verbose' in kwargs:
			self.verbose = kwargs['verbose']

		prefixes = ()
		if self.config['main']['prefix_short']:
			prefixes += (self.config['main']['prefix_short']+' ', self.config['main']['prefix_short'])
		if self.config['main']['prefix_long']: prefixes += (self.config['main']['prefix_long']+' ',)

		super().__init__(command_prefix = commands.when_mentioned_or(*prefixes),
										 help_command = None,
										 intents = self.intents)

		self.autoload_extensions()

	def autoload_extensions(self):
		# a natural sort is used to make it possible to prioritize extensions by filename
		# add underscores to extension filenames to increase their priority
		for ext in sorted(os.listdir('extensions'), key=lambda s:[int(''.join(g)) if k else ''.join(g) for k, g in groupby('\0'+s, str.isdigit)]):
			if ext[-3:] == '.py':
				extfile = ext[:-3]
				extname = extfile.strip('_')
				if extname in self.config['extensions'].keys():
					if self.config.getboolean('extensions', extname):
						try:
							self.load_extension('extensions.'+extfile)
							print(f"{extname} loaded.")
						except Exception as e:
							print(f"Failed to load extension '{ext[:-3]}':\n{e}")
					else:
						if set(['-v','--verbose']) & set(sys.argv): print(f"{extname} is disabled, skipping.")
				else:
					self.config['extensions'][extname] = 'False'
					print(f"discovered {extname}, disabled by default, you can enable it in the config.")
		self.config.save()

class Logger(object):
	def __init__(self, err=False):
		self.terminal = sys.stderr if err else sys.stdout
		self.err = err
	def write(self, message):
		self.terminal.write(message.encode('utf-8').decode('ascii','ignore'))
		with open("logs/merely"+('-errors' if self.err else '')+"-"+time.strftime("%d-%m-%y")+".log", "a", encoding='utf-8') as log:
			log.write(message)
	def flush(self):
		return self

if __name__ == '__main__':
	if set(['-h','--help']) & set(sys.argv):
		print("""
		merelybot commands
		-h,--help		shows this help screen
		-v,--verbose		enables verbose logging
		""")
	else:
		bot = merelybot(verbose=bool(set(['-v','--verbose']) & set(sys.argv)))

		@bot.command()
		async def reload(ctx:commands.Context, module:str=None):
			if bot.config.getboolean('extensions', 'allow_reloading'):
				if 'Auth' in bot.cogs:
					bot.cogs['Auth'].superusers(ctx)
					extensions = [e.replace('extensions.','').strip('_') for e in bot.extensions.keys()] + ['config', 'babel']
					if module is None:
						await ctx.reply(bot.babel(ctx, 'main', 'extensions_list', list='\n'.join(extensions)))
						return
					module = module.lower()
					if module in extensions:
						extcandidate = [ext for ext in bot.extensions.keys() if ext.replace('extensions.','').strip('_') == module]
						if extcandidate:
							ext = extcandidate[0]
							bot.reload_extension(ext)
							if module.capitalize() in bot.cogs:
								for listener in bot.cogs[module.capitalize()].get_listeners():
									if listener[0] == 'on_ready':
										await listener[1]()
							await ctx.reply(bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
						elif module=='config':
							bot.config.reload()
							await ctx.reply(bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
						elif module=='babel':
							bot.babel.reload()
							await ctx.reply(bot.babel(ctx, 'main', 'extension_reload_success', extension=module))
						else:
							await ctx.reply(bot.babel(ctx, 'main', 'extension_file_missing'))
					else:
						await ctx.reply(bot.babel(ctx, 'main', 'extension_not_found'))
				else:
					raise Exception("'Auth' is a required extension in order to use reload.")

		token = bot.config.get('main', 'token', fallback=None)
		if token is not None:
			bot.run(token)
		else:
			raise Exception("failed to login! make sure you filled the token field in the config file.")
	
	print("exited.")
import disnake
from disnake.ext import commands 
from config import Config
from babel import Babel
import sys, time, os
from itertools import groupby

class merelybot(commands.AutoShardedBot):
	"""this is the core of the merely framework."""
	config = Config()
	babel = Babel(config)
	verbose = False

	intents = disnake.Intents.none()
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

		super().__init__(command_prefix = self.check_prefix,
										 help_command = None,
										 intents = self.intents,
										 case_insensitive = True)

		self.autoload_extensions()
	
	def check_prefix(self, bot, msg:disnake.Message):
		if bot.config['main']['prefix_short'] and msg.content.lower().startswith(bot.config['main']['prefix_short'].lower()):
			return [msg.content[0:len(bot.config['main']['prefix_short'])], msg.content[0 : len(bot.config['main']['prefix_short'])] + ' ']
		if bot.config['main']['prefix_long'] and msg.content.lower().startswith(bot.config['main']['prefix_long'].lower()):
			return msg.content[0:len(bot.config['main']['prefix_long'])] + ' '
		return commands.when_mentioned(bot, msg)

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
		if not os.path.exists("logs/"+time.strftime("%m-%y")):
			os.makedirs("logs/"+time.strftime("%m-%y"))
		self.terminal.write(message.encode('utf-8').decode('ascii','ignore'))
		with open("logs/"+time.strftime("%m-%y")+"/merelybot"+('-errors' if self.err else '')+"-"+time.strftime("%d-%m-%y")+".log", "a", encoding='utf-8') as log:
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

		token = bot.config.get('main', 'token', fallback=None)
		if token is not None:
			bot.run(token)
		else:
			raise Exception("failed to login! make sure you filled the token field in the config file.")

print("exited.")
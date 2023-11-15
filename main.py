"""
	MerelyBot Framework
	Adds modularity, translation support, and a config system to Python Discord bots
	Created by Yiays and contributors
"""

import sys, time, os
from itertools import groupby
import disnake
from disnake.ext import commands
from config import Config
from babel import Babel

class MerelyBot(commands.AutoShardedBot):
	"""this is the core of the merely framework."""
	config = Config()
	babel = Babel(config)
	verbose = False

	def __init__(self, **kwargs):
		print(f"""
		merely framework{' beta' if self.config.getboolean('main', 'beta') else ''} v{self.config['main']['ver']}
		currently named {self.config['main']['botname']} by config, uses {self.config['main']['prefix_short']}
		created by Yiays#5930. https://github.com/yiays/merelybot
		""")

		#stdout to file
		if not os.path.exists('logs'):
			os.makedirs('logs')
		sys.stdout = Logger()
		sys.stderr = Logger(err=True)

		if 'verbose' in kwargs:
			self.verbose = kwargs['verbose']

		# set intents
		intents = disnake.Intents.none()
		intents.guilds = self.config.getboolean('intents', 'guilds')
		intents.members = self.config.get('intents', 'members') != 'none'
		intents.moderation = self.config.getboolean('intents', 'moderation')
		intents.emojis = self.config.getboolean('intents', 'emojis')
		intents.integrations = self.config.getboolean('intents', 'integrations')
		intents.webhooks = self.config.getboolean('intents', 'webhooks')
		intents.invites = self.config.getboolean('intents', 'invites')
		intents.voice_states = self.config.getboolean('intents', 'voice_states')
		intents.presences = self.config.getboolean('intents', 'presences')
		intents.message_content = self.config.getboolean('intents', 'message_content')
		intents.guild_messages = 'guild' in self.config.get('intents', 'guild_messages')
		intents.dm_messages = 'dm' in self.config.get('intents', 'dm_messages')
		intents.messages = intents.guild_messages or intents.dm_messages
		intents.guild_reactions = 'guild' in self.config.get('intents', 'reactions')
		intents.dm_reactions = 'dm' in self.config.get('intents', 'reactions')
		intents.reactions = intents.guild_reactions or intents.dm_reactions
		intents.guild_typing = 'guild' in self.config.get('intents', 'typing')
		intents.dm_typing = 'dm' in self.config.get('intents', 'typing')
		intents.typing = intents.guild_typing or intents.dm_typing

		# set cache policy
		cachepolicy = disnake.MemberCacheFlags.all()
		if self.config.get('intents', 'members') in ('uncached', 'False'):
			cachepolicy = disnake.MemberCacheFlags.none()

		super().__init__(
			command_prefix = self.check_prefix,
			help_command = None,
			intents = intents,
			member_cache_flags = cachepolicy,
			case_insensitive = True
		)

		self.autoload_extensions()

	def check_prefix(self, _, msg:disnake.Message) -> list[str]:
		""" Check provided message should trigger the bot """
		if (
			self.config['main']['prefix_short'] and
			msg.content.lower().startswith(self.config['main']['prefix_short'].lower())
		):
			return (
				[msg.content[0:len(self.config['main']['prefix_short'])],
				msg.content[0 : len(self.config['main']['prefix_short'])] + ' ']
			)
		if (
			self.config['main']['prefix_long'] and
			msg.content.lower().startswith(self.config['main']['prefix_long'].lower())
		):
			return msg.content[0:len(self.config['main']['prefix_long'])] + ' '
		return commands.when_mentioned(self, msg)

	def autoload_extensions(self):
		""" Search the filesystem for extensions, list them in config, load them if enabled """
		# a natural sort is used to make it possible to prioritize extensions by filename
		# add underscores to extension filenames to increase their priority
		for ext in sorted(
			os.listdir('extensions'),
			key=lambda s:[int(''.join(g)) if k else ''.join(g) for k,
			g in groupby('\0'+s, str.isdigit)]
		):
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
						if self.verbose:
							print(f"{extname} is disabled, skipping.")
				else:
					self.config['extensions'][extname] = 'False'
					print(f"discovered {extname}, disabled by default, you can enable it in the config.")
		self.config.save()

class Logger(object):
	""" Records all stdout and stderr to log files, filename is based on date """
	def __init__(self, err=False):
		self.terminal = sys.stderr if err else sys.stdout
		self.err = err
	def write(self, message):
		""" Write output to log file """
		mfolder = os.path.join('logs', time.strftime("%m-%y"))
		if not os.path.exists(mfolder):
			os.makedirs(mfolder)
		self.terminal.write(message.encode('utf-8').decode('ascii','ignore'))
		fname = os.path.join(
			"logs",
			time.strftime("%m-%y"),
			"merelybot"+('-errors' if self.err else '')+"-"+time.strftime("%d-%m-%y")+".log"
		)
		with open(fname, "a", encoding='utf-8') as log:
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
		bot = MerelyBot(verbose=bool(set(['-v','--verbose']) & set(sys.argv)))

		token = bot.config.get('main', 'token', fallback=None)
		if token is not None:
			bot.run(token)
		else:
			raise Exception("failed to login! make sure you filled the token field in the config file.")

print("exited.")

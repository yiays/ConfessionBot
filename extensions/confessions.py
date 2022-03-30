"""
	Confessions - Anonymous messaging cog
	Features: botmod, bot banning, vetting, image support
	Dependencies: Auth, Help
	Notes: Contains generic command names like set, list, botmod, imagesupport, and ban
		As a result, this only really suits a singlular purpose bot
"""

from array import array
import asyncio, re, time
from enum import Enum
import base64
from typing import Optional, Union
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import disnake
from disnake.ext import commands


class ChannelType(int, Enum):
	""" Channel Types as they are stored """
	invalid = -2
	none = -1
	untraceable = 0
	traceable = 1
	vetting = 2
	feedback = 3

class Toggle(int, Enum):
	""" Enable and disable options for imagesupport """
	enable = 1
	disable = 0

class ConfessionData:
	""" Dataclass for Confessions """
	def __init__(
		self,
		bot:commands.Bot,
		rawdata:Optional[str]=None,
		*,
		author:Optional[disnake.User]=None,
		origin:Optional[Union[disnake.Message, disnake.Interaction]]=None,
		targetchannel:Optional[disnake.TextChannel]=None,
		embed:Optional[disnake.Embed]=None
	):
		# crypto config
		backend = default_backend()
		key = base64.decodebytes(bytes(bot.config['confessions']['secret'], encoding='ascii'))
		nonce = b'\xae[Et\xcd\n\x01\xf4\x95\x9c|No\x03\x81\x98'
		cipher = Cipher(algorithms.AES(key), modes.CTR(nonce), backend=backend)
		self.encryptor = cipher.encryptor()
		self.decryptor = cipher.decryptor()

		if rawdata:
			self.offline = True

			# print('==========')
			# print('rawdata', rawdata)
			encrypted = base64.b64decode(rawdata)
			# print('encrypted', encrypted)
			binary = self.decryptor.update(encrypted) + self.decryptor.finalize()
			# print('binary', binary)

			inputs = binary.split(b'_')
			self.author_id = int.from_bytes(inputs[0], 'big')
			self.origin_id = int.from_bytes(inputs[1], 'big')
			self.targetchannel_id = int.from_bytes(inputs[2], 'big')
		else:
			self.offline = False
			self.author = author
			self.origin = origin
			self.targetchannel = targetchannel

		if embed:
			self.content = \
				embed.description[20:] if embed.description.startswith('**[Anon-')\
				else embed.description
			self.image = embed.image.url if embed.image else None

	def store(self) -> str:
		""" Encrypt data for secure storage """

		if self.offline:
			bauthor = self.author_id.to_bytes(8, 'big')
			borigin = (self.origin_id if self.origin_id else 0).to_bytes(8, 'big')
			btarget = self.targetchannel_id.to_bytes(8, 'big')
		else:
			bauthor = self.author.id.to_bytes(8, 'big')
			borigin = (self.origin.id if self.origin else 0).to_bytes(8, 'big')
			btarget = self.targetchannel.id.to_bytes(8, 'big')

		binary = b'_'.join([bauthor, borigin, btarget])
		# print('binary', binary)
		encrypted = self.encryptor.update(binary) + self.encryptor.finalize()
		# print('encrypted', encrypted)
		rawdata = base64.b64encode(encrypted)
		# print('rawdata', rawdata)

		return rawdata.decode('ascii')

	async def fetch(self, bot:commands.Bot):
		""" Fetches referenced Discord elements for use """
		if self.offline:
			self.author = await bot.fetch_user(self.author_id)
			self.origin = None
			if self.origin_id > 0:
				try:
					self.origin = await self.author.fetch_message(self.origin_id)
				except (disnake.NotFound, disnake.Forbidden):
					pass
			self.targetchannel = await bot.fetch_channel(self.targetchannel_id)
			self.offline = False


class Confessions(commands.Cog):
	""" Enable anonymous messaging with moderation on your server """

	channel_icons = {
		ChannelType.untraceable: '🙈',
		ChannelType.traceable: '👁',
		ChannelType.feedback: '📢'
	}

	def __init__(self, bot:commands.Bot):
		self.bot = bot
		if not bot.config.getboolean('extensions', 'auth', fallback=False):
			raise Exception("'auth' must be enabled to use 'confessions'")
		# ensure config file has required data
		if not bot.config.has_section('confessions'):
			bot.config.add_section('confessions')
		if 'confession_cooldown' not in bot.config['confessions']:
			bot.config['confessions']['confession_cooldown'] = 1
		if 'anonid_generator' not in bot.config['confessions']:
			bot.config['confessions']['anonid_generator'] = '#import\nanonid = hex(uuid)[-6:]'
			print("""
				WARNING: you should define a more advanced algorithm for hiding user ids.
				(config[confessions][anonid_generator])
			""")
		self.initiated = set()
		self.ignore = set()
		self.confession_cooldown = dict()

	#	Utility functions

	def get_anonid(self, guildid:int, userid:int) -> str:
		""" Calculates the current anon-id for a user """

		offset = self.bot.config.getint('confessions', f"{guildid}_shuffle", fallback=0)
		loc = {'uuid' : guildid+userid+offset, 'anonid' : None}
		exec(self.bot.config['confessions']['anonid_generator'], None, loc)
		return loc['anonid']

	def generate_list(self, user:disnake.User, matches:array, vetting:bool, enum:bool=False) -> str:
		""" Returns a formatted list of available confession targets """

		targets = []
		for i, match in enumerate(matches):
			targets.append(
				(str(i+1)+':' if enum else '') +\
				f'{self.channel_icons[match[1]]}<#{match[0].id}>' +\
				(' ('+match[0].guild.name+')' if not isinstance(user, disnake.Member) else '')
			)
		vettingwarning = ('\n'+self.bot.babel(user, 'confessions', 'vetting') if vetting else '')

		return '\n'.join(targets) + vettingwarning

	def scanguild(self, member:disnake.Member) -> tuple:
		""" Scans a guild for any targets that a member can use for confessions """

		matches = []
		vetting = False
		for channel in member.guild.channels:
			if f"{member.guild.id}_{channel.id}" in self.bot.config['confessions']:
				chtype = self.bot.config.getint('confessions', f"{member.guild.id}_{channel.id}")
				if chtype == ChannelType.vetting:
					vetting = True
					continue
				if chtype == ChannelType.feedback:
					matches.append((channel, chtype))
					continue
				if channel.permissions_for(member).read_messages:
					matches.append((channel, chtype))
					continue

		return matches, vetting

	def listavailablechannels(self, user:Union[disnake.User, disnake.Member]) -> tuple:
		"""
			List all available targets on a server for a member
			List all available targets on all mutual servers for a user
		"""

		if isinstance(user, disnake.Member):
			matches,vetting = self.scanguild(user)
		else:
			matches = []
			vetting = False
			for guild in self.bot.guilds:
				if member := guild.get_member(user.id):
					newmatches, newvetting = self.scanguild(member)
					matches += newmatches
					vetting = vetting or newvetting

		return matches, vetting

	def generate_confession(
		self,
		anonid:str,
		lead:str,
		content:str,
		image:Optional[str]
	) -> disnake.Embed:
		""" Generate the confession embed """
		if lead:
			embed = disnake.Embed(colour=disnake.Colour(int(anonid,16)),description=lead+' '+content)
		else:
			embed = disnake.Embed(description=content)
		if image:
			embed.set_image(url=image)
		return embed

	async def send_confession(
		self,
		ctx:Union[disnake.DMChannel, disnake.Interaction],
		targetchannel:disnake.TextChannel,
		embed:disnake.Embed
	) -> None:
		""" Sends confessions through, plus the copious amounts of error handling """
		try:
			await targetchannel.send(embed=embed)
		except disnake.Forbidden:
			try:
				await targetchannel.send(
					self.bot.babel(
						targetchannel.guild,
						'confessions',
						'missingperms',
						perm='Embed Links'
					)
				)
				if isinstance(ctx, disnake.DMChannel):
					await ctx.send(self.bot.babel(ctx, 'confessions', 'embederr'))
				else:
					await ctx.send(self.bot.babel(ctx, 'confessions', 'embederr'), ephemeral=True)
			except disnake.Forbidden:
				if isinstance(ctx, disnake.DMChannel):
					await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'))
				else:
					await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'), ephemeral=True)
		except disnake.NotFound:
			if isinstance(ctx, disnake.DMChannel):
				await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'))
			else:
				await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'), ephemeral=True)

	def findvettingchannel(self, guild) -> Optional[disnake.TextChannel]:
		""" Check if guild has a vetting channel and return it """

		for channel in guild.channels:
			if self.bot.config.getint(
				'confessions',
				str(guild.id)+'_'+str(channel.id),
				fallback=ChannelType.none
			) == ChannelType.vetting:
				return channel
		return None


	#	Checks

	def check_channel(self, guild_id:int, channel_id:int) -> bool:
		""" Verifies channel is currently in the config """

		channeltype = self.bot.config.getint(
			'confessions', f"{guild_id}_{channel_id}",
			fallback=ChannelType.none
		)
		if channeltype in [ChannelType.traceable, ChannelType.untraceable, ChannelType.feedback]:
			return True
		return False

	def check_banned(self, guild_id:int, anonid:str) -> bool:
		""" Verify the user hasn't been banned """

		if anonid in self.bot.config.get('confessions', f"{guild_id}_banned", fallback='').split(','):
			return False
		return True

	def check_imagesupport(self, guild_id:int, image:disnake.Attachment) -> bool:
		""" Verify imagesupport is enabled, if required """

		if image and image.content_type.startswith('image'):
			if self.bot.config.getboolean('confessions', f"{guild_id}_imagesupport", fallback=True):
				return True
			return False

	def check_spam(self, content:str):
		""" Verify message doesn't contain spam as defined in [confessions] spam_flags """

		for spamflag in self.bot.config.get('confessions', 'spam_flags', fallback=None).splitlines():
			if re.match(spamflag, content):
				return False
		return True

	def check_promoted(self, member:disnake.Member):
		""" Verify provided member has been promoted """

		promoted = self.bot.config.get('confessions', str(member.guild.id)+'_promoted', fallback='')
		promoted = promoted.split(',')
		return str(member.id) in promoted

	#	Views

	class ChannelView(disnake.ui.View):
		""" View for selecting a target interactively """
		def __init__(self, origin:disnake.Message, confessions, matches):
			super().__init__(timeout=30)
			self.origin = origin
			self.confessions = confessions
			self.done = False
			for channel,channeltype in matches:
				self.channel_selector.append_option(
					disnake.SelectOption(
						label=f'{channel.name} (from {channel.guild.name})',
						value=str(channel.id),
						emoji=Confessions.channel_icons[channeltype]
					)
				)
			self.channel_selector.placeholder = self.confessions.bot.babel(
				origin,
				'confessions',
				'channelprompt_placeholder'
			)
			self.send_button.label = self.confessions.bot.babel(
				origin,
				'confessions',
				'channelprompt_button_send'
			)

		@disnake.ui.select(min_values=1, max_values=1)
		async def channel_selector(self, select:disnake.ui.Select, inter:disnake.MessageInteraction):
			""" Update the message to preview the selected target """

			self.send_button.disabled = False
			channel = await self.confessions.bot.fetch_channel(int(select._selected_values[0]))
			vetting = self.confessions.findvettingchannel(channel.guild)
			channeltype = self.confessions.bot.config.getint(
				'confessions',
				f"{channel.guild.id}_{channel.id}"
			)
			await inter.response.edit_message(
				content=self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompted',
					channel=channel.mention,
					vetting=vetting and channeltype != ChannelType.feedback),
				view=self)

		@disnake.ui.button(disabled=True, style=disnake.ButtonStyle.primary)
		async def send_button(self, _:disnake.Button, inter:disnake.MessageInteraction):
			""" Send the confession """

			channel = await self.confessions.bot.fetch_channel(int(self.channel_selector.values[0]))

			anonid = self.confessions.get_anonid(channel.guild.id, inter.author.id)
			lead = f"**[Anon-*{anonid}*]**"
			channeltype = self.confessions.bot.config.getint(
				'confessions',
				f"{channel.guild.id}_{channel.id}"
			)

			if not self.confessions.check_banned(channel.guild.id, anonid):
				await inter.send(self.confessions.bot.babel(inter, 'confessions', 'nosendbanned'))
				await self.disable(inter)
				return

			content = self.origin.content
			image = self.origin.attachments[0] if self.origin.attachments else None
			if image:
				if not self.confessions.check_imagesupport(channel.guild.id, image):
					await inter.send(self.confessions.bot.babel(inter, 'confessions', 'nosendimages'))
					await self.disable(inter)
					return

			vetting = self.confessions.findvettingchannel(channel.guild)
			embed = self.confessions.generate_confession(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				content,
				image.url if image else None
			)

			if vetting and channeltype != ChannelType.feedback:
				pendingconfession = ConfessionData(
					self.confessions.bot,
					author=inter.author,
					origin=self.origin,
					targetchannel=channel
				)

				view = self.confessions.PendingConfessionView(self.confessions, pendingconfession)

				await vetting.send(
					self.confessions.bot.babel(
						channel.guild,
						'confessions',
					  'vetmessagecta',
						channel=channel.mention
					),
					embed=embed,
					view=view
				)
				await inter.send(
					self.confessions.bot.babel(
						inter,
						'confessions',
						'confession_vetting',
						channel=channel.mention
					),
					ephemeral=True
				)
				await self.disable(inter)
				return

			await self.confessions.send_confession(inter, channel, embed)

			self.send_button.label = self.confessions.bot.babel(
				inter,
				'confessions',
				'channelprompt_button_sent'
			)
			self.channel_selector.disabled = True
			self.send_button.disabled = True
			self.done = True
			await inter.response.edit_message(
				content=self.confessions.bot.babel(
					inter,
					'confessions',
					'confession_sent_channel',
					channel=channel.mention
				),
				view=self
			)

		async def disable(self, inter:disnake.MessageInteraction):
			""" Prevent further input """

			self.channel_selector.disabled = True
			self.send_button.disabled = True
			self.done = True
			await inter.message.edit(view=self)

		async def on_timeout(self):
			if not self.done:
				await self.origin.reply(
					self.confessions.bot.babel(self.origin.author, 'confessions', 'timeouterror')
				)
			async for msg in self.origin.channel.history(after=self.origin):
				if msg.reference.message_id == self.origin.id:
					await msg.delete()
					return

	class PendingConfessionView(disnake.ui.View):
		""" Asks moderators to approve or deny a confession as a part of vetting """
		def __init__(self, confessions, pendingconfession:ConfessionData):
			self.confessions = confessions
			self.pendingconfession = pendingconfession
			super().__init__(timeout=None)

			data = pendingconfession.store()
			self.add_item(disnake.ui.Button(
				label = confessions.bot.babel(
					pendingconfession.targetchannel.guild,
					'confessions',
					'vetting_approve_button'
				),
				emoji = '✅',
				style = disnake.ButtonStyle.blurple,
				custom_id = f"pendingconfession_approve_{data}"
			))

			self.add_item(disnake.ui.Button(
				label = confessions.bot.babel(
					pendingconfession.targetchannel.guild,
					'confessions',
					'vetting_deny_button'
				),
				emoji = '❎',
				style = disnake.ButtonStyle.danger,
				custom_id = f"pendingconfession_deny_{data}"
			))

	class ConfessionModal(disnake.ui.Modal):
		""" Modal for completing an incomplete confession """
		def __init__(self, confessions, origin:disnake.ModalInteraction, image:disnake.Attachment):
			super().__init__(
				title = confessions.bot.babel(origin, 'confessions', 'editor_title'),
				custom_id = "confession_modal",
				components = [
					disnake.ui.TextInput(
						label = confessions.bot.babel(origin, 'confessions', 'editor_message_label'),
						placeholder = confessions.bot.babel(
							origin,
							'confessions',
							'editor_message_placeholder'
						),
						custom_id = "content",
						style = disnake.enums.TextInputStyle.paragraph,
						min_length = 1
					)
				]
			)

			self.confessions = confessions
			self.origin = origin
			self.image = image

		async def callback(self, inter:disnake.ModalInteraction):
			""" Send the completed confession """

			if 'Log' in self.confessions.bot.cogs:
				await self.confessions.bot.cogs['Log'].log_misc_str(inter, inter.text_values['content'])

			if not self.confessions.check_spam(inter.text_values['content']):
				await inter.send(
					self.confessions.bot.babel(inter, 'confessions', 'nospam'),
					ephemeral=True
				)
				return

			anonid = self.confessions.get_anonid(inter.guild.id, inter.author.id)
			channeltype = self.confessions.bot.config.getint(
				'confessions',
				f"{inter.guild_id}_{inter.channel_id}"
			)
			lead = f"**[Anon-*{anonid}*]**"

			vetting = self.confessions.findvettingchannel(inter.guild)
			embed = self.confessions.generate_confession(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				inter.text_values['content'],
				self.image.url if self.image else None
			)

			if vetting and channeltype != ChannelType.vetting:
				pendingconfession = ConfessionData(
					self.confessions.bot,
					author=inter.author,
					targetchannel=inter.channel
				)

				view = self.confessions.PendingConfessionView(self.confessions, pendingconfession)

				await vetting.send(
					self.confessions.bot.babel(
						inter.guild,
						'confessions',
						'vetmessagecta',
						channel=inter.channel.mention
					),
					embed=embed,
					view=view)
				await inter.send(
					self.confessions.bot.babel(
						inter,
						'confessions',
						'confession_vetting',
						channel=inter.channel.mention
					),
					ephemeral=True)

				return

			await inter.send(
				self.confessions.bot.babel(inter, 'confessions', 'confession_sent_below'),
				ephemeral=True
			)
			await self.confessions.send_confession(inter, inter.channel, embed)

	#	Events

	@commands.Cog.listener('on_button_click')
	async def on_confession_review(self, inter:disnake.MessageInteraction):
		""" Handle approving and denying confessions """
		if inter.data.custom_id.startswith('pendingconfession_'):
			vetmessage = inter.message

			if inter.data.custom_id.startswith('pendingconfession_approve_'):
				pendingconfession = ConfessionData(
					self.bot,
					inter.data.custom_id[26:],
					embed=vetmessage.embeds[0]
				)
				accepted = True

			elif inter.data.custom_id.startswith('pendingconfession_deny_'):
				pendingconfession = ConfessionData(self.bot, inter.data.custom_id[23:])
				accepted = False
			else:
				print(f"WARN: Unknown button action '{inter.data.custom_id}'!")
				return

			try:
				await pendingconfession.fetch(self.bot)
			except (disnake.NotFound, disnake.Forbidden):
				if accepted:
					await inter.send(self.bot.babel(
						inter,
						'confessions',
						'vettingrequiredmissing',
						channel=f"<#{pendingconfession.targetchannel_id}>"
					))
					return

			if accepted:
				anonid = self.get_anonid(inter.guild.id, pendingconfession.author.id)
				lead = f"**[Anon-*{anonid}*]**"
				channeltype = self.bot.config.getint(
					'confessions',
					f"{inter.guild.id}_{pendingconfession.targetchannel_id}"
				)

				embed = self.generate_confession(
					anonid,
					lead if channeltype != ChannelType.untraceable else '',
					pendingconfession.content,
					pendingconfession.image
				)

				if not pendingconfession.author.dm_channel:
					await pendingconfession.author.create_dm()
				await self.send_confession(
					pendingconfession.author.dm_channel,
					pendingconfession.targetchannel,
					embed
				)

			await vetmessage.edit(view=None)
			await inter.send(self.bot.babel(
				inter.guild,
				'confessions',
				'vetaccepted' if accepted else 'vetdenied',
				user=inter.author.mention,
				channel=pendingconfession.targetchannel.mention)
			)

			content = self.bot.babel(
				pendingconfession.author,
				'confessions',
				'confession_vetting_accepted' if accepted else 'confession_vetting_denied',
				channel=pendingconfession.targetchannel.mention
			)
			if isinstance(pendingconfession.origin, disnake.Message):
				await pendingconfession.origin.reply(content)
			elif isinstance(pendingconfession.origin, disnake.Interaction):
				await pendingconfession.origin.send(content, ephemeral=True)
			else:
				await pendingconfession.author.send(content)

	@commands.Cog.listener('on_message')
	async def confession_request(self, msg:disnake.Message):
		""" Handle plain DM messages as confessions """
		ctx = await self.bot.get_context(msg)
		if ctx.prefix is not None:
			return
		if isinstance(msg.channel, disnake.DMChannel) and\
				msg.author != self.bot.user:
			if msg.channel in self.ignore:
				self.ignore.remove(msg.channel)
				return
			if msg.author in self.confession_cooldown and self.confession_cooldown[msg.author] > time.time():
				return
			else:
				self.confession_cooldown[msg.author] = time.time() +\
					self.bot.config.getint('confessions', 'confession_cooldown', fallback=1)

			if 'Log' in self.bot.cogs:
				await self.bot.cogs['Log'].log_misc_message(msg)

			matches,_ = self.listavailablechannels(msg.author)

			if not self.bot.is_ready():
				await msg.channel.send(self.bot.babel(msg, 'confessions', 'cachebuilding'))
				if not matches:
					return

			if not matches:
				await msg.channel.send(self.bot.babel(msg, 'confessions', 'inaccessible'))
				return

			if not self.check_spam(msg.content):
				await msg.reply(self.bot.babel(msg, 'confessions', 'nospam'))
				return

			await msg.reply(
				self.bot.babel(msg, 'confessions', 'channelprompt'),
				view=self.ChannelView(msg, self, matches))


	#	Slash commands

	@commands.cooldown(1, 1)
	@commands.slash_command(description="Send an anonymous message")
	async def confess(
		self,
		inter: disnake.GuildCommandInteraction,
		content:Optional[str] = None,
		image:Optional[disnake.Attachment] = None
	):
		"""
		Send an anonymous message to this channel

		Parameters
		----------
		content: The text of your anonymous message, leave blank for a paragraph editor
		image: An optional image that appears below the text
		"""

		if content and 'Log' in self.bot.cogs:
			await self.bot.cogs['Log'].log_misc_str(inter, content + ('*' if image else ''))

		if not self.check_channel(inter.guild_id, inter.channel_id):
			await inter.send(self.bot.babel(inter, 'confessions', 'nosendchannel'), ephemeral=True)
			return

		anonid = self.get_anonid(inter.guild_id, inter.author.id)
		lead = f"**[Anon-*{anonid}*]**"
		channeltype = self.bot.config.getint('confessions', f"{inter.guild_id}_{inter.channel_id}")

		if not self.check_banned(inter.guild_id, anonid):
			await inter.send(self.bot.babel(inter, 'confessions', 'nosendbanned'), ephemeral=True)
			return

		if image:
			if not self.check_imagesupport(inter.channel_id, image):
				await inter.send(self.bot.babel(inter, 'confessions', 'nosendimages'), ephemeral=True)
				return

		if content or image:
			if content is None:
				content=''

			if not self.check_spam(content):
				await inter.send(self.bot.babel(inter, 'confessions', 'nospam'), ephemeral=True)
				return

			vetting = self.findvettingchannel(inter.guild)
			embed = self.generate_confession(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				content,
				image.url if image else None
			)

			if (
				(vetting := self.findvettingchannel(inter.guild)) and
				channeltype != ChannelType.feedback
				):
				pendingconfession = ConfessionData(
					self.bot,
					author=inter.author,
					targetchannel=inter.channel
				)

				view = self.PendingConfessionView(self, pendingconfession)

				await vetting.send(
					self.bot.babel(inter.guild, 'confessions', 'vetmessagecta', channel=inter.channel.mention),
					embed=embed,
					view=view
				)
				await inter.send(
					self.bot.babel(inter, 'confessions', 'confession_vetting', channel=inter.channel.mention),
					ephemeral=True
				)

				return

			await inter.send(
				self.bot.babel(inter, 'confessions', 'confession_sent_below'),
				ephemeral=True
			)
			await self.send_confession(inter, inter.channel, embed)

		else:
			await inter.response.send_modal(
				modal=self.ConfessionModal(confessions=self, origin=inter, image=image)
			)

	#	Commands

	@commands.guild_only()
	@commands.slash_command()
	async def set(
		self,
		inter:disnake.GuildCommandInteraction,
		mode:ChannelType = commands.Param(ChannelType.invalid, ge=ChannelType.none)
	):
		"""
		Set a channel for use with ConfessionBot

		Parameters
		----------
		mode: The channel type, use `/help set` for an explaination of types
		"""
		self.bot.cogs['Auth'].admins(inter)
		if mode==ChannelType.invalid:
			raise commands.BadArgument()
		elif mode==ChannelType.none:
			wastype = self.bot.config.getint(
				'confessions',
				str(inter.guild.id)+'_'+str(inter.channel.id), fallback=ChannelType.none
			)
			if wastype == ChannelType.none:
				await inter.send(self.bot.babel(inter, 'confessions', 'unsetfailure'))
				return
			self.bot.config.remove_option('confessions', str(inter.guild.id)+'_'+str(inter.channel.id))
		else:
			self.bot.config['confessions'][str(inter.guild.id)+'_'+str(inter.channel.id)] = str(mode)
		self.bot.config.save()

		modestring = (
			'setsuccess'+str(mode) if mode>ChannelType.none else 'unsetsuccess'+str(wastype)
		)
		await inter.send(
			self.bot.babel(inter, 'confessions', modestring) +' '+ \
			self.bot.babel(inter, 'confessions', 'setundo' if mode>ChannelType.none else 'unsetundo')
		)

	@commands.slash_command()
	async def list(self, inter:disnake.ApplicationCommandInteraction):
		"""
		List all anonymous channels available here
		"""
		matches,vetting = self.listavailablechannels(inter.author)
		local = ('local' if isinstance(inter.author, disnake.Member) else '')
		# warn users when the channel list isn't complete
		if not self.bot.is_ready():
			await inter.send(self.bot.babel(inter,'confessions','cachebuilding'))
		elif len(matches) == 0:
			await inter.send(self.bot.babel(inter,'confessions','inaccessible' + local))
		else:
			await inter.send(
				self.bot.babel(inter,'confessions','listtitle' + local) + \
				'\n'+self.generate_list(inter.author, matches, vetting)
			)

	@commands.guild_only()
	@commands.slash_command()
	async def shuffle(
		self,
		inter:disnake.GuildCommandInteraction
	):
		"""
		Change all anon-ids on a server
		"""
		if not self.check_promoted(inter.author):
			self.bot.cogs['Auth'].mods(inter)
		if str(inter.guild.id)+'_banned' in self.bot.config['confessions']:
			await inter.send(
				self.bot.babel(inter, 'confessions', 'shufflebanresetwarning')
			)
			def check(m):
				return m.channel == inter.channel and m.author == inter.author and m.content.lower() == 'yes'
			try:
				await self.bot.wait_for('message', check=check, timeout=30)
			except asyncio.TimeoutError:
				await inter.send(self.bot.babel(inter, 'confessions', 'timeouterror'))
			else:
				self.bot.config.remove_option('confessions', str(inter.guild.id)+'_banned')

		shuffle = self.bot.config.getint('confessions', str(inter.guild.id)+'_shuffle', fallback=0)
		self.bot.config.set('confessions', str(inter.guild.id)+'_shuffle', str(shuffle + 1))
		self.bot.config.save()

		await inter.send(self.bot.babel(inter, 'confessions', 'shufflesuccess'))

	@commands.guild_only()
	@commands.slash_command()
	async def imagesupport(self, inter:disnake.GuildCommandInteraction, toggle:Toggle):
		"""
		Enable or disable images in confessions
		"""
		self.bot.cogs['Auth'].admins(inter)
		val = self.bot.config.getboolean('confessions', f"{inter.guild.id}_imagesupport", fallback=True)
		if toggle == Toggle.enable:
			if val:
				await inter.send(self.bot.babel(inter, 'confessions', 'imagesupportalreadyenabled'))
			else:
				self.bot.config['confessions'][str(inter.guild.id)+'_imagesupport'] = 'True'
				self.bot.config.save()
				await inter.send(self.bot.babel(inter, 'confessions', 'imagesupportenabled'))
		elif toggle == Toggle.disable:
			if not val:
				await inter.send(self.bot.babel(inter, 'confessions', 'imagesupportalreadydisabled'))
			else:
				self.bot.config['confessions'][str(inter.guild.id)+'_imagesupport'] = 'False'
				self.bot.config.save()
				await inter.send(self.bot.babel(inter, 'confessions', 'imagesupportdisabled'))

	@commands.guild_only()
	@commands.slash_command(aliases=['ban'])
	async def block(
		self,
		inter:disnake.GuildCommandInteraction,
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
		if not self.check_promoted(inter.author):
			self.bot.cogs['Auth'].mods(inter)

		banlist = self.bot.config.get('confessions', str(inter.guild.id)+'_banned', fallback='')
		banlist = banlist.split(',')
		if anonid is None:
			if banlist:
				printedlist = '\n```'+'\n'.join(banlist)+'```'
				await inter.send(self.bot.babel(inter, 'confessions', 'banlist') + printedlist)
			else:
				await inter.send(self.bot.babel(inter, 'confessions', 'emptybanlist'))
			return

		anonid = anonid.lower()
		if len(anonid)>6:
			anonid = anonid[-6:]
		try:
			int(anonid, 16)
		except ValueError:
			await inter.send(self.bot.babel(inter, 'confessions', 'invalidanonid'))
			return
		if anonid in banlist and not unblock:
			await inter.send(self.bot.babel(inter, 'confessions', 'doublebananonid'))
			return

		if unblock:
			fullid = [i for i in banlist.split(',') if anonid in i][0]
			self.bot.config['confessions'][str(inter.guild.id)+'_banned'] = banlist.replace(fullid+',','')
		else:
			self.bot.config['confessions'][str(inter.guild.id)+'_banned'] = banlist + anonid + ','
		self.bot.config.save()

		await inter.send(
			self.bot.babel(inter, 'confessions', ('un' if unblock else '')+'bansuccess', user=anonid)
		)

	@commands.guild_only()
	@commands.slash_command()
	async def botmod(
		self,
		inter:disnake.GuildCommandInteraction,
		target:Optional[disnake.Member] = None,
		revoke:Optional[bool] = False
	):
		"""
		Grant or take away botmod powers from a user

		Parameters
		----------
		target: The user who will be affected by this command
		revoke: Set to true if you want to revoke botmod powers
		"""
		self.bot.cogs['Auth'].admins(inter)

		modlist = self.bot.config.get('confessions', str(inter.guild.id)+'_promoted', fallback='')
		if target is None:
			if modlist:
				printedlist = '\n```\n' + '\n'.join(modlist.split(',')) + '```'
				await inter.send(self.bot.babel(inter, 'confessions', 'botmodlist') + printedlist)
			else:
				await inter.send(self.bot.babel(inter, 'confessions', 'botmodemptylist'))
		elif target:
			if target.bot:
				await inter.send(self.bot.babel(inter, 'confessions', 'botmodboterr'))
				return
			if target.guild_permissions.ban_members:
				await inter.send(self.bot.babel(inter, 'confessions', 'botmodmoderr'))
				return

			if revoke:
				if str(target.id) in modlist.split(','):
					modlist = modlist.replace(str(target.id)+',','')
					self.bot.config['confessions'][str(inter.guild.id)+'_promoted'] = modlist
					self.bot.config.save()
					await inter.send(
						self.bot.babel(inter, 'confessions', 'botmoddemotesuccess', user=target.name)
					)
				else:
					await inter.send(self.bot.babel(inter, 'confessions', 'botmoddemoteerr'))
			else:
				if str(target.id) not in modlist.split(','):
					modlist += str(target.id)+','
					self.bot.config['confessions'][str(inter.guild.id)+'_promoted'] = modlist
					self.bot.config.save()
					await inter.send(self.bot.babel(inter, 'confessions', 'botmodsuccess', user=target.name))
				else:
					await inter.send(self.bot.babel(inter, 'confessions', 'rebotmoderr'))
		else:
			raise commands.BadArgument()

	#	Cleanup

	@commands.Cog.listener('on_guild_leave')
	async def guild_cleanup(self, guild:disnake.Guild):
		""" Automatically remove data related to a guild on removal """
		for option in self.bot.config['confessions']:
			if option.startswith(str(guild.id)+'_'):
				self.bot.config.remove_option('confessions', option)
		self.bot.config.save()

	@commands.Cog.listener('on_guild_channel_delete')
	async def channel_cleanup(self, channel:disnake.TextChannel):
		""" Automatically remove data related to a channel on delete """
		for option in self.bot.config['confessions']:
			if option == str(channel.guild.id)+'_'+str(channel.id):
				self.bot.config.remove_option('confessions', option)
				break
		self.bot.config.save()

def setup(bot) -> None:
	""" Bind this cog to the bot """
	bot.add_cog(Confessions(bot))

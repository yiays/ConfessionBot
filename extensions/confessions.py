"""
	Confessions - Anonymous messaging cog
	Features: botmod, bot banning, vetting, image support
	Dependencies: Auth, Help
	Notes: Contains generic command names like set, list, botmod, imagesupport, and ban
		As a result, only really suits a singlular purpose bot
"""

from array import array
import asyncio, re, time, os
import base64
from typing import Optional, Union
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import disnake
from disnake.ext import commands


class ChannelType:
	""" Channel Types as they are stored """
	INVALID = -2
	NONE = -1
	UNTRACEABLE = 0
	TRACEABLE = 1
	VETTING = 2
	FEEDBACK = 3


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
			data = binary.decode('utf-8')

			inputs = data.split('_')
			self.author_id = int(inputs[0])
			self.origin_id = int(inputs[1])
			self.targetchannel_id = int(inputs[2])
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
			data = f"{self.author_id}_{self.origin_id if self.origin_id else 0}_{self.targetchannel_id}"
		else:
			data = f"{self.author.id}_{self.origin.id if self.origin else 0}_{self.targetchannel.id}"

		binary = bytes(data, encoding='utf-8')
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
		ChannelType.UNTRACEABLE: '🙈',
		ChannelType.TRACEABLE: '👁',
		ChannelType.FEEDBACK: '📢'
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
				if chtype == ChannelType.VETTING:
					vetting = True
					continue
				if chtype == ChannelType.FEEDBACK:
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
					await ctx.response.send_message(
						self.bot.babel(ctx, 'confessions', 'embederr'),
						ephemeral=True
					)
			except disnake.Forbidden:
				if isinstance(ctx, disnake.DMChannel):
					await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'))
				else:
					await ctx.response.send_message(
						self.bot.babel(ctx, 'confessions', 'missingchannelerr'),
						ephemeral=True
					)
		except Exception as e:
			if isinstance(ctx, disnake.DMChannel):
				await ctx.send(self.bot.babel(ctx, 'confessions', 'missingchannelerr'))
			else:
				await ctx.response.send_message(
					self.bot.babel(ctx, 'confessions', 'missingchannelerr'),
					ephemeral=True
				)
			raise e

	def findvettingchannel(self, guild) -> Optional[disnake.TextChannel]:
		""" Check if guild has a vetting channel and return it """

		for channel in guild.channels:
			if self.bot.config.getint(
				'confessions',
				str(guild.id)+'_'+str(channel.id),
				fallback=ChannelType.NONE
			) == ChannelType.VETTING:
				return channel
		return None


	#	Checks

	def check_channel(self, guild_id:int, channel_id:int) -> bool:
		""" Verifies channel is currently in the config """

		channeltype = self.bot.config.getint(
			'confessions', f"{guild_id}_{channel_id}",
			fallback=ChannelType.NONE
		)
		if channeltype in [ChannelType.TRACEABLE, ChannelType.UNTRACEABLE, ChannelType.FEEDBACK]:
			return True
		return False

	def check_banned(self, guild_id:int, anonid:str) -> bool:
		""" Verify the user hasn't been banned """

		for i in self.bot.config.get('confessions', str(guild_id)+'_banned', fallback='').split(','):
			if anonid == i:
				return False
		return True

	def check_imagesupport(self, guild_id:int, image:disnake.Attachment) -> bool:
		""" Verify imagesupport is enabled, if required """

		if image and image.content_type.startswith('image'):
			if self.bot.config.getboolean('confessions', str(guild_id)+'_imagesupport', fallback=True):
				return True
			return False

	def check_spam(self, content:str):
		""" Verify message doesn't contain spam as defined in [confessions] spam_flags """

		for spamflag in self.bot.config.get('confessions', 'spam_flags', fallback=None).splitlines():
			if re.match(spamflag, content):
				return False
		return True

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
			channeltype = self.confessions.bot.config.getint('confessions', f"{channel.guild.id}_{channel.id}")
			await inter.response.edit_message(
				content=self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompted',
					channel=channel.mention,
					vetting=vetting and channeltype != ChannelType.FEEDBACK),
				view=self)

		@disnake.ui.button(disabled=True, style=disnake.ButtonStyle.primary)
		async def send_button(self, button:disnake.Button, inter:disnake.MessageInteraction):
			""" Send the confession """

			channel = await self.confessions.bot.fetch_channel(int(self.channel_selector.values[0]))

			anonid = self.confessions.get_anonid(channel.guild.id, inter.author.id)
			lead = f"**[Anon-*{anonid}*]**"
			channeltype = self.confessions.bot.config.getint(
				'confessions',
				f"{channel.guild.id}_{channel.id}"
			)

			if not self.confessions.check_banned(channel.guild.id, anonid):
				await inter.response.send_message(
					self.confessions.bot.babel(inter, 'confessions', 'nosendbanned')
				)
				await self.disable(inter)
				return

			content = self.origin.content
			image = self.origin.attachments[0] if self.origin.attachments else None
			if image:
				if not self.confessions.check_imagesupport(channel.guild.id, image):
					await inter.response.send_message(
						self.confessions.bot.babel(inter, 'confessions', 'nosendimages')
					)
					await self.disable(inter)
					return

			vetting = self.confessions.findvettingchannel(channel.guild)
			embed = self.confessions.generate_confession(
				anonid,
				lead if vetting or channeltype != ChannelType.UNTRACEABLE else '',
				content,
				image.url if image else None
			)

			if vetting and channeltype != ChannelType.FEEDBACK:
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
				await inter.response.send_message(
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
				await inter.response.send_message(
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
				lead if vetting or channeltype != ChannelType.UNTRACEABLE else '',
				inter.text_values['content'],
				self.image.url if self.image else None
			)

			if vetting and channeltype != ChannelType.VETTING:
				pendingconfession = ConfessionData(
					self.confessions.bot,
					origin=self.origin,
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
				await inter.response.send_message(
					self.confessions.bot.babel(
						inter,
						'confessions',
						'confession_vetting',
						channel=inter.channel.mention
					),
					ephemeral=True)

				return

			await inter.response.send_message(
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
			except Exception as e:
				print("Failed to fetch required channels or guilds related to a confession;\n"+str(e))
				if accepted:
					await inter.response.send_message(self.bot.babel(
						inter,
						'confessions',
						'vettingrequiredmissing',
						channel=f"<#{pendingconfession.targetchannel_id}>"
					))
					return
			
			if accepted:
				anonid = self.get_anonid(inter.guild.id, pendingconfession.author.id)
				lead = f"**[Anon-*{anonid}*]**"
				channeltype = self.bot.config.getint('confessions', f"{inter.guild.id}_{pendingconfession.targetchannel_id}")
			
				embed = self.generate_confession(
					anonid,
					lead if channeltype != ChannelType.UNTRACEABLE else '',
					pendingconfession.content,
					pendingconfession.image
				)

				if not pendingconfession.author.dm_channel: await pendingconfession.author.create_dm()
				await self.send_confession(pendingconfession.author.dm_channel, pendingconfession.targetchannel, embed)

			await vetmessage.edit(view=None)
			await inter.response.send_message(self.bot.babel(
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
			if(isinstance(pendingconfession.origin, disnake.Message)):
				await pendingconfession.origin.reply(content)
			elif(isinstance(pendingconfession.origin, disnake.Interaction)):
				await pendingconfession.origin.response.send_message(content, ephemeral=True)
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
				self.confession_cooldown[msg.author] = time.time() + self.bot.config.getint('confessions', 'confession_cooldown', fallback=1)
			
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
			
			await msg.reply(self.bot.babel(msg, 'confessions', 'channelprompt'), view=self.ChannelView(msg, self, matches))


	#	Slash commands

	@commands.cooldown(1, 1)
	@commands.slash_command(description="Send an anonymous message")
	async def confess(self, inter: disnake.GuildCommandInteraction,
		content:Optional[str]=commands.Param(None, description="The text of your anonymous message, leave blank for a paragraph editor"),
		image:Optional[disnake.Attachment]=commands.Param(None, description="Include an image, appears below the content")
	):
		""" Confess in the current channel directly """
		if content and 'Log' in self.bot.cogs:
			await self.bot.cogs['Log'].log_misc_str(inter, content + ('*' if image else ''))
		
		if not self.check_channel(inter.guild_id, inter.channel_id):
			await inter.response.send_message(self.bot.babel(inter, 'confessions', 'nosendchannel'), ephemeral=True)
			return
		
		anonid = self.get_anonid(inter.guild_id, inter.author.id)
		lead = f"**[Anon-*{anonid}*]**"
		channeltype = self.bot.config.getint('confessions', f"{inter.guild_id}_{inter.channel_id}")

		if not self.check_banned(inter.guild_id, anonid):
			await inter.response.send_message(self.bot.babel(inter, 'confessions', 'nosendbanned'), ephemeral=True)
			return
		
		if image:
			if not self.check_imagesupport(inter.channel_id, image):
				await inter.response.send_message(self.bot.babel(inter, 'confessions', 'nosendimages'), ephemeral=True)
				return

		if content or image:
			if content is None: content=''

			if not self.check_spam(content):
				await inter.response.send_message(self.bot.babel(inter, 'confessions', 'nospam'), ephemeral=True)
				return
			
			vetting = self.findvettingchannel(inter.guild)
			embed = self.generate_confession(
				anonid,
				lead if vetting or channeltype != ChannelType.UNTRACEABLE else '',
				content,
				image.url if image else None
			)

			if (vetting := self.findvettingchannel(inter.guild)) and channeltype != ChannelType.FEEDBACK:
				pendingconfession = ConfessionData(
					self.bot,
					author=inter.author,
					targetchannel=inter.channel
				)
				
				view = self.PendingConfessionView(self, pendingconfession)

				await vetting.send(self.bot.babel(inter.guild, 'confessions', 'vetmessagecta', channel=inter.channel.mention), embed=embed, view=view)
				await inter.response.send_message(self.bot.babel(inter, 'confessions', 'confession_vetting', channel=inter.channel.mention), ephemeral=True)
				
				return
			
			await inter.response.send_message(self.bot.babel(inter, 'confessions', 'confession_sent_below'), ephemeral=True)
			await self.send_confession(inter, inter.channel, embed)

		else:
			await inter.response.send_modal(modal=self.ConfessionModal(confessions=self, origin=inter, image=image))

	#	Commands

	@commands.guild_only()
	@commands.command()
	async def set(self, ctx:commands.Context, mode:str):
		""" Set a channel for use with ConfessionBot """
		self.bot.cogs['Auth'].admins(ctx)
		type = ChannelType.__dict__.get(mode.upper(), ChannelType.INVALID)
		if type==ChannelType.INVALID:
			raise commands.BadArgument()
		elif type==ChannelType.NONE:
			wastype = self.bot.config.getint('confessions', str(ctx.guild.id)+'_'+str(ctx.channel.id), fallback=ChannelType.NONE)
			if wastype == ChannelType.NONE:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'unsetfailure'))
				return
			self.bot.config.remove_option('confessions', str(ctx.guild.id)+'_'+str(ctx.channel.id))
		else:
			self.bot.config['confessions'][str(ctx.guild.id)+'_'+str(ctx.channel.id)] = str(type)
		self.bot.config.save()

		await ctx.reply(self.bot.babel(ctx, 'confessions', ('setsuccess'+str(type) if type>ChannelType.NONE else 'unsetsuccess'+str(wastype))) +' '+ \
										self.bot.babel(ctx, 'confessions', 'setundo' if type>ChannelType.NONE else 'unsetundo'))

	@commands.command()
	async def list(self, ctx):
		""" List all channels in a server or to a user """
		matches,vetting = self.listavailablechannels(ctx.author)
		# warn users when the channel list isn't complete
		if not self.bot.is_ready():
			await ctx.reply(self.bot.babel(ctx,'confessions','cachebuilding'))
		elif len(matches) == 0:
			await ctx.reply(self.bot.babel(ctx,'confessions','inaccessiblelocal' if isinstance(ctx.author, disnake.Member) else 'inaccessible'))
		else:
			await ctx.reply((self.bot.babel(ctx,'confessions','listtitlelocal') if isinstance(ctx.author, disnake.Member) else self.bot.babel(ctx,'confessions','listtitle')) + \
											 '\n'+self.generate_list(ctx.author, matches, vetting))

	@commands.guild_only()
	@commands.command()
	async def shuffle(self, ctx, one:str = None):
		""" Change all anon-ids on a server """
		if str(ctx.author.id) not in self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='').split(','):
			self.bot.cogs['Auth'].mods(ctx)
		if one:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'shuffleobsoleteone'))
		else:
			if str(ctx.guild.id)+'_banned' in self.bot.config['confessions']:
				msg = await ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflebanresetwarning'))
				def check(m):
					return m.channel == ctx.channel and m.author == ctx.author and m.content.lower() == 'yes'
				try:
					await self.bot.wait_for('message', check=check, timeout=30)
				except asyncio.TimeoutError:
					await ctx.send(self.bot.babel(ctx, 'confessions', 'timeouterror'))
				else:
					self.bot.config.remove_option('confessions', str(ctx.guild.id)+'_banned')
			
			shuffle = self.bot.config.getint('confessions', str(ctx.guild.id)+'_shuffle', fallback=0)
			self.bot.config.set('confessions', str(ctx.guild.id)+'_shuffle', str(shuffle + 1))
			self.bot.config.save()

			await ctx.reply(self.bot.babel(ctx, 'confessions', 'shufflesuccess'))

	@commands.guild_only()
	@commands.command()
	async def imagesupport(self, ctx:commands.Context, cmd:str):
		""" Enable or disable images in confessions """
		self.bot.cogs['Auth'].admins(ctx)
		if cmd=='enable':
			if self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadyenabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = 'True'
				self.bot.config.save()
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportenabled'))
		elif cmd=='disable':
			if not self.bot.config.getboolean('confessions', str(ctx.guild.id)+'_imagesupport', fallback=True):
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportalreadydisabled'))
			else:
				self.bot.config['confessions'][str(ctx.guild.id)+'_imagesupport'] = 'False'
				self.bot.config.save()
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'imagesupportdisabled'))

	@commands.guild_only()
	@commands.command(aliases=['ban'])
	async def block(self, ctx:commands.Context, anonid:str=None):
		""" Block or unblock anon-ids from confessing """
		if str(ctx.author.id) not in self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='').split(','):
			self.bot.cogs['Auth'].mods(ctx)

		banlist = self.bot.config.get('confessions', str(ctx.guild.id)+'_banned', fallback='')
		if anonid is None:
			if banlist:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'banlist') + '\n```' + '\n'.join(banlist.split(',')) + '```')
			else:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'emptybanlist'))
			return
		
		unban = anonid.startswith('-')
		if unban: anonid = anonid[1:]
		
		anonid = anonid.lower()
		if len(anonid)>6:
			anonid = anonid[-6:]
		try: int(anonid, 16)
		except ValueError:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'invalidanonid'))
			return
		if anonid in banlist and not unban:
			await ctx.reply(self.bot.babel(ctx, 'confessions', 'doublebananonid'))
			return
		
		if unban:
			fullid = [i for i in banlist.split(',') if anonid in i][0]
			self.bot.config['confessions'][str(ctx.guild.id)+'_banned'] = banlist.replace(fullid+',','')
		else:
			self.bot.config['confessions'][str(ctx.guild.id)+'_banned'] = banlist + anonid + ','
		self.bot.config.save()

		await ctx.reply(self.bot.babel(ctx, 'confessions', ('un' if unban else '')+'bansuccess', user=anonid))

	@commands.guild_only()
	@commands.command()
	async def botmod(self, ctx:commands.Context, target:str=None):
		""" Grant or take away botmod powers from a user """
		self.bot.cogs['Auth'].admins(ctx)

		modlist = self.bot.config.get('confessions', str(ctx.guild.id)+'_promoted', fallback='')
		if target is None:
			if modlist:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodlist') + '\n```\n' + '\n'.join(modlist.split(',')) + '```')
			else:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodemptylist'))
		elif ctx.message.mentions:
			revoke = target.startswith('-')
			botmodee = [m for m in ctx.message.mentions if m != self.bot.user][0]
			if botmodee.bot:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodboterr'))
				return
			if botmodee.guild_permissions.ban_members:
				await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodmoderr'))
				return

			if revoke:
				if str(botmodee.id) in modlist.split(','):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] = modlist.replace(str(botmodee.id)+',','')
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemotesuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmoddemoteerr'))
			else:
				if str(botmodee.id) not in modlist.split(','):
					self.bot.config['confessions'][str(ctx.guild.id)+'_promoted'] = modlist + str(botmodee.id)+','
					self.bot.config.save()
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'botmodsuccess', user=botmodee.name))
				else:
					await ctx.reply(self.bot.babel(ctx, 'confessions', 'rebotmoderr'))
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

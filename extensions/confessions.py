"""
	Confessions - Anonymous messaging cog
	Features: botmod, bot banning, vetting, image support
	Dependencies: Auth, Help
	Notes: Contains generic command names like set, list, botmod, imagesupport, and ban
		As a result, this only really suits a singlular purpose bot
"""

import os, asyncio, re, time, base64, hashlib
from enum import Enum
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

class CorruptConfessionDataException(Exception):
	""" Thrown when decrypted ConfessionData doesn't fit the required format """

class NoMemberCacheError(Exception):
	""" Unable to continue without a member cache """

class Crypto:
	""" Handles encryption and decryption of sensitive data """
	_key = None

	@property
	def key(self) -> str:
		""" Key getter """
		return self._key

	@key.setter
	def key(self, value:str):
		""" Key setter """
		self._key = base64.decodebytes(bytes(value, encoding='ascii'))

	def setup(self, nonce:bytes = b'\xae[Et\xcd\n\x01\xf4\x95\x9c|No\x03\x81\x98'):
		""" Initializes the AES-256 scheme """
		backend = default_backend()
		cipher = Cipher(algorithms.AES(self._key), modes.CTR(nonce), backend=backend)
		return (cipher.encryptor(), cipher.decryptor())

	def keygen(self, length:int = 32) -> str:
		""" Generates a key for storage """
		return base64.encodebytes(os.urandom(length)).decode('ascii')

	def encrypt(self, data:bytes) -> bytes:
		""" Encodes data and returns a base64 string ready for storage """
		encryptor, _ = self.setup()
		encrypted = encryptor.update(data) + encryptor.finalize()
		encodedata = base64.b64encode(encrypted)
		return encodedata

	def decrypt(self, data:str) -> bytes:
		""" Read encoded data and return the raw bytes that created it """
		_, decryptor = self.setup()
		encrypted = base64.b64decode(data)
		rawdata = decryptor.update(encrypted) + decryptor.finalize()
		return rawdata


class ConfessionData:
	""" Dataclass for Confessions """
	def __init__(
		self,
		bot:commands.Bot,
		crypto:Crypto,
		rawdata:Optional[str]=None,
		*,
		author:Optional[disnake.User]=None,
		origin:Optional[Union[disnake.Message, disnake.Interaction]]=None,
		targetchannel:Optional[disnake.TextChannel]=None,
		embed:Optional[disnake.Embed]=None
	):

		if rawdata:
			self.offline = True

			binary = crypto.decrypt(rawdata)
			if len(binary) != 24:
				raise CorruptConfessionDataException()

			self.author_id = int.from_bytes(binary[0:8], 'big')
			self.origin_id = int.from_bytes(binary[8:16], 'big')
			self.targetchannel_id = int.from_bytes(binary[16:24], 'big')
		else:
			self.offline = False
			self.author = author
			self.origin = origin
			self.targetchannel = targetchannel

		self.bot = bot
		self.crypto = crypto
		self.embed = embed

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

		binary = bauthor + borigin + btarget
		return self.crypto.encrypt(binary).decode('ascii')

	async def fetch(self):
		""" Fetches referenced Discord elements for use """
		if self.offline:
			self.author = await self.bot.fetch_user(self.author_id)
			self.origin = None
			if self.origin_id > 0:
				try:
					self.origin = await self.author.fetch_message(self.origin_id)
				except (disnake.NotFound, disnake.Forbidden):
					pass
			self.targetchannel = await self.bot.fetch_channel(self.targetchannel_id)
			self.offline = False

	def generate_embed(self, anonid:str, lead:str, content:str, image:Optional[str] = None):
		""" Generate the confession embed """
		if lead:
			embed = disnake.Embed(colour=disnake.Colour(int(anonid,16)),description=lead+' '+content)
		else:
			embed = disnake.Embed(description=content if content else '')
		if image:
			embed.set_image(url=image)
		self.embed = embed

	async def handle_send_errors(self, ctx:Union[disnake.DMChannel, disnake.Interaction], func):
		"""
		Wraps around functions that send confessions to channels
		Adds copious amounts of error handling
		"""
		kwargs = {'ephemeral':True} if isinstance(ctx, disnake.Interaction) else {}
		try:
			await func
			return True
		except disnake.Forbidden:
			try:
				await self.targetchannel.send(self.bot.babel(
					self.targetchannel.guild,
					'confessions',
					'missingperms',
					perm='Embed Links'
				))
				await ctx.send(self.bot.babel(ctx, 'confessions', 'embederr'), **kwargs)
			except disnake.Forbidden:
				await ctx.send(
					self.bot.babel(ctx, 'confessions', 'missingchannelerr') + ' (403 Forbidden)',
					**kwargs
				)
		except disnake.NotFound:
			await ctx.send(
				self.bot.babel(ctx, 'confessions', 'missingchannelerr') + ' (404 Not Found)',
				**kwargs
			)
		return False

	async def send_vetting(
		self,
		ctx:Union[disnake.DMChannel, disnake.Interaction],
		confessions,
		vettingchannel:disnake.TextChannel
	):
		""" Send confession to a vetting channel for approval """
		success = await self.handle_send_errors(ctx, vettingchannel.send(
			self.bot.babel(ctx, 'confessions', 'vetmessagecta', channel=self.targetchannel.mention),
			embed=self.embed,
			view=confessions.PendingConfessionView(confessions, self)
		))

		if success:
			await ctx.send(
				self.bot.babel(
					ctx,
					'confessions',
					'confession_vetting',
					channel=self.targetchannel.mention
				),
				ephemeral=True
			)

	async def send_confession(self, ctx:Union[disnake.DMChannel, disnake.Interaction], smsg=False):
		""" Send confession to the destination channel """
		func = self.targetchannel.send(embed=self.embed)
		success = await self.handle_send_errors(ctx, func)

		if success and smsg:
			await ctx.send(self.bot.babel(
				ctx,
				'confessions',
				'confession_sent_below' if ctx.channel == self.targetchannel else 'confession_sent_channel',
				channel=self.targetchannel.mention
			), ephemeral=True)



class Confessions(commands.Cog):
	""" Enable anonymous messaging with moderation on your server """

	channel_icons = {
		ChannelType.untraceable: '🙈',
		ChannelType.traceable: '👁',
		ChannelType.feedback: '📢'
	}

	def __init__(self, bot:commands.Bot):
		self.bot = bot
		self.crypto = Crypto()

		if not bot.config.getboolean('extensions', 'auth', fallback=False):
			raise Exception("'auth' must be enabled to use 'confessions'")
		# ensure config file has required data
		if not bot.config.has_section('confessions'):
			bot.config.add_section('confessions')
		if 'confession_cooldown' not in bot.config['confessions']:
			bot.config['confessions']['confession_cooldown'] = '1'
		if 'secret' not in bot.config['confessions'] or bot.config['confessions']['secret'] == '':
			bot.config['confessions']['secret'] = self.crypto.keygen(32)
			print("WARNING: Your security key has been regenerated. Old confessions are now incompatible.")

		self.crypto.key = bot.config['confessions']['secret']

		# self.initiated = set()
		self.ignore = set()
		self.confession_cooldown = dict()

	#	Utility functions

	def get_anonid(self, guildid:int, userid:int) -> str:
		""" Calculates the current anon-id for a user """
		offset = self.bot.config.getint('confessions', f"{guildid}_shuffle", fallback=0)
		encrypted = self.crypto.encrypt(
			guildid.to_bytes(8, 'big') + userid.to_bytes(8, 'big') + offset.to_bytes(2, 'big')
		)
		return hashlib.sha256(encrypted).hexdigest()[-6:]

	def generate_list(
		self,
		user:disnake.User,
		matches:list[tuple],
		vetting:bool,
		enum:bool=False
	) -> str:
		""" Returns a formatted list of available confession targets """

		targets = []
		for i, match in enumerate(matches):
			targets.append(
				(str(i+1)+':' if enum else '') +\
				f'{self.channel_icons[match[1]]}<#{match[0].id}>' +\
				(' ('+match[0].guild.name+')' if not isinstance(user, disnake.Member) else '')
			)
		vettingwarning = ('\n\n'+self.bot.babel(user, 'confessions', 'vetting') if vetting else '')

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
				channel.name = channel.name[:40] + ('...' if len(channel.name) > 40 else '')
				channel.guild.name = channel.guild.name[:40] + ('...' if len(channel.guild.name) > 40 else '')
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
			if not self.bot.intents.members:
				raise NoMemberCacheError()
			matches = []
			vetting = False
			for guild in self.bot.guilds:
				if member := guild.get_member(user.id):
					newmatches, newvetting = self.scanguild(member)
					matches += newmatches
					vetting = vetting or newvetting

		return matches, vetting

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

	async def safe_fetch_channel(
		self,
		ctx:Union[commands.Context, disnake.ApplicationCommandInteraction],
		channel_id:int
	):
		""" Gracefully handles whenever a confession target isn't available """
		try:
			return await self.bot.fetch_channel(channel_id)
		except disnake.Forbidden:
			await ctx.send(
				self.bot.babel(ctx, 'confessions', 'missingchannelerr') + ' (fetch)',
				**{'ephemeral':True} if isinstance(ctx, disnake.Interaction) else {}
			)
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

	def check_image(self, guild_id:int, image:disnake.Attachment) -> bool:
		""" Only allow images to be sent if imagesupport is enabled and the image is valid """

		if image and image.content_type.startswith('image'):
			if self.bot.config.getboolean('confessions', f"{guild_id}_imagesupport", fallback=True):
				return True
			return False
		raise commands.BadArgument

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
		return str(member.id) in promoted or bool(r for r in member.roles if r.id in promoted)

	#	Views

	class ChannelView(disnake.ui.View):
		""" View for selecting a target interactively """
		def __init__(self, origin:disnake.Message, confessions, matches):
			super().__init__(timeout=30)
			self.origin = origin
			self.confessions = confessions
			self.matches = matches
			self.page = 0
			self.done = False
			self.update_list()
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

			if len(matches) > 25:
				# Add pagination only when needed
				self.page_decrement_button = disnake.ui.Button(
					disabled=True,
					style=disnake.ButtonStyle.secondary,
					label=self.confessions.bot.babel(origin, 'confessions', 'channelprompt_button_prev')
				)
				self.page_decrement_button.callback = self.decrement_page
				self.add_item(self.page_decrement_button)

				self.page_increment_button = disnake.ui.Button(
					disabled=False,
					style=disnake.ButtonStyle.secondary,
					label=self.confessions.bot.babel(origin, 'confessions', 'channelprompt_button_next')
				)
				self.page_increment_button.callback = self.increment_page
				self.add_item(self.page_increment_button)

		def update_list(self):
			"""
				Fill channel selector with channels
				Discord limits this to 25 options, so longer lists need pagination
			"""
			self.channel_selector.options = []
			start = self.page*25
			for channel,channeltype in self.matches[start:start+25]:
				self.channel_selector.append_option(
					disnake.SelectOption(
						label=f'{channel.name} (from {channel.guild.name})',
						value=str(channel.id),
						emoji=Confessions.channel_icons[channeltype]
					)
				)

		@disnake.ui.select(min_values=1, max_values=1)
		async def channel_selector(self, select:disnake.ui.Select, inter:disnake.MessageInteraction):
			""" Update the message to preview the selected target """

			self.send_button.disabled = False
			try:
				channel = await self.confessions.bot.fetch_channel(int(select._selected_values[0]))
			except disnake.Forbidden:
				self.send_button.disabled = True
				await inter.response.edit_message(
					content=self.confessions.bot.babel(inter, 'confessions', 'missingchannelerr') + ' (select)',
					view=self
				)
				return
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

			channel = await self.confessions.safe_fetch_channel(inter, int(self.channel_selector.values[0]))
			if channel is None:
				self.disable(inter)
				return

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

			pendingconfession = ConfessionData(
				self.confessions.bot,
				self.confessions.crypto,
				author=inter.author,
				origin=self.origin,
				targetchannel=channel
			)
			if self.origin.attachments:
				if not self.confessions.check_image(channel.guild.id, self.origin.attachments[0]):
					await inter.send(self.confessions.bot.babel(inter, 'confessions', 'nosendimages'))
					await self.disable(inter)
					return

			vetting = self.confessions.findvettingchannel(channel.guild)
			pendingconfession.generate_embed(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				self.origin.content,
				self.origin.attachments[0].url if self.origin.attachments else None
			)

			if vetting and channeltype != ChannelType.feedback:
				await pendingconfession.send_vetting(inter, self.confessions, vetting)
				await self.disable(inter)
				return

			await pendingconfession.send_confession(inter)

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

		async def decrement_page(self, inter:disnake.MessageInteraction):
			""" Count page down by 1 and handle consequences """
			self.page -= 1
			self.page_increment_button.disabled = False

			if self.page <= 0:
				self.page = 0
				self.page_decrement_button.disabled = True

			self.send_button.disabled = True

			self.update_list()

			await inter.response.edit_message(
				content=self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompt'
				) +' '+ self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompt_pager',
					page=self.page + 1
				),
				view=self
			)

		async def increment_page(self, inter:disnake.MessageInteraction):
			""" Count page up by 1 and handle consequences """
			self.page += 1
			self.page_decrement_button.disabled = False

			if self.page >= len(self.matches) // 25:
				self.page = len(self.matches) // 25
				self.page_increment_button.disabled = True

			self.send_button.disabled = True

			self.update_list()

			await inter.response.edit_message(
				content=self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompt'
				) +' '+ self.confessions.bot.babel(
					inter,
					'confessions',
					'channelprompt_pager',
					page=self.page + 1
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
			try:
				if not self.done:
					await self.origin.reply(
						self.confessions.bot.babel(self.origin.author, 'confessions', 'timeouterror')
					)
				async for msg in self.origin.channel.history(after=self.origin):
					if (
						isinstance(msg.reference, disnake.MessageReference) and
						msg.reference.message_id == self.origin.id
					):
						await msg.delete()
						return
			except disnake.HTTPException:
				pass

	class PendingConfessionView(disnake.ui.View):
		""" Asks moderators to approve or deny a confession as a part of vetting """
		def __init__(self, confessions, pendingconfession:ConfessionData):
			self.confessions = confessions
			self.pendingconfession = pendingconfession
			super().__init__(timeout=None)

			data = self.pendingconfession.store()
			self.add_item(disnake.ui.Button(
				label = confessions.bot.babel(
					self.pendingconfession.targetchannel.guild,
					'confessions',
					'vetting_approve_button'
				),
				emoji = '✅',
				style = disnake.ButtonStyle.blurple,
				custom_id = f"pendingconfession_approve_{data}"
			))

			self.add_item(disnake.ui.Button(
				label = confessions.bot.babel(
					self.pendingconfession.targetchannel.guild,
					'confessions',
					'vetting_deny_button'
				),
				emoji = '❎',
				style = disnake.ButtonStyle.danger,
				custom_id = f"pendingconfession_deny_{data}"
			))

	class ConfessionModal(disnake.ui.Modal):
		""" Modal for completing an incomplete confession """
		def __init__(
			self,
			confessions,
			origin:disnake.ModalInteraction,
			pendingconfession:ConfessionData
		):
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
			self.pendingconfession = pendingconfession

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
				f"{self.pendingconfession.targetchannel.guild.id}_{self.pendingconfession.targetchannel.id}"
			)
			lead = f"**[Anon-*{anonid}*]**"

			vetting = self.confessions.findvettingchannel(inter.guild)
			self.pendingconfession.generate_embed(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				inter.text_values['content']
			)

			if vetting and channeltype != ChannelType.vetting:
				await self.pendingconfession.send_vetting(inter, self.confessions, vetting)
				return

			await self.pendingconfession.send_confession(inter, True)

	#	Events

	@commands.Cog.listener('on_button_click')
	async def on_confession_review(self, inter:disnake.MessageInteraction):
		""" Handle approving and denying confessions """
		if inter.data.custom_id.startswith('pendingconfession_'):
			vetmessage = inter.message

			try:
				if inter.data.custom_id.startswith('pendingconfession_approve_'):
					pendingconfession = ConfessionData(
						self.bot,
						self.crypto,
						inter.data.custom_id[26:],
						embed=vetmessage.embeds[0]
					)
					accepted = True

				elif inter.data.custom_id.startswith('pendingconfession_deny_'):
					pendingconfession = ConfessionData(self.bot, self.crypto, inter.data.custom_id[23:])
					accepted = False
				else:
					print(f"WARN: Unknown button action '{inter.data.custom_id}'!")
					return
			except CorruptConfessionDataException:
				await inter.send(self.bot.babel(inter, 'confessions', 'vetcorrupt'))
				return

			try:
				await pendingconfession.fetch()
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

				pendingconfession.generate_embed(
					anonid,
					lead if channeltype != ChannelType.untraceable else '',
					pendingconfession.content,
					pendingconfession.image
				)

				if not pendingconfession.author.dm_channel:
					await pendingconfession.author.create_dm()
				await pendingconfession.send_confession(inter)

			await vetmessage.edit(view=None)
			await inter.send(self.bot.babel(
				inter.guild,
				'confessions',
				'vetaccepted' if accepted else 'vetdenied',
				user=inter.author.mention,
				channel=f"<#{pendingconfession.targetchannel_id}>"
			))

			content = self.bot.babel(
				pendingconfession.author,
				'confessions',
				'confession_vetting_accepted' if accepted else 'confession_vetting_denied',
				channel=f"<#{pendingconfession.targetchannel_id}>"
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

			try:
				matches,_ = self.listavailablechannels(msg.author)
			except NoMemberCacheError:
				await msg.reply(self.bot.babel(msg, 'confessions', 'dmconfessiondisabled'))
				return

			if not self.bot.is_ready():
				await msg.reply(self.bot.babel(msg, 'confessions', 'cachebuilding'))
				if not matches:
					return

			if not matches:
				await msg.reply(self.bot.babel(msg, 'confessions', 'inaccessible'))
				return

			if not self.check_spam(msg.content):
				await msg.reply(self.bot.babel(msg, 'confessions', 'nospam'))
				return

			await msg.reply(
				self.bot.babel(
					msg,
					'confessions',
					'channelprompt'
				) + (
					' ' + self.bot.babel(msg, 'confessions', 'channelprompt_pager', page=1)
					if len(matches) > 25 else ''
				),
				view=self.ChannelView(msg, self, matches))


	#	Slash commands

	@commands.cooldown(1, 1)
	@commands.slash_command()
	async def confess(
		self,
		inter: disnake.GuildCommandInteraction,
		content:Optional[str] = None,
		image:Optional[disnake.Attachment] = None,
		**kwargs
	):
		"""
		Send an anonymous message to this channel

		Parameters
		----------
		content: The text of your anonymous message, leave blank for a paragraph editor
		image: An optional image that appears below the text
		"""

		if 'channel' in kwargs:
			channel = kwargs['channel']
		else:
			channel = inter.channel

		if not self.check_channel(inter.guild_id, channel.id):
			await inter.send(self.bot.babel(inter, 'confessions', 'nosendchannel'), ephemeral=True)
			return

		anonid = self.get_anonid(inter.guild_id, inter.author.id)
		lead = f"**[Anon-*{anonid}*]**"
		channeltype = self.bot.config.getint('confessions', f"{inter.guild_id}_{channel.id}")

		if not self.check_banned(inter.guild_id, anonid):
			await inter.send(self.bot.babel(inter, 'confessions', 'nosendbanned'), ephemeral=True)
			return

		if image:
			if not self.check_image(inter.guild_id, image):
				await inter.send(self.bot.babel(inter, 'confessions', 'nosendimages'), ephemeral=True)
				return

		pendingconfession = ConfessionData(
			self.bot,
			self.crypto,
			author=inter.author,
			targetchannel=channel
		)

		if content or image:
			if content is None:
				content=''

			if not self.check_spam(content):
				await inter.send(self.bot.babel(inter, 'confessions', 'nospam'), ephemeral=True)
				return

			vetting = self.findvettingchannel(inter.guild)

			pendingconfession.generate_embed(
				anonid,
				lead if vetting or channeltype != ChannelType.untraceable else '',
				content,
				image.url if image else None
			)

			if (
				(vetting := self.findvettingchannel(inter.guild)) and
				channeltype != ChannelType.feedback
				):
				await pendingconfession.send_vetting(inter, self, vetting)
				return

			await pendingconfession.send_confession(inter, True)

		else:
			await inter.response.send_modal(
				modal=self.ConfessionModal(confessions=self, origin=inter, pendingconfession=pendingconfession)
			)

	@commands.cooldown(1, 1)
	@commands.slash_command(name='confess-to')
	async def confess_to(
		self,
		inter:disnake.GuildCommandInteraction,
		channel:str,
		content:Optional[str] = None,
		image:Optional[disnake.Attachment] = None
	):
		"""
		Send an anonymous message to a specified channel

		Parameters
		----------
		channel: The target channel, can include anonymous feedback channels that you can't see
		content: The text of your anonymous message, leave blank for a paragraph editor
		image: An optional image that appears below the text
		"""

		search = re.search(r".*\((\d+)\)$", channel)
		if search:
			channel_id = search.groups()[0]
			targetchannel = await self.safe_fetch_channel(inter, channel_id)
			if targetchannel is None:
				return
			await self.confess(inter, content, image, channel=targetchannel)
		else:
			raise commands.BadArgument("Channel must be selected from the list")
	@confess_to.autocomplete('channel')
	async def channel_ac(self, inter:disnake.GuildCommandInteraction, search:str):
		""" Lists available channels, allows searching by name """
		if not isinstance(inter.author, disnake.Member):
			return [self.bot.babel(inter, 'error', 'noprivatemessage').replace('*','')]

		results = []
		matches, _ = self.scanguild(inter.author)
		for match in matches:
			if search in match[0].name:
				results.append(f"{self.channel_icons[match[1]]} #{match[0].name} ({match[0].id})")
		return results[0:24] + (
			['this list is incomplete, use /list to see all'] if len(results) > 25 else []
		)


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
			self.bot.babel(inter, 'confessions', 'setundo' if mode>ChannelType.none else 'unsetundo') + \
			('\n'+self.bot.babel(inter, 'confessions', 'setcta') if mode>ChannelType.none else '')
		)

	@commands.slash_command()
	async def list(self, inter:disnake.ApplicationCommandInteraction):
		"""
		List all anonymous channels available here
		"""
		try:
			matches, vetting = self.listavailablechannels(inter.author)
		except NoMemberCacheError:
			await inter.send(self.bot.babel(inter, 'confessions', 'dmconfessiondisabled'))
			return

		local = ('local' if isinstance(inter.author, disnake.Member) else '')
		# warn users when the channel list isn't complete
		if not self.bot.is_ready() and not local:
			await inter.send(self.bot.babel(inter,'confessions','cachebuilding'), ephemeral=True)
		elif len(matches) == 0:
			await inter.send(self.bot.babel(inter,'confessions','inaccessible' + local), ephemeral=True)
		# send the list of channels, complete or not
		if len(matches) > 0:
			await inter.send(
				(
					self.bot.babel(inter,'confessions','listtitle' + local) +
					'\n'+self.generate_list(inter.author, matches, vetting) +
					(
						'\n\n' + self.bot.babel(inter, 'confessions', 'confess_to_feedback')
						if [match for match in matches if match[1] == ChannelType.feedback] else ''
					)
				),
				ephemeral=True
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
		banlist_split = banlist.split(',')
		if anonid is None:
			if banlist_split:
				printedlist = '\n```'+'\n'.join(banlist_split)+'```'
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
		if anonid in banlist_split and not unblock:
			await inter.send(self.bot.babel(inter, 'confessions', 'doublebananonid'))
			return

		if unblock:
			fullid = [i for i in banlist_split if anonid in i][0]
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
		target:Optional[Union[disnake.Member, disnake.Role]] = None,
		revoke:Optional[bool] = False
	):
		"""
		Grant or take away botmod powers from a user

		Parameters
		----------
		target: The user or role which will be affected by this command
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
			if isinstance(target, disnake.Member):
				if target.bot:
					await inter.send(self.bot.babel(inter, 'confessions', 'botmodboterr'))
					return
				if target.guild_permissions.ban_members:
					await inter.send(self.bot.babel(inter, 'confessions', 'botmodmoderr'))
					return
			else:
				if target.permissions.ban_members:
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

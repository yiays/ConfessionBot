![ConfessionBot Logo](profile.png)
# ConfessionBot
**ConfessionBot is the most advanced anonymous messaging bot on Discord, with mod tools, multiple anonymous channel types, image support, and much more!** - Powered by the [merely framework](https://github.com/MerelyServices/Merely-Framework) and [disnake](https://github.com/DisnakeDev/disnake).

> Try ConfessionBot on the [Official Bot Discord server](https://discord.gg/wfKx24kDUR)

> [Invite ConfessionBot](https://discord.com/oauth2/authorize?client_id=952453311703941170&permissions=0&scope=bot%20applications.commands) to your own server

## News
Seven languages are now supported! English, German, French, Polish, Brazilian Portugese, Tagalog, and Chinese are all available to choose with `/language set` today, but some are incomplete. *ConfessionBot now also follows your user and server language preferences by default.*
> [See live translation stats and contribute >](https://translate.yiays.com)

ConfessionBot v2.4.0 has launched! This update adds a context menu button for reporting confessions directly to the moderators on the official support server.
> [Read the terms of service >](https://yiays.com/blog/confession-bot-a-side-project/#terms-of-service)

## Usage

### Terms of use
You are welcome to clone this source and run your own instance for any purpose, but **please don't copy the branding of ConfessionBot!**

Clones of ConfessionBot that have the same branding are harmful for our support server and image. Especially if modifications are made which invade users' privacy.

You can easily rename the bot by changing the botname parameter in `config.ini`. You should also use a different Username and profile picture when creating the bot user.

### Setup Instructions
 - Clone the project to a folder
 - Install python <=3.10
 - Install required python packages with `python3 -m pip install -r requirements.txt`
 - Create a discord bot in the [Discord Developer Portal](https://discordapp.com/developers/applications/), you will need the token to continue
    - **[Please don't copy the branding of confessionbot!](#Terms-of-use)**
 - Give ConfessionBot the token by setting it in the [main] section of the config
 - Run your bot with `python3 main.py`
 - Add your ConfessionBot to your server

## Contributing
### Translation
I have built a website which makes it easier to translate my projects, including ConfessionBot. [Babel Translator](https://translate.yiays.com).

### Code contribution
ConfessionBot is written in Python with the help of the disnake API wrapper (like discord.py). Refer to the [Project roadmap](https://github.com/yiays/ConfessionBot-2.0/projects/1) for future features we'd like to implement. All contributions are welcome and support can be given in the [Discord server](https://discord.gg/wfKx24kDUR).

### Design
As the Babel language framework is being used, there's no need to provide strings for your code. Myself and the volunteer translators can add strings later. In place of strings, simply invent a meaningful key, for example;

```py
self.bot.babel('confessions', 'confession_vetting_accepted', channel=channel.mention)
# Appears like the following until a string is written:
"<CONFESSION_VETTING_ACCEPTED: channel={channel}>"
# An example of a written string:
"Your message was accepted and posted to {channel}."
```

All code relevant to ConfessionBot is contained within `extensions/confessions.py`, the rest is a copy from the merelybot framework. Improvements to the framework are shared between both codebases. Refer to `extensions/example.py` to learn the basic formatting and common features of commands.

If you want to make changes to merelybot framework code, consider [committing it directly upstream](https://github.com/MerelyServices/Merely-Framework/). If you feel the improvements would only benefit ConfessionBot, committing it here is fine as well.

### Code structure
`confessions.py` implements the [`disnake.ext.commands.Cog`](https://docs.disnake.dev/en/latest/ext/commands/api.html#cog) class. Read the documentation to learn how to write new commands or improve existing ones with this structure.

If you wish to provide strings, add them to `babel/confessionbot_en.ini`.
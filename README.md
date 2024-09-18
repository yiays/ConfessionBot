![ConfessionBot Logo](profile.png)
# ConfessionBot
**ConfessionBot is the most advanced anonymous messaging bot on Discord, with mod tools, multiple anonymous channel types, image support, and much more!** - Powered by the [merely framework](https://github.com/MerelyServices/Merely-Framework) and [Discord.py](https://github.com/Rapptz/discord.py).

> Try ConfessionBot on the [Official Bot Discord server](https://discord.gg/wfKx24kDUR)

> [Invite ConfessionBot](https://discord.com/oauth2/authorize?client_id=562440687363293195&permissions=0&scope=bot%20applications.commands) to your own server

## News
![New features you might have missed: Compact confessions; admins with premium can enable this in the /controlpanel. Consolidated control; /controlpanel can be used anywhere to tweak advanced settings. Simpler setup; setup your entire server with /setup. More moderation; right click to confess or report confessions. Built-in branding; Admins with premium can now set the text before confessions.](news/Update%20Poster%20-%20Catchup.webp)

![ConfessionBot v2.6: Confession Replies; reply to any message anonymously in the right click menu. Easier channel types; Untraceable and traceable modes have been combined into one new type (Anonymous). Marketplace; A marketplace channel type is available to users who pay for a custom bot. Click to command; click on mentioned commands to use them immediately. Second chances; If you send a confession to an unset channel, you can redirect it.](news/Update%20Poster%20-%20v2.6.webp)

## Usage

### Terms of use
You are welcome to clone this source and run your own instance for any purpose, but **please don't copy the branding of ConfessionBot!**

Clones of ConfessionBot that have the same branding are harmful for our support server and image. Especially if modifications are made which invade users' privacy.

You can easily rename the bot by changing the botname parameter in `config.ini`. You should also use a different Username and profile picture when creating the bot user.

### Setup Instructions
 - Clone [Merely Framework](https://github.com/MerelyServices/Merely-Framework) into a folder
 - Create a subfolder named 'overlay'
 - Clone this project into 'overlay'
 - Install python <=3.10
 - Install required python packages with `python3 -m pip install -r requirements.txt`
 - Create a discord bot in the [Discord Developer Portal](https://discordapp.com/developers/applications/), you will need the token to continue
    - **[Please don't copy the branding of ConfessionBot!](#Terms-of-use)**
 - Give ConfessionBot the token by setting it in the [main] section of the config
 - Run your bot with `python3 main.py`
 - Add your ConfessionBot to your server

## Contributing
### Translation
I have built a website which makes it easier to translate my projects, including ConfessionBot. [Babel Translator](https://translate.yiays.com).

### Code contribution
ConfessionBot is written in Python with the help of the Discord.py API wrapper. Refer to the [Project roadmap](https://github.com/yiays/ConfessionBot-2.0/projects/1) for future features we'd like to implement. All contributions are welcome and support can be given in the [Discord server](https://discord.gg/wfKx24kDUR).

### Design
As the Babel language framework is being used, there's no need to provide strings for your code. Myself and the volunteer translators can add strings later. In place of strings, simply invent a meaningful key, for example;

```py
self.bot.babel('confessions', 'confession_vetting_accepted', channel=channel.mention)
# Appears like the following until a string is written:
"<CONFESSION_VETTING_ACCEPTED: channel={channel}>"
# An example of a written string:
"Your message was accepted and posted to {channel}."
```

**This repository depends on the Merely Framework.** Clone this repo into an overlay folder inside of [Merely Framework](https://github.com/MerelyServices/Merely-Framework) to run this code *(you will need to create the overlay folder)*. Afterwards, any improvements made to the framework can be comitted back upstream without any merge conflicts. *- Contributions to the framework are greatly appreciated!*

### Code structure
`confessions.py` implements the [`discord.ext.commands.Cog`](https://discordpy.readthedocs.io/en/latest/ext/commands/api.html#cog) class. Read the documentation to learn how to write new commands or improve existing ones with this structure.

If you wish to provide strings, add them to `babel/confessionbot_en.ini`.
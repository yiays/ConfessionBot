![ConfessionBot Logo](profile.png)
# ConfessionBot
**ConfessionBot is the most advanced anonymous messaging bot on Discord, with mod tools, multiple anonymous channel types, image support, and much more!** - Powered by the [merely framework](https://github.com/MerelyServices/Merely-Framework) and [Discord.py](https://github.com/Rapptz/discord.py).

> Try ConfessionBot on the [Official Bot Discord server](https://discord.gg/wfKx24kDUR)

> [Invite ConfessionBot](https://discord.com/oauth2/authorize?client_id=562440687363293195&permissions=0&scope=bot%20applications.commands) to your own server

## News
![ConfessionBot v2.6: Confession Replies; reply to any message anonymously in the right click menu. Easier channel types; Untraceable and traceable modes have been combined into one new type (Anonymous). Marketplace; A marketplace channel type is available to users who pay for a custom bot. Click to command; click on mentioned commands to use them immediately. Second chances; If you send a confession to an unset channel, you can redirect it.](news/Update%20Poster%20-%20v2.6.webp)

## Usage

### Terms of use
You are welcome to clone this source and run your own instance for any purpose, but **please don't copy the branding of ConfessionBot!**

Clones of ConfessionBot that have the same branding are harmful for our support server and image.

You can easily rename the bot by changing the botname parameter in `config.ini`. You should also use a different Username and profile picture when creating the bot user.

### Setup Instructions
 - Clone [Merely Framework](https://github.com/MerelyServices/Merely-Framework) into a folder
   - ```sh
     git clone https://github.com/MerelyServices/Merely-Framework.git ConfessionBot
 - Clone this project into a subfolder named 'overlay'
   - ```sh
     cd ConfessionBot
     git clone https://github.com/yiays/ConfessionBot.git overlay
 - Install python >= 3.12
 - Install required python packages
   - ```sh
     python3 -m pip install -r requirements.txt -r overlay/requirements.txt
 - Run your bot once to generate the config file; `python3 main.py`
 - Create a discord bot in the [Discord Developer Portal](https://discordapp.com/developers/applications/), you will need the token
    - **[Please don't copy the branding of ConfessionBot!](#Terms-of-use)**
 - Give ConfessionBot the token by setting it in the `[main]` section of the config (overlay/config/config.ini)
   - **Never put your token in config.factory.ini** - this file is public when you commit to GitHub.
 - Run your bot with `python3 main.py`
 - Add your bot to your server, use the id from the Discord Developer Portal in the following link;
   - `https://discord.com/oauth2/authorize?client_id=PASTE_ID_HERE`
 - *Optional*: change the behaviour and features of your bot in the `config/config.ini` file.
   - Restart the bot to apply changes; `/die restart:true`

### Updating
To update, first shut down your bot gracefully with `/die`, then use the following commands.

```sh
$ git pull
$ pip install -r requirements.txt -r overlay/requirements.txt
```

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
![ConfessionBot Logo](profile.png)
# ConfessionBot
**ConfessionBot is the most advanced anonymous messaging bot on Discord, with mod tools, multiple anonymous channel types, image support, and much more!** - Powered by the [merely framework](https://github.com/MerelyServices/Merely-Framework) and [disnake](https://github.com/DisnakeDev/disnake).

> Demo ConfessionBot on my [Discord server](https://discord.gg/wfKx24kDUR)

> [Invite ConfessionBot](https://discord.com/oauth2/authorize?client_id=952453311703941170&permissions=0&scope=bot%20applications.commands) to your own server

## News
Translation tooling for my projects (including ConfessionBot) has launched! contribute translations with the help of this tooling and see your language become available in all sorts of places!
> [try it now >](https://translate.yiays.com)

Version 2.0 has launched, this rebased the project on the merelybot framework and drastically increased the capability of the translation system. *Use `cb!changes` for more info*.
> [see the roadmap for future updates >](https://github.com/yiays/ConfessionBot-2.0/projects/1)

## Usage

### Terms of use
You're welcome to clone this source and run your own instance for any purpose, but **please don't copy the branding of ConfessionBot!**

I ask this of you because I don't want to recieve support requests from forks of ConfessionBot that have nothing to do with me. The confusion would waste a lot of people's time.

You can easily rename the bot by changing the botname parameter in `config.ini`. You should also use a different Username and profile picture when creating the bot user.

### Setup Instructions
 - Clone the project to a folder
 - Install python <=3.9
 - Install required python packages with `python3 -m pip install -r requirements.txt`
 - Create a discord bot in the [Discord Developer Portal](https://discordapp.com/developers/applications/), you will need the token to continue
    - **[Please don't copy the branding of confessionbot!](#Terms-of-use)**
 - Give ConfessionBot the token by setting it in the [main] section of the config
 - Run your bot with `python3 main.py`
 - Add your ConfessionBot to your server

## Contributing
ConfessionBot is written in Python with the help of the disnake API wrapper (like discord.py). Any help would be greatly appreciated as I'm finding myself more busy with other projects these days.

### Design
All code relevant to ConfessionBot is contained within `extensions/confessions.py`, the rest is a direct copy from the merelybot framework, if you want to make changes to merelybot framework code, consider [committing it directly upstream](https://github.com/MerelyServices/Merely-Framework/).

### Code structure
`confessions.py` implements the [`disnake.ext.commands.Cog`](https://docs.disnake.dev/en/latest/ext/commands/api.html#cog) class. Read the documentation to learn how to write new commands or improve existing ones with this structure.
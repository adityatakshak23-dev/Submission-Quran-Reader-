import os
import re
import discord
from discord import app_commands
from source import SetupError, get_quran_text, adjacent_reference, validate_reference, reader_lock

GUILD = discord.Object(id=int(os.getenv("GUILD_ID", "911268076933230662")))
CHANNELS = {int(i.strip()) for i in os.getenv("READER_CHANNEL_IDS", "915639051967676496,915639080119849030,1075986349607358544,1082833497812648046").split(",")}

class Reader(discord.Client):
    async def setup_hook(self):
        await tree.sync(guild=GUILD)
        print("Registered /quran for server", GUILD.id, flush=True)

client = Reader(intents=discord.Intents(guilds=True))
tree = app_commands.CommandTree(client)

def panel(c, v, data, plain, owner):
    embed = discord.Embed(title=f"[{c}:{v}]", description=data[c,v])
    embed.set_footer(text="Submission.org · Quran Inspector · English")
    view = discord.ui.View(timeout=3600)
    for delta, label in ((-1,"Previous"),(1,"Next")):
        try:
            target = adjacent_reference(c,v,delta)
        except SetupError:
            target = None
        button = discord.ui.Button(label=label, disabled=target is None)
        async def move(it, dest=target):
            if it.user.id != owner:
                return await it.response.send_message("Start your own reading with /quran.",ephemeral=True)
            e,w = panel(*dest,data,plain,owner)
            await it.response.edit_message(embed=e,view=w)
            view.stop()
        button.callback = move
        view.add_item(button)
    if not plain:
        view.add_item(discord.ui.Button(label="Source and notes",url=f"https://submission.org/QI#{c}:{v}"))
    return embed,view

@tree.command(name="quran",description="Read an English Quran verse in this VC chat.",guild=GUILD)
@app_commands.describe(verse="Chapter:verse, for example 2:255",no_commentary="Show just the verse without the notes link")
@app_commands.rename(no_commentary="no-commentary")
async def quran(it: discord.Interaction, verse: str, no_commentary: bool=False):
    if it.channel_id not in CHANNELS:
        return await it.response.send_message("Use /quran in a configured VC text chat.",ephemeral=True)
    match = re.fullmatch(r"([0-9]{1,3})\s*:\s*([0-9]{1,3})",verse.strip())
    try:
        if not match:
            raise SetupError("Enter a chapter and verse like 2:255.")
        c,v=map(int,match.groups())
        validate_reference(c,v)
    except SetupError as exc:
        return await it.response.send_message(str(exc),ephemeral=True)
    await it.response.defer()
    try:
        async with reader_lock:
            data=await get_quran_text()
    except SetupError as exc:
        return await it.edit_original_response(content=str(exc))
    embed,view=panel(c,v,data,no_commentary,it.user.id)
    await it.edit_original_response(embed=embed,view=view)

client.run(os.environ["DISCORD_TOKEN"])

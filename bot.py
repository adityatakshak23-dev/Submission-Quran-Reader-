import asyncio
import logging
import os
import re
import discord
from discord import app_commands
from source import (InputError, refs, indices, parse_reference, reference_label,
                    render_passage, render_appendix, appendix_path)

GUILD = discord.Object(id=int(os.getenv('GUILD_ID', '911268076933230662')))
CHANNELS = {int(i.strip()) for i in os.getenv('READER_CHANNEL_IDS', '915639051967676496,915639080119849030,1075986349607358544,1082833497812648046').split(',') if i.strip()}
NO_MENTIONS = discord.AllowedMentions.none()
render_lock = asyncio.Lock()

class Reader(discord.Client):
    async def setup_hook(self):
        await tree.sync(guild=GUILD)
        print('Quran Reader v5: offline edition, God casing, ranges, /appendix and saved study progress. Server:', GUILD.id, flush=True)

client = Reader(intents=discord.Intents(guilds=True,guild_messages=True,message_content=True),allowed_mentions=NO_MENTIONS)
tree = app_commands.CommandTree(client)

async def render(kind, first, last, page):
    # PyMuPDF operations are serialised; never run concurrent rendering threads.
    async with render_lock:
        if kind == 'quran':
            return await asyncio.to_thread(render_passage, first, last, page)
        return await asyncio.to_thread(render_appendix, first, page)

async def panel(kind,first,last,owner,page=0):
    image,total=await render(kind,first,last,page)
    title=f'[{reference_label(first,last)}]' if kind=='quran' else (f'Appendix {first}' if first is not None else 'Appendix index')
    embed=discord.Embed(title=title,description='Quran: The Final Testament · English')
    embed.set_image(url='attachment://reading.png')
    embed.set_footer(text=f'Page {page+1} of {total}')
    file=discord.File(image,filename='reading.png')
    view=discord.ui.View(timeout=3600)
    single=kind=='quran' and first==last and total==1
    for delta,label in ((-1,'Previous verse' if single else 'Previous page'),(1,'Next verse' if single else 'Next page')):
        target=indices[first]+delta if single else page+delta
        valid=0<=target<(len(refs) if single else total)
        button=discord.ui.Button(label=label,disabled=not valid)
        async def move(it,dest=target):
            if it.user.id!=owner:
                return await it.response.send_message('Start your own reading with /quran or /appendix.',ephemeral=True)
            await it.response.defer()
            try:
                if single:
                    e,f,w=await panel(kind,refs[dest],refs[dest],owner)
                else:
                    e,f,w=await panel(kind,first,last,owner,dest)
                await it.edit_original_response(embed=e,attachments=[f],view=w)
                view.stop()
            except Exception:
                logging.exception('Reader navigation failed')
                await it.followup.send('Could not load that page. Please run the command again.',ephemeral=True)
        button.callback=move; view.add_item(button)
    if kind=='appendix':
        download=discord.ui.Button(label='Download PDF')
        async def send_pdf(it):
            await it.response.defer(ephemeral=True)
            await it.followup.send(file=discord.File(appendix_path(first),filename=f'Appendix-{first or "index"}.pdf'),ephemeral=True)
        download.callback=send_pdf; view.add_item(download)
    return embed,file,view

@client.event
async def on_message(m):
    if m.author.bot or m.webhook_id or not m.guild or m.guild.id!=GUILD.id or m.channel.id not in CHANNELS:
        return
    if not re.match(r'^[qQ]\s*[0-9]',m.content.strip()):return
    try:
        first,last=parse_reference(m.content)
        e,f,w=await panel('quran',first,last,m.author.id)
        await m.channel.send(embed=e,file=f,view=w)
    except InputError as exc:
        await m.channel.send(str(exc))
    except Exception:
        logging.exception('Reader request failed')
        try: await m.channel.send('Could not display the passage. Check that the reader has Attach Files permission and try again.')
        except discord.HTTPException: pass

@tree.command(name='quran',description='Read a verse or verse range from the English edition.',guild=GUILD)
@app_commands.describe(verse='Chapter:verse or chapter:first-last, for example 1:1-7')
async def quran(it:discord.Interaction,verse:str):
    if it.guild_id!=GUILD.id or it.channel_id not in CHANNELS:
        return await it.response.send_message('Use this in a configured VC text chat.',ephemeral=True)
    try:first,last=parse_reference(verse)
    except InputError as exc:return await it.response.send_message(str(exc),ephemeral=True)
    await it.response.defer()
    e,f,w=await panel('quran',first,last,it.user.id)
    await it.edit_original_response(embed=e,attachments=[f],view=w)

@tree.command(name='appendix',description='Read an appendix or see the index of all 38.',guild=GUILD)
@app_commands.describe(number='Choose 1–38, or leave blank for the index')
async def appendix(it:discord.Interaction,number:app_commands.Range[int,1,38]=None):
    if it.guild_id!=GUILD.id or it.channel_id not in CHANNELS:
        return await it.response.send_message('Use this in a configured VC text chat.',ephemeral=True)
    await it.response.defer()
    e,f,w=await panel('appendix',number,None,it.user.id)
    await it.edit_original_response(embed=e,attachments=[f],view=w)

study_lock = asyncio.Lock()
STUDY_HOST_IDS = {int(v.strip()) for v in os.getenv('STUDY_HOST_IDS', '').split(',') if v.strip().isdigit()}

@tree.command(name='study_update', description='Host: save the verse or range actually read in Quran study.', guild=GUILD)
@app_commands.describe(verse='Last passage read, for example 1:1-7 or 2:225')
async def study_update(it: discord.Interaction, verse: str):
    if it.guild_id != GUILD.id:
        return await it.response.send_message('Use this in Submission.', ephemeral=True)
    if not (it.user.id in STUDY_HOST_IDS or it.user.guild_permissions.administrator):
        return await it.response.send_message('Only a designated study host or administrator can update study progress.', ephemeral=True)
    try:
        parse_reference(verse)
    except InputError as exc:
        return await it.response.send_message(str(exc), ephemeral=True)
    await it.response.defer(ephemeral=True)
    from study import record
    async with study_lock:
        entry = record(verse, it.user.id)
    await it.followup.send(f"Saved study passage: **{entry['passage']}**. Last verse read: **{entry['last_verse']}**.", ephemeral=True)

@tree.command(name='study_latest', description='Show the latest saved Quran study passage.', guild=GUILD)
async def study_latest(it: discord.Interaction):
    if it.guild_id != GUILD.id:
        return await it.response.send_message('Use this in Submission.', ephemeral=True)
    from study import load
    async with study_lock:
        history = load()['history']
    if not history:
        return await it.response.send_message('No study passage saved in this reader yet. A host can use /study_update.', ephemeral=True)
    entry = history[-1]
    embed = discord.Embed(title='Latest Quran study', description=f"Passage read: **{entry['passage']}**\nLast verse read: **{entry['last_verse']}**")
    embed.set_footer(text='Saved ' + entry['recorded_at'])
    await it.response.send_message(embed=embed)

@tree.error
async def command_error(it,error):
    logging.error('Reader command failed',exc_info=(type(error),error,error.__traceback__))
    text='Could not load the reading. Check Attach Files permission and that all files from the update were uploaded.'
    if it.response.is_done():await it.followup.send(text,ephemeral=True)
    else:await it.response.send_message(text,ephemeral=True)

if __name__=='__main__':
    token=os.getenv('DISCORD_TOKEN','').strip()
    if not token:raise SystemExit('Add DISCORD_TOKEN to this Quran Reader service in Railway, then deploy.')
    client.run(token)

import asyncio
import logging
import os
import re
import discord
from discord import app_commands
from source import (InputError, refs, indices, parse_reference, reference_label,
                    render_passage, render_appendix, appendix_path, passage_text_pages)

GUILD = discord.Object(id=int(os.getenv('GUILD_ID', '911268076933230662')))
CHANNELS = {int(i.strip()) for i in os.getenv('READER_CHANNEL_IDS', '915639051967676496,915639080119849030,1075986349607358544,1082833497812648046').split(',') if i.strip()}
NO_MENTIONS = discord.AllowedMentions.none()
render_lock = asyncio.Lock()

class Reader(discord.Client):
    async def setup_hook(self):
        await tree.sync(guild=GUILD)
        print('Quran Reader v8: Quran text, headings, footnotes, semantic search, ranges, appendices and saved study progress. Server:', GUILD.id, flush=True)

client = Reader(intents=discord.Intents(guilds=True,guild_messages=True,message_content=True),allowed_mentions=NO_MENTIONS)
tree = app_commands.CommandTree(client)

async def render(kind, first, last, page):
    # PyMuPDF operations are serialised; never run concurrent rendering threads.
    async with render_lock:
        if kind == 'quran':
            return await asyncio.to_thread(render_passage, first, last, page)
        return await asyncio.to_thread(render_appendix, first, page)

async def panel(kind,first,last,owner,page=0):
    if kind == 'quran':
        async with render_lock:
            pages = await asyncio.to_thread(passage_text_pages, first, last)
        total = len(pages)
        image = None
    else:
        image,total=await render(kind,first,last,page)
    if page == -1: page = total - 1
    title=f'[{reference_label(first,last)}]' if kind=='quran' else (f'Appendix {first}' if first is not None else 'Appendix index')
    embed=discord.Embed(title=title,description='Quran: The Final Testament · English')
    if kind == 'quran':
        embed.description = pages[page]
    else:
        embed.set_image(url='attachment://reading.png')
    embed.set_footer(text=f'Page {page+1} of {total}')
    file=discord.File(image,filename='reading.png') if image is not None else None
    view=discord.ui.View(timeout=3600)
    # Move within a long passage first, then continue with an equally sized range.
    for delta in (-1, 1):
        next_first, next_last, next_page = first, last, page + delta
        valid = 0 <= next_page < total
        label = 'Previous page' if delta < 0 else 'Next page'
        if kind == 'quran' and not valid:
            width = indices[last] - indices[first] + 1
            start = indices[first] - width if delta < 0 else indices[last] + 1
            end = indices[first] - 1 if delta < 0 else start + width - 1
            valid = end >= 0 and start < len(refs)
            if valid:
                next_first, next_last = refs[max(0, start)], refs[min(len(refs)-1, end)]
            next_page = -1 if delta < 0 else 0
            label = 'Previous verses' if delta < 0 else 'Next verses'
        button = discord.ui.Button(label=label, disabled=not valid)
        async def move(it, nf=next_first, nl=next_last, np=next_page):
            if kind == 'appendix' and it.user.id != owner:
                return await it.response.send_message('Start your own appendix with /appendix.', ephemeral=True)
            await it.response.defer()
            try:
                e,f,w = await panel(kind,nf,nl,owner,np)
                await it.edit_original_response(embed=e,attachments=[f] if f is not None else [],view=w)
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
        await m.channel.send(embed=e,view=w,**({"file": f} if f is not None else {}))
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
    await it.edit_original_response(embed=e,attachments=[f] if f is not None else [],view=w)

@tree.command(name='appendix',description='Read an appendix or see the index of all 38.',guild=GUILD)
@app_commands.describe(number='Choose 1–38, or leave blank for the index')
async def appendix(it:discord.Interaction,number:app_commands.Range[int,1,38]=None):
    if it.guild_id!=GUILD.id or it.channel_id not in CHANNELS:
        return await it.response.send_message('Use this in a configured VC text chat.',ephemeral=True)
    await it.response.defer()
    e,f,w=await panel('appendix',number,None,it.user.id)
    await it.edit_original_response(embed=e,attachments=[f] if f is not None else [],view=w)

@tree.command(name='quran_search', description='Find Quran verses by words, phrases, or meaning.', guild=GUILD)
@app_commands.describe(query='For example: comfort during hardship, or doubts and hypocrisy')
async def quran_search(it: discord.Interaction, query: str):
    if it.guild_id != GUILD.id or it.channel_id not in CHANNELS:
        return await it.response.send_message('Use this in a configured VC text chat.', ephemeral=True)
    if not 2 <= len(query.strip()) <= 300:
        return await it.response.send_message('Enter between 2 and 300 characters.', ephemeral=True)
    await it.response.defer()
    try:
        from search import search_verses
        matches = await asyncio.to_thread(search_verses, query)
    except Exception:
        logging.exception('Semantic search failed')
        return await it.edit_original_response(content='Search is unavailable. Check the Railway search-index build logs; verse reading still works.')
    embed = discord.Embed(title='Quran search', description='Possible matches. Select a verse to read its full text and notes.')
    view = discord.ui.View(timeout=3600)
    for ref, entry in matches:
        preview = entry['text']
        if len(preview) > 650: preview = preview[:647] + '…'
        embed.add_field(name=f'[{ref}]', value=preview, inline=False)
        button = discord.ui.Button(label=ref)
        async def open_verse(interaction, selected=ref):
            await interaction.response.defer()
            e,f,w = await panel('quran', selected, selected, interaction.user.id)
            await interaction.followup.send(embed=e, view=w)
        button.callback = open_verse
        view.add_item(button)
    embed.set_footer(text='Matches by meaning and wording • Quran: The Final Testament')
    await it.edit_original_response(embed=embed, view=view)

study_lock = asyncio.Lock()
STUDY_HOST_IDS = {int(v.strip()) for v in os.getenv('STUDY_HOST_IDS', '').split(',') if v.strip().isdigit()}

STUDY_ROLE_IDS = {int(v.strip()) for v in os.getenv('STUDY_ROLE_IDS', '').split(',') if v.strip().isdigit()}

async def study_access(it):
    if it.guild_id != GUILD.id:
        return False
    if it.user.id in STUDY_HOST_IDS or it.permissions.administrator:
        return True
    if it.guild and it.guild.owner_id == it.user.id:
        return True
    member = it.user
    if it.guild:
        try:
            member = await it.guild.fetch_member(it.user.id)
        except discord.HTTPException:
            pass
    return (getattr(member, 'guild_permissions', discord.Permissions.none()).administrator
            or any(r.id in STUDY_ROLE_IDS for r in getattr(member, 'roles', [])))

@tree.command(name='study_access', description='Check your Grand Quran Study update access.', guild=GUILD)
async def study_access_command(it: discord.Interaction):
    await it.response.defer(ephemeral=True)
    allowed = await study_access(it)
    roles = ', '.join(f'{r.name} ({r.id})' for r in getattr(it.user, 'roles', []) if not r.is_default()) or 'None'
    await it.followup.send(
        f'Reader v8 | Study update allowed: {allowed}\n'
        f'Your user ID: {it.user.id}\n'
        f'Discord Administrator permission: {it.permissions.administrator}\n'
        f'Roles: {roles}'[:1900], ephemeral=True)

@tree.command(name='study_update', description='Host: save the verse or range actually read in Quran study.', guild=GUILD)
@app_commands.describe(verse='Last passage read, for example 1:1-7 or 2:225')
async def study_update(it: discord.Interaction, verse: str):
    if it.guild_id != GUILD.id:
        return await it.response.send_message('Use this in Submission.', ephemeral=True)
    await it.response.defer(ephemeral=True)
    if not await study_access(it):
        return await it.followup.send('Study access is not configured for your account. Run /study_access and send its result to the bot maintainer.', ephemeral=True)
    try:
        parse_reference(verse)
    except InputError as exc:
        return await it.followup.send(str(exc), ephemeral=True)
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
    embed = discord.Embed(title='Latest Grand Quran Study', description=f"Passage read: **{entry['passage']}**\nLast verse read: **{entry['last_verse']}**")
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

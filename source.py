"""Offline reading from the supplied English edition; no scripture web service."""
from io import BytesIO
import json
import re
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent
locations = json.loads((ROOT / 'locations.json').read_text())
refs = list(locations)
indices = {key: i for i, key in enumerate(refs)}
REFERENCE = re.compile(r'(?:[qQ]\s*)?([0-9]{1,3})(?:\s*:\s*|\s+)([0-9]{1,3})(?:\s*[-–]\s*([0-9]{1,3}))?')
MAX_HEIGHT = 510

class InputError(ValueError):
    pass

def parse_reference(value):
    match = REFERENCE.fullmatch(value.strip())
    if not match:
        raise InputError('Use q1:1-7 or q2:225. With /quran, enter 1:1-7 or 2:225.')
    chapter, first = map(int, match.groups()[:2])
    last = int(match.group(3) or first)
    if last < first:
        raise InputError('The ending verse must be the same as or greater than the starting verse.')
    selected = [f'{chapter}:{verse}' for verse in range(first, last + 1)]
    if not selected or any(ref not in indices for ref in selected):
        raise InputError('That verse or range is not in the supplied edition. Use a range within one chapter.')
    return selected[0], selected[-1]

def reference_label(first, last):
    return first if first == last else f'{first}-{last.split(":")[1]}'

def passage_strips(doc, first, last):
    page, col, y = locations[first]
    last_page, last_col, last_y = locations[last]
    i = indices[last] + 1
    endpage, endcol, end_y = locations[refs[i]] if i < len(refs) else (last_page, last_col, 606)
    # At chapter boundaries, stop before a new chapter heading or footnote.
    if i == len(refs) or refs[i].split(':')[0] != last.split(':')[0]:
        x1,x2 = (32,404) if last_page == 0 else ((30,218) if last_col == 0 else (214,405))
        candidates=[]
        for block in doc[last_page].get_text('dict')['blocks']:
            for line in block.get('lines', []):
                text=''.join(s['text'] for s in line['spans']).strip()
                box=fitz.Rect(line['bbox'])
                if box.y0 > last_y + 3 and x1 <= box.x0 < x2 and (text.startswith('*') or re.match(r'Sura\s+\d+',text)):
                    candidates.append(box.y0)
        if candidates:
            endpage, endcol, end_y = last_page, last_col, min(candidates)
    strips=[]
    for pn in range(page,endpage+1):
        for side in range(1 if pn==0 else 2):
            if not (page,col) <= (pn,side) <= (endpage,endcol):
                continue
            top=max(0,y-2) if (pn,side)==(page,col) else 53
            bottom=end_y-2 if (pn,side)==(endpage,endcol) else 606
            x1,x2=(32,404) if pn==0 else ((30,218) if side==0 else (214,405))
            if bottom-top >= 8:
                strips.append((pn,fitz.Rect(x1,top,x2,bottom)))
    if not strips:
        raise InputError('This passage could not be rendered.')
    return strips

def passage_pages(doc, first, last):
    """Bound image sizes; long ranges remain navigable without truncation."""
    pages=[]; current=[]; height=0
    for pn, rect in passage_strips(doc,first,last):
        top=rect.y0
        while top < rect.y1:
            space=MAX_HEIGHT-height
            if space < 12:
                pages.append(current); current=[]; height=0; space=MAX_HEIGHT
            bottom=min(rect.y1,top+space-4)
            current.append((pn,fitz.Rect(rect.x0,top,rect.x1,bottom)))
            height+=bottom-top+4; top=bottom
    if current: pages.append(current)
    return pages

def render_passage(first,last,page_number=0):
    with fitz.open(ROOT/'reading.pdf') as doc:
        pages=passage_pages(doc,first,last)
        if not 0 <= page_number < len(pages): raise InputError('Page is outside this passage.')
        strips=pages[page_number]
        with fitz.open() as out:
            width=max(r.width for _,r in strips)
            height=sum(r.height+4 for _,r in strips)
            page=out.new_page(width=width,height=height); offset=0
            for pn,r in strips:
                page.show_pdf_page(fitz.Rect(0,offset,r.width,offset+r.height),doc,pn,clip=r)
                offset+=r.height+4
            return BytesIO(page.get_pixmap(matrix=fitz.Matrix(2.4,2.4)).tobytes('png')),len(pages)

def appendix_path(number):
    if number is not None and (type(number) is not int or not 1 <= number <= 38):
        raise InputError('Choose an appendix from 1 to 38.')
    return ROOT/'appendices'/(f'{number}.pdf' if number is not None else 'index.pdf')

def render_appendix(number,page_number=0):
    with fitz.open(appendix_path(number)) as doc:
        if not 0 <= page_number < len(doc): raise InputError('Page is outside this appendix.')
        return BytesIO(doc[page_number].get_pixmap(matrix=fitz.Matrix(1.8,1.8)).tobytes('png')),len(doc)

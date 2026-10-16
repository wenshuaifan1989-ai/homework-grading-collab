"""Versioned local PDF templates and teacher geometry registration."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.utils import ImageReader
from models.known_assignment import PageTemplate, QuestionPlacement
from models.learning import AssignmentVariantQuestion
from services.storage_provider import LocalStorageProvider
from services.known_page_vision import png, load_image


def store(data, suffix='.png'):
    return LocalStorageProvider().store_bytes(data,task_id='known',image_index=0,filename='file'+suffix,content_type=None)


def questions(db, variant_id):
    return db.query(AssignmentVariantQuestion).filter_by(variant_id=variant_id).order_by(AssignmentVariantQuestion.sort_order,AssignmentVariantQuestion.id).all()


def fingerprint(rows):
    values=[(q.id,q.source_asset_id,q.question_text,q.options_json,q.correct_answer,str(q.max_score)) for q in rows]
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def rasterize_pdf(data):
    binary=shutil.which('pdftoppm')
    if not binary:
        raise ValueError('Poppler pdftoppm is required for local PDF mapping')
    with tempfile.TemporaryDirectory(prefix='known-pdf-') as folder:
        path=Path(folder)/'source.pdf'
        path.write_bytes(data)
        subprocess.run([binary,'-r','144','-f','1','-l','10','-png',str(path),str(Path(folder)/'page')],check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        files=sorted(Path(folder).glob('page-*.png'))
        if not 1 <= len(files) <= 9:
            raise ValueError('Only 1-9 PDF pages supported')
        return [load_image(p) for p in files]


def render_pdf(title, rows, page_uids):
    """Coordinates use top-left pixels at 144 dpi; brackets follow wrapped stem."""
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    buffer=BytesIO()
    width,height=595.2756,841.8898
    c=canvas.Canvas(buffer,pagesize=(width,height))
    pages=[]
    placements=[]
    page_index=-1
    y=0
    def start():
        nonlocal y,page_index,placements
        if page_index >= 0:
            pages.append(placements)
            c.showPage()
        page_index+=1
        if page_index >= 9:
            raise ValueError('Generated paper exceeds nine pages')
        placements=[]
        uid=page_uids[page_index]
        code=cv2.QRCodeEncoder_create().encode(uid)
        code=cv2.copyMakeBorder(code,4,4,4,4,cv2.BORDER_CONSTANT,value=255)
        c.drawImage(ImageReader(Image.fromarray(code)),width-86,height-86,48,48)
        c.setFont('STSong-Light',14)
        c.drawString(40,height-46,title[:28])
        c.setFont('Helvetica',7)
        c.drawString(40,height-64,uid)
        c.drawString(40,24,f'Page {page_index+1} / Known assignment')
        c.setFont('STSong-Light',11)
        y=height-104
    def box(x1,top,x2,bottom):
        return [round(x1*2),round((height-top)*2),round(x2*2),round((height-bottom)*2)]
    start()
    for idx,q in enumerate(rows):
        options=q.options_json
        if not options:
            raise ValueError('Only choice questions with four options can register a bracket template')
        if isinstance(options,list):
            opts={chr(65+i):str(v) for i,v in enumerate(options)}
        else:
            opts={str(k).rstrip('.、').upper():str(v) for k,v in options.items()}
        if set(opts) != set('ABCD'):
            raise ValueError('Choice question must contain A/B/C/D options')
        stem=f'{idx+1}. '+re.sub(r'[（(]\s*[）)]\s*[。.]?$', '',q.question_text.strip())
        lines=[]; line=''
        for ch in stem:
            if ch=='\n' or pdfmetrics.stringWidth(line+ch,'STSong-Light',11)>440:
                lines.append(line); line='' if ch=='\n' else ch
            else:
                line+=ch
        lines.append(line)
        if pdfmetrics.stringWidth(lines[-1],'STSong-Light',11)>360:
            lines.append('')
        # Options are separately wrapped, never used as answer regions.
        option_lines=[]
        for letter in 'ABCD':
            line=letter+'. '
            for ch in opts[letter]:
                if pdfmetrics.stringWidth(line+ch,'STSong-Light',11)>440:
                    option_lines.append(line);line='  '+ch
                else:
                    line+=ch
            option_lines.append(line)
        need=(len(lines)+len(option_lines))*19+40
        if need>650:
            raise ValueError('Question too long for one template page')
        if y-need<48:
            start()
        top=y+18
        for line in lines:
            c.drawString(40,y,line);y-=19
        baseline=y+19
        bx=40+pdfmetrics.stringWidth(lines[-1],'STSong-Light',11)+6
        c.drawString(bx,baseline,'（')
        c.drawString(bx+58,baseline,'）')
        bracket=box(bx-2,baseline+16,bx+72,baseline-5)
        stem_box=box(38,top,520,baseline-6)
        y-=6
        otop=y+13
        for line in option_lines:
            c.drawString(54,y,line);y-=19
        obox=box(50,otop,520,y+5)
        placements.append({'variant_question_id':q.id,'question_asset_id':q.source_asset_id,'question_number':str(idx+1),
                           'stem_bbox':stem_box,'answer_bracket_bbox':bracket,'options_bbox':obox,
                           'question_bbox':box(36,top,524,y),'choice_kind':'multi' if len(str(q.correct_answer).strip())>1 else 'single'})
        y-=22
    pages.append(placements)
    c.save()
    return buffer.getvalue(),pages


def generate(db,assignment,variant,user_id,*,page_uids=None):
    rows=questions(db,variant.id)
    if not rows:
        raise ValueError('Variant has no questions')
    fp=fingerprint(rows)
    existing=db.query(PageTemplate).filter_by(variant_id=variant.id,status='ACTIVE',source='generated',variant_fingerprint=fp).order_by(PageTemplate.page_index).all()
    if existing:
        return existing
    uids=page_uids or [uuid.uuid4().hex for _ in range(9)]
    pdf,placements=render_pdf(assignment.title,rows,uids)
    images=rasterize_pdf(pdf)
    pdf_path=store(pdf,'.pdf')
    previous=db.query(PageTemplate).filter_by(variant_id=variant.id).all()
    version=max([p.export_version for p in previous] or [0])+1
    for p in previous:
        p.status='RETIRED'
    result=[]
    for idx,(image,mapping) in enumerate(zip(images,placements)):
        data=png(image)
        page=PageTemplate(assignment_id=assignment.id,variant_id=variant.id,page_index=idx,page_uid=uids[idx],export_version=version,
                          width=image.shape[1],height=image.shape[0],image_locator=store(data),image_sha256=hashlib.sha256(data).hexdigest(),
                          pdf_locator=pdf_path,variant_fingerprint=fp,source='generated',status='ACTIVE',created_by=user_id)
        db.add(page);db.flush()
        for item in mapping:
            db.add(QuestionPlacement(page_template_id=page.id,**item))
        result.append(page)
    db.commit()
    return result


def valid_box(value,width,height):
    if not isinstance(value,list) or len(value)!=4 or not all(isinstance(v,(int,float)) and np.isfinite(v) for v in value):
        raise ValueError('Bounding boxes require four finite coordinates')
    x1,y1,x2,y2=map(int,value)
    if not (0<=x1<x2<=width and 0<=y1<y2<=height):
        raise ValueError('Bounding box outside template')
    return [x1,y1,x2,y2]


def inside(inner,outer):
    return outer[0]<=inner[0]<inner[2]<=outer[2] and outer[1]<=inner[1]<inner[3]<=outer[3]

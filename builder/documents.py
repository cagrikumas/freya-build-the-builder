"""Read a case folder without losing tables, sheet labels, or diagram images."""
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
S = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
R = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'


def office_images(archive, prefix, output):
    images = []
    for name in archive.namelist():
        if name.startswith(prefix) and Path(name).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
            dest = output / (hashlib.sha256(name.encode()).hexdigest()[:12] + Path(name).suffix)
            dest.write_bytes(archive.read(name)); images.append(dest)
    return images


def word(path, output):
    with zipfile.ZipFile(path) as z:
        parts = []
        names = [n for n in z.namelist() if re.fullmatch(r'word/(document|footnotes|endnotes|header\d+|footer\d+)\.xml', n)]
        for name in sorted(names, key=lambda n: (n != 'word/document.xml', n)):
            root = ET.fromstring(z.read(name))
            parts.append('PART ' + name)
            def paragraph(p):
                pieces = []
                for node in p.iter():
                    if node.tag == W + 't': pieces.append(node.text or '')
                    elif node.tag == W + 'tab': pieces.append('\t')
                    elif node.tag == W + 'br': pieces.append('\n')
                return ''.join(pieces)
            def visit(node):
                if node.tag == W+'p':
                    value = paragraph(node)
                    if value: parts.append(value)
                elif node.tag == W+'tbl':
                    parts.append('TABLE')
                    for row in node.findall(W+'tr'):
                        parts.append(' | '.join(json.dumps('\n'.join(paragraph(p) for p in cell.iter(W+'p')), ensure_ascii=False) for cell in row.findall(W+'tc')))
                    parts.append('END TABLE')
                else:
                    for child in node: visit(child)
            visit(root)
        return '\n'.join(parts), office_images(z, 'word/media/', output)


def spreadsheet(path, output):
    with zipfile.ZipFile(path) as z:
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            strings = [''.join(t.text or '' for t in si.iter(S+'t')) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        workbook = ET.fromstring(z.read('xl/workbook.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        epoch1904 = workbook.find(S+'workbookPr')
        epoch1904 = epoch1904 is not None and epoch1904.get('date1904') in ('1', 'true')
        formats, styles = {}, []
        if 'xl/styles.xml' in z.namelist():
            style = ET.fromstring(z.read('xl/styles.xml'))
            formats = {int(n.get('numFmtId')): n.get('formatCode', '') for n in style.iter(S+'numFmt')}
            xfs = style.find(S+'cellXfs')
            styles = [int(n.get('numFmtId', '0')) for n in xfs] if xfs is not None else []
        lines = []
        for sheet in workbook.find(S+'sheets'):
            target = rels[sheet.get(R+'id')]
            name = target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl') / target)
            lines.append('\nSHEET: ' + sheet.get('name', '') + ' (state=' + sheet.get('state', 'visible') + ')')
            root = ET.fromstring(z.read(name))
            for row in root.iter(S+'row'):
                cells = []
                for c in row.findall(S+'c'):
                    v = c.find(S+'v'); value = v.text if v is not None else ''
                    typ = c.get('t', '')
                    if typ == 's' and value: value = strings[int(value)]
                    elif typ == 'inlineStr': value = ''.join(t.text or '' for t in c.iter(S+'t'))
                    elif typ == 'b': value = 'true' if value == '1' else 'false'
                    style_index = int(c.get('s', '0'))
                    fmt = styles[style_index] if style_index < len(styles) else 0
                    code = formats.get(fmt, '')
                    numeric = bool(value and re.fullmatch(r'-?\d+(?:\.\d+)?', value))
                    date_fmt = fmt in (*range(14, 23), 45, 46, 47) or bool(re.search(r'[dy]|h.*s', re.sub(r'"[^"]*"|\[[^\]]*\]', '', code), re.I))
                    if numeric and typ not in ('s', 'b', 'inlineStr') and date_fmt:
                        serial = float(value)
                        epoch = dt.datetime(1904, 1, 1) if epoch1904 else dt.datetime(1899, 12, 30)
                        if not epoch1904 and 0 < serial < 60: serial += 1
                        value = (epoch + dt.timedelta(days=serial)).isoformat() + ' [raw=' + value + ']'
                    elif numeric and re.fullmatch('0+', code): value = value.zfill(len(code))
                    formula = c.find(S+'f')
                    if formula is not None: value += ' [formula=' + (formula.text or '') + ']'
                    cells.append(c.get('r', '?') + '=' + json.dumps(value, ensure_ascii=False))
                if cells: lines.append(' | '.join(cells))
            for merged in root.iter(S+'mergeCell'): lines.append('MERGED ' + merged.get('ref', ''))
        return '\n'.join(lines), office_images(z, 'xl/media/', output)


def read_folder(folder, run_dir):
    folder = folder.resolve()
    assets = run_dir / 'input-images'; assets.mkdir(exist_ok=True)
    files = sorted((p for p in folder.rglob('*') if p.is_file() and not any(part.startswith('.') for part in p.relative_to(folder).parts)),
                   key=lambda p: (p.name.upper() not in ('BRIEF.MD', 'README.MD'), str(p)))
    documents, images, manifest = [], [], []
    for p in files:
        if p.is_symlink(): raise ValueError('Case inputs must be regular files: ' + str(p))
        relative = str(p.relative_to(folder)); suffix = p.suffix.lower()
        bucket = assets / hashlib.sha256(relative.encode()).hexdigest()[:12]; bucket.mkdir(exist_ok=True)
        pictures = []
        if suffix in ('.md', '.txt', '.csv', '.json', '.yaml', '.yml', '.xml', '.html'):
            try: content = p.read_text(encoding='utf-8-sig')
            except UnicodeDecodeError: content = p.read_text(encoding='cp1254')
        elif suffix == '.docx': content, pictures = word(p, bucket)
        elif suffix == '.xlsx': content, pictures = spreadsheet(p, bucket)
        elif suffix == '.pdf':
            content = subprocess.check_output(['pdftotext', '-layout', str(p), '-'], text=True, timeout=120)
            subprocess.run(['pdftoppm', '-scale-to', '1800', '-png', str(p), str(bucket/'page')], check=True, capture_output=True, timeout=180)
            pictures = sorted(bucket.glob('page-*.png'), key=lambda f: int(f.stem.rsplit('-', 1)[-1]))
        elif suffix in ('.png', '.jpg', '.jpeg', '.webp'):
            target = bucket / p.name; target.write_bytes(p.read_bytes()); pictures = [target]; content = '[Image document; see attached image.]'
        else: raise ValueError('Unsupported case document type; add a general reader before building: ' + relative)
        documents.append('### INPUT FILE ' + relative + '\n' + content)
        for picture in pictures:
            images.append(picture)
            documents.append('ATTACHED IMAGE ' + str(len(images)) + ': ' + relative + ' / ' + picture.name)
        manifest.append({'path': relative, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'text_chars': len(content), 'images': len(pictures)})
    if not files: raise ValueError('The case folder is empty')
    return '\n\n'.join(documents), images, manifest

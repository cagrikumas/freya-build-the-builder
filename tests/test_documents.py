import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from documents import read_folder, spreadsheet, word


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.assets = self.root/'assets'; self.assets.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def test_word_tables_keep_cells_and_non_ascii_text(self):
        p = self.root/'terms.docx'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>İşlem koşulları</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Alan</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Açıklama</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>kod</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>0007</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        text, _ = word(p, self.assets)
        self.assertIn('İşlem koşulları', text)
        self.assertIn('"Alan" | "Açıklama"', text)
        self.assertIn('"kod" | "0007"', text)

    def test_excel_preserves_sheet_cell_dates_zeroes_and_formulas(self):
        p = self.root/'values.xlsx'
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Kayıtlar" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/styles.xml', f'<styleSheet xmlns="{ns}"><numFmts><numFmt numFmtId="164" formatCode="0000"/></numFmts><cellXfs><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="14"/></cellXfs></styleSheet>')
            z.writestr('xl/sharedStrings.xml', f'<sst xmlns="{ns}"><si><t>Çağrı</t></si></sst>')
            z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" s="1"><v>7</v></c><c r="C1" s="2"><v>61</v></c><c r="D1"><f>1+2</f><v>3</v></c><c r="E1"><f>D1*2</f><v/></c></row></sheetData></worksheet>')
        text, _ = spreadsheet(p, self.assets)
        for expected in ['Kayıtlar', 'A1="Çağrı"', 'B1="0007 [raw=7;', '1900-03-01', 'formula=1+2', 'formula=D1*2']:
            self.assertIn(expected, text)

    def test_excel_percentage_units_and_numeric_formats_are_preserved(self):
        p = self.root/'percentages.xlsx'
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Rates" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels', '<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/styles.xml', f'<styleSheet xmlns="{ns}"><numFmts><numFmt numFmtId="164" formatCode="0.00%"/><numFmt numFmtId="165" formatCode="0.00 &quot;TL&quot;"/></numFmts><cellXfs><xf numFmtId="9"/><xf numFmtId="10"/><xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>')
            z.writestr('xl/worksheets/sheet1.xml', f'<worksheet xmlns="{ns}"><sheetData><row><c r="A1"><v>0.25</v></c><c r="B1" s="1"><v>0.125</v></c><c r="C1" s="2"><v>0.30</v></c><c r="D1" s="3"><v>15.5</v></c><c r="E1"><v>2.5E-1</v></c></row></sheetData></worksheet>')
        text, _ = spreadsheet(p, self.assets)
        for expected in ['A1="25.00% [raw=0.25;', 'B1="12.500% [raw=0.125;',
                         'C1="30.00% [raw=0.30;', '15.5 [raw=15.5;', 'TL', 'E1="25.00% [raw=2.5E-1;']:
            self.assertIn(expected, text)

    def test_word_smartart_preserves_labels_and_directed_connections(self):
        p = self.root/'flow.docx'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Follow this flow.</w:t></w:r></w:p></w:body></w:document>')
            z.writestr('word/diagrams/data1.xml', '<dgm:dataModel xmlns:dgm="http://schemas.openxmlformats.org/drawingml/2006/diagram" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><dgm:ptLst><dgm:pt modelId="verify"><dgm:t><a:p><a:r><a:t>Önce kimlik doğrula</a:t></a:r></a:p></dgm:t></dgm:pt><dgm:pt modelId="lookup"><dgm:t><a:p><a:r><a:t>Sonra hesap getir</a:t></a:r></a:p></dgm:t></dgm:pt></dgm:ptLst><dgm:cxnLst><dgm:cxn type="parOf" srcId="verify" destId="lookup"/></dgm:cxnLst></dgm:dataModel>')
        text, images = word(p, self.assets)
        self.assertIn('SMARTART PART word/diagrams/data1.xml', text)
        self.assertIn('Önce kimlik doğrula', text)
        self.assertIn('Sonra hesap getir', text)
        self.assertIn('"srcId": "verify", "destId": "lookup"', text)
        self.assertEqual(images, [])

    def test_word_unsupported_native_graphic_fails_explicitly(self):
        p = self.root/'chart.docx'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><w:body><w:p><w:r><w:drawing><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"/></a:graphic></w:drawing></w:r></w:p></w:body></w:document>')
        with self.assertRaisesRegex(ValueError, 'Unsupported native Word graphic'):
            word(p, self.assets)

    def test_folder_manifests_all_documents_and_rejects_unknown_types(self):
        folder = self.root/'case'; folder.mkdir()
        (folder/'BRIEF.md').write_text('Read the amendments.')
        (folder/'amendment.txt').write_text('Replaces the earlier rule.')
        run = self.root/'run';run.mkdir()
        text, images, manifest = read_folder(folder, run)
        self.assertIn('Replaces the earlier rule.', text)
        self.assertEqual(len(manifest), 2)
        self.assertTrue(all(len(r['sha256']) == 64 for r in manifest))
        (folder/'unknown.doc').write_bytes(b'not silently ignored')
        with self.assertRaisesRegex(ValueError, 'Unsupported case document'):
            read_folder(folder, run)

    @unittest.skipUnless(shutil.which('pdftotext') and shutil.which('pdftoppm'), 'Poppler required')
    def test_scanned_pdf_is_attached_as_image(self):
        try: from PIL import Image
        except ImportError: self.skipTest('Pillow required for generating PDF fixture')
        folder = self.root/'case';folder.mkdir()
        Image.new('RGB', (100, 100), 'white').save(folder/'diagram.pdf')
        run=self.root/'run';run.mkdir()
        text, images, manifest=read_folder(folder, run)
        self.assertEqual(len(images), 1)
        self.assertTrue(images[0].is_file())
        self.assertIn('ATTACHED IMAGE 1: diagram.pdf', text)

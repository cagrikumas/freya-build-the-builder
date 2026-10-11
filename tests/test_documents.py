import json
import hashlib
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'builder'))
from documents import read_folder, spreadsheet, word, compact_json_text


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.assets = self.root/'assets'; self.assets.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def test_json_compaction_preserves_nested_values_and_string_whitespace(self):
        original = '{\n "items": [ true, false, null, { "text": " keep  spaces " } ],\r\n "n": 17\n}'
        compact = compact_json_text(original)
        self.assertEqual(compact, '{"items":[true,false,null,{"text":" keep  spaces "}],"n":17}')
        self.assertEqual(json.loads(compact), json.loads(original))

    def test_json_compaction_preserves_numeric_tokens_without_float_roundtrip(self):
        tokens = ['123456789012345678901234567890.123456789012345678901234567890',
                  '-0', '1.2300e+004', '1e999999', '9' * 5001]
        original = '[\n' + ',\n '.join(tokens) + '\n]'
        compact = compact_json_text(original)
        self.assertEqual(compact, '[' + ','.join(tokens) + ']')
        self.assertEqual(json.loads(compact, parse_float=Decimal, parse_int=Decimal),
                         json.loads(original, parse_float=Decimal, parse_int=Decimal))

    def test_json_compaction_keeps_escape_spellings_and_duplicate_key_values(self):
        original = r'''{ "text": "line\n tab\t slash\\ quote\" letter\u0131", "same": 1, "same": 2 }'''
        expected = r'''{"text":"line\n tab\t slash\\ quote\" letter\u0131","same":1,"same":2}'''
        self.assertEqual(compact_json_text(original), expected)
        self.assertEqual(json.loads(original), json.loads(expected))

    def test_json_compaction_does_not_turn_invalid_input_into_valid_json(self):
        for original in ('1 2', '{ "bad": NaN }', '[Infinity]', '[-Infinity]', '{"x": 01}', '{"x": "broken\\"}'):
            with self.subTest(original=original), self.assertRaises(ValueError):
                compact_json_text(original)

    def test_json_folder_compaction_preserves_original_bytes_and_hash(self):
        folder = self.root/'case'; folder.mkdir()
        path = folder/'data.json'
        original = b'\xef\xbb\xbf{\n  "account": "00001234",\n  "exact": 0.123456789012345678901\n}\n'
        path.write_bytes(original)
        run = self.root/'run'; run.mkdir()
        text, _, manifest = read_folder(folder, run)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(manifest[0]['sha256'], hashlib.sha256(original).hexdigest())
        self.assertIn('{"account":"00001234","exact":0.123456789012345678901}', text)
        self.assertEqual(manifest[0]['text_transform'], 'json_whitespace_minified')
        self.assertGreater(manifest[0]['source_text_chars'], manifest[0]['text_chars'])

    def test_word_tables_keep_cells_and_non_ascii_text(self):
        p = self.root/'terms.docx'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>İşlem koşulları</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Alan</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Açıklama</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>kod</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>0007</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
        text, _ = word(p, self.assets)
        self.assertIn('İşlem koşulları', text)
        self.assertIn('"Alan" | "Açıklama"', text)
        self.assertIn('"kod" | "0007"', text)

    def test_source_and_config_documents_are_read_as_text_without_execution(self):
        folder = self.root/'case'; folder.mkdir()
        source = 'throw new Error("must never execute");\nexport default { fetch() {} };\n'
        config = '# Configuration is source evidence\nname = "example"\n[vars]\nCODE = "0007"\n'
        (folder/'worker.js').write_text(source, encoding='utf-8')
        (folder/'wrangler.toml').write_text(config, encoding='utf-8')
        run = self.root/'run'; run.mkdir()
        text, images, manifest = read_folder(folder, run)
        self.assertIn(source, text)
        self.assertIn(config, text)
        self.assertEqual(images, [])
        self.assertEqual({item['path'] for item in manifest}, {'worker.js', 'wrangler.toml'})
        for item in manifest:
            original = (folder/item['path']).read_bytes()
            self.assertEqual(item['sha256'], hashlib.sha256(original).hexdigest())
            self.assertNotIn('text_transform', item)

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

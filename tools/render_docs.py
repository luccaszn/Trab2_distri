"""Gera HTML/PDF do relatório e SVGs Mermaid. Ferramenta de documentação, não deploy."""
import html
from pathlib import Path
import re
import urllib.request

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


def main():
    vendor = ROOT / 'build' / 'vendor' / 'mermaid.min.js'
    if not vendor.exists():
        vendor.parent.mkdir(parents=True, exist_ok=True)
        vendor.write_bytes(urllib.request.urlopen('https://cdn.jsdelivr.net/npm/mermaid@10.9.3/dist/mermaid.min.js', timeout=40).read())
    diagram_sources = re.findall(r'```mermaid\n(.*?)```', (DOCS / 'diagramas.md').read_text(encoding='utf-8'), re.S)
    titles = ['Diagrama em blocos', 'Sequência A/B — solicitação', 'Sequência — chegada', 'Sequência C — venda']
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel='chrome', headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1100, 'height': 1600})
        page.set_content('<html><body></body></html>')
        page.add_script_tag(path=str(vendor))
        page.evaluate("mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'neutral',fontFamily:'Arial',sequence:{useMaxWidth:false,wrap:true},flowchart:{useMaxWidth:false,htmlLabels:false}})")
        diagram_html = []
        for index, source in enumerate(diagram_sources):
            svg = page.evaluate('async ({source,id}) => (await mermaid.render(id,source)).svg', {'source': source, 'id': f'diagram{index}'})
            (DOCS / f'diagrama-{index + 1}.svg').write_text(svg, encoding='utf-8')
            diagram_html.append(f'<section class="diagram-page"><h1>{html.escape(titles[index])}</h1>{svg}</section>')
        sections = []
        for name in ('relatorio', 'instalacao', 'operacao'):
            text = (DOCS / f'{name}.md').read_text(encoding='utf-8')
            sections.append(f'<section class="document {name}">' + markdown.markdown(text, extensions=['tables', 'fenced_code']) + '</section>')
        style = '''@page{size:A4;margin:18mm 16mm 18mm}body{font:10pt/1.5 Arial,sans-serif;color:#18372d}h1{font:25pt Georgia,serif;line-height:1.15}h2{font-size:13pt;margin:6mm 0 3mm;break-after:avoid}h3{font-size:11pt;break-after:avoid}p{orphans:3;widows:3}blockquote{margin:5mm 0;padding:3mm 4mm;border-left:3px solid #9e5c30;background:#f7f1df}table{width:100%;border-collapse:collapse;font-size:9pt;break-inside:avoid}th,td{border-bottom:1px solid #d5dcd5;padding:2mm;text-align:left;vertical-align:top}th{background:#e9eee9}code{font:8.5pt Consolas,monospace;overflow-wrap:anywhere}pre{background:#f2f4f2;padding:3mm;white-space:pre-wrap}a{color:inherit}li{margin-bottom:1.2mm}.document+.document,.diagram-page{break-before:page}.diagram-page{height:255mm;overflow:hidden}.diagram-page svg{display:block;width:100%!important;height:auto;max-height:235mm}.diagram-page h1{font-size:19pt}.small{color:#687268;font-size:8pt}'''
        style += '.instalacao{font-size:9.5pt;line-height:1.4}.instalacao h2{margin-top:4mm}'
        document = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Sebo na Nuvem — relatório e documentação</title><style>' + style + '</style><body>' + sections[0] + ''.join(diagram_html) + ''.join(sections[1:]) + '</body></html>'
        target = DOCS / 'relatorio-completo.html'
        target.write_text(document, encoding='utf-8')
        page.goto(target.as_uri(), wait_until='load')
        page.pdf(path=str(DOCS / 'relatorio-completo.pdf'), format='A4', print_background=True,
                 display_header_footer=True, header_template='<span></span>',
                 footer_template='<div style="font:8px Arial;width:100%;text-align:center;color:#777">Sebo na Nuvem · Enzo Abate / Lucca Sznaider · <span class="pageNumber"></span> / <span class="totalPages"></span></div>')
        page.screenshot(path=str(DOCS / 'evidencias' / 'relatorio-preview.png'))
        print(f'Relatório HTML/PDF e {len(diagram_sources)} diagramas SVG gerados.')
        browser.close()


if __name__ == '__main__':
    main()

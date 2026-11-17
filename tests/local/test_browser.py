"""Fluxos visuais reais com Chromium contra Lambdas reais em AWS emulada."""
import json
from pathlib import Path
import urllib.request

import pytest
from playwright.sync_api import sync_playwright, expect

from test_http_flow import local_server

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs' / 'evidencias'


@pytest.fixture
def browser():
    with sync_playwright() as p:
        try:
            instance = p.chromium.launch(channel='chrome', headless=True)
        except Exception:
            instance = p.chromium.launch(headless=True)
        try:
            yield instance
        finally:
            instance.close()


def test_browser_full_customer_staff_flow(local_server, browser):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(local_server)
    expect(page.locator('.book-card')).to_have_count(4)
    expect(page.locator('#local-banner')).to_be_visible()
    page.screenshot(path=str(EVIDENCE / 'cliente-desktop.png'), full_page=True)
    page.get_by_role('button', name='Selecionar Dom Casmurro', exact=True).click()
    page.locator('#form-pedido [name=nomeCliente]').fill('Leitor de teste')
    page.locator('#form-pedido [name=emailCliente]').fill('browser@example.com')
    page.locator('#enviar-pedido').click()
    expect(page.locator('#pedido-resultado')).to_contain_text('Um exemplar foi reservado')
    expect(page.locator('#enviar-pedido')).to_be_enabled()
    # Duplicado não pode reservar outro exemplar.
    page.locator('#enviar-pedido').click()
    expect(page.locator('#pedido-resultado')).to_contain_text('Já existe interesse ativo')
    page.locator('#tab-colaborador').click()
    expect(page.locator('#interesses tbody tr')).to_have_count(1)
    page.on('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Efetivar venda', exact=True).click()
    expect(page.locator('#venda-resultado')).to_contain_text('Venda efetivada')
    expect(page.locator('#vendas tbody tr')).to_have_count(1)
    page.locator('#tab-cliente').click()
    page.get_by_role('button', name='Selecionar O Alienista', exact=True).click()
    page.locator('#enviar-pedido').click()
    expect(page.locator('#pedido-resultado')).to_contain_text('Interesse registrado')
    page.locator('#tab-colaborador').click()
    expect(page.locator('#interesses tbody tr')).to_have_count(2)
    page.locator('#livro-existente').select_option('SEED-003')
    page.locator('#form-cadastro [name=quantidade]').fill('2')
    page.locator('#form-cadastro button[type=submit]').click()
    expect(page.locator('#cadastro-resultado')).to_contain_text('Clientes reservados: 1')
    expect(page.locator('#cadastro-resultado')).to_contain_text('Publicações de aviso aceitas: 1')
    page.screenshot(path=str(EVIDENCE / 'colaborador-desktop.png'), full_page=True)
    assert page.locator('#interesses').inner_text().count('RESERVADO') == 1
    assert errors == []
    page.close()


def test_browser_responsive_xss_errors_and_missing_config(local_server, browser):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(local_server)
    expect(page.locator('.book-card')).to_have_count(4)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(EVIDENCE / 'cliente-mobile.png'), full_page=True)
    page.locator('#tab-colaborador').click()
    expect(page.locator('#estoque tbody tr')).to_have_count(4)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    title = '<img src=x onerror="window.__xss=1">'
    page.locator('#form-cadastro [name=titulo]').fill(title)
    page.locator('#form-cadastro [name=autor]').fill('<script>alert(1)</script>')
    page.locator('#form-cadastro [name=preco]').fill('12.50')
    page.locator('#form-cadastro button[type=submit]').click()
    expect(page.locator('#cadastro-resultado')).to_contain_text('Livro cadastrado')
    page.locator('#tab-cliente').click()
    expect(page.locator('#catalogo')).to_contain_text(title)
    assert page.locator('#catalogo img, #catalogo script').count() == 0
    assert page.evaluate('window.__xss === undefined')
    page.locator('#busca').fill('titulo-inexistente-xyz')
    expect(page.locator('#catalogo')).to_contain_text('Nenhum título encontrado')
    page.locator('#busca').fill('')
    page.route('**/api/listar*', lambda route: route.abort())
    page.locator('#atualizar-catalogo').click()
    expect(page.locator('#catalogo-estado')).to_contain_text('rede')
    page.unroute('**/api/listar*')
    assert errors == []
    # config.js inexistente: erro visível, não catálogo inventado.
    page.route('**/config.js', lambda route: route.fulfill(status=200, body='window.SEBO_CONFIG = {};', content_type='application/javascript'))
    page.reload()
    expect(page.locator('#config-alert')).to_contain_text('Ambiente não configurado')
    expect(page.locator('.book-card')).to_have_count(0)
    assert errors == []
    page.close()

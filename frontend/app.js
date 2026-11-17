/* Interface sem dependências. Dados do serviço entram somente por textContent. */
(function () {
  'use strict';
  const { moeda, dt, cadastroPayload, clientePayload, createApi } = window.SeboUtil;
  const api = createApi(window.SEBO_CONFIG || {});
  const $ = id => document.getElementById(id);
  const state = { livros: [], interesses: [], vendas: [], selected: null, pedidoBusy: false, staffLoaded: false, loaded: new Set(), requests: new Map(), selling: new Set() };
  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text ?? '');
    if (className) node.className = className;
    return node;
  }
  function notice(id, message, type = '') {
    const node = $(id);
    node.textContent = message;
    node.className = `notice ${type}`;
    node.hidden = !message;
  }
  function empty(target, message) { target.replaceChildren(el('p', message, 'empty-state')); }
  function formData(form) { return Object.fromEntries(new FormData(form)); }
  function lock(form, busy) {
    form.setAttribute('aria-busy', String(busy));
    for (const control of form.elements) control.disabled = busy;
  }
  function selectedBook() { return state.livros.find(book => book.livroId === state.selected); }
  function updateSelection() {
    const book = selectedBook();
    const target = $('livro-selecionado');
    target.replaceChildren();
    if (book) {
      target.append(el('strong', book.titulo), el('span', book.autor, 'muted'), el('span', `${moeda(book.preco)} · ${Number(book.quantidade) > 0 ? 'Disponível para reserva' : 'Avise-me quando chegar'}`, 'selected-detail'));
    } else target.textContent = 'Selecione um título no acervo ao lado.';
    $('enviar-pedido').disabled = !book || state.pedidoBusy;
    $('enviar-pedido').firstChild.textContent = book && Number(book.quantidade) <= 0 ? 'Registrar interesse ' : 'Registrar pedido ';
  }
  function renderCatalogue() {
    const query = $('busca').value.trim().toLocaleLowerCase('pt-BR');
    const books = state.livros.filter(book => `${book.titulo} ${book.autor} ${book.livroId}`.toLocaleLowerCase('pt-BR').includes(query));
    $('catalogo-contagem').textContent = `${books.length} ${books.length === 1 ? 'título' : 'títulos'}${query ? ` de ${state.livros.length}` : ' no acervo'}`;
    const target = $('catalogo'); target.replaceChildren();
    if (!books.length) {
      if (state.loaded.has('livros')) empty(target, query ? 'Nenhum título encontrado. Experimente outra busca.' : 'O acervo ainda não tem títulos cadastrados.');
      return;
    }
    for (const book of books) {
      const available = Number(book.quantidade) > 0;
      const card = el('article', undefined, `book-card${state.selected === book.livroId ? ' selected' : ''}`);
      const top = el('div', undefined, 'book-top');
      top.append(el('span', book.livroId, 'book-code'), el('span', available ? 'Disponível' : 'Sob interesse', `badge ${available ? 'available' : 'pending'}`));
      const detail = [book.ano, book.condicao].filter(Boolean).join(' · ');
      card.append(top, el('h2', book.titulo), el('p', book.autor, 'book-author'));
      if (detail) card.append(el('p', detail, 'book-detail'));
      const bottom = el('div', undefined, 'book-bottom');
      const price = el('div'); price.append(el('strong', moeda(book.preco)), el('small', available ? `${book.quantidade} em estoque` : 'Aguardando chegada'));
      const select = el('button', state.selected === book.livroId ? 'Selecionado ✓' : 'Escolher ↗', 'button small');
      select.type = 'button'; select.setAttribute('aria-pressed', String(state.selected === book.livroId)); select.setAttribute('aria-label', `Selecionar ${book.titulo}`);
      select.addEventListener('click', () => {
        if (state.pedidoBusy) return;
        state.selected = book.livroId; notice('pedido-resultado', ''); renderCatalogue(); updateSelection();
      });
      select.disabled = state.pedidoBusy;
      bottom.append(price, select); card.append(bottom); target.append(card);
    }
  }
  function table(targetId, headings, items, rowBuilder, emptyMessage) {
    const target = $(targetId); target.replaceChildren();
    if (!items.length) { empty(target, emptyMessage); return; }
    const node = el('table');
    const head = el('thead'); const headerRow = el('tr');
    for (const heading of headings) { const cell = el('th', heading); cell.scope = 'col'; headerRow.append(cell); }
    head.append(headerRow); const body = el('tbody');
    for (const item of items) { const row = el('tr'); for (const content of rowBuilder(item)) { const cell = el('td'); if (content instanceof Node) cell.append(content); else cell.textContent = String(content ?? '—'); row.append(cell); } body.append(row); }
    node.append(head, body); target.append(node);
  }
  function titleCell(title, subtitle) { const cell = el('div', undefined, 'cell-title'); cell.append(el('strong', title || 'Título indisponível'), el('small', subtitle || '')); return cell; }
  function bookTitle(item) { return item.titulo || state.livros.find(book => book.livroId === item.livroId)?.titulo || item.livroId; }
  function renderStock() {
    $('estoque-contagem').textContent = `${state.livros.length} títulos`;
    table('estoque', ['Título / código', 'Disponíveis', 'Preço', 'Entrada'], state.livros, book => {
      const button = el('button', '+ Chegada', 'button small subtle'); button.type = 'button';
      button.setAttribute('aria-label', `Registrar chegada de ${book.titulo}`);
      button.addEventListener('click', () => {
        if ($('form-cadastro').getAttribute('aria-busy') === 'true') return;
        $('livro-existente').value = book.livroId; fillEntry(); $('form-cadastro').elements.quantidade.focus();
      });
      return [titleCell(book.titulo, book.livroId), book.quantidade, moeda(book.preco), button];
    }, 'Nenhum livro cadastrado. Registre o primeiro título.');
    const selector = $('livro-existente'); const previous = selector.value;
    selector.replaceChildren(new Option('Novo título', ''));
    for (const book of state.livros) selector.add(new Option(`${book.titulo} · ${book.livroId}`, book.livroId));
    if (state.livros.some(book => book.livroId === previous)) selector.value = previous;
  }
  function renderInterests() {
    const filter = $('filtro-interesses').value;
    const items = state.interesses.filter(item => !filter || item.status === filter);
    table('interesses', ['Livro / leitor', 'Criado em', 'Status', 'Ação'], items, item => {
      const identity = titleCell(bookTitle(item), `${item.nomeCliente ? `${item.nomeCliente} · ` : ''}${item.emailCliente || 'E-mail indisponível'}`);
      identity.append(el('small', item.interesseId, 'identifier'));
      const badge = el('span', item.status, `badge ${item.status === 'RESERVADO' ? 'available' : item.status === 'VENDIDO' ? 'sold' : 'pending'}`);
      let action = '—';
      if (item.status === 'RESERVADO') {
        action = el('button', state.selling.has(item.interesseId) ? 'Efetivando…' : 'Efetivar venda', 'button small'); action.type = 'button'; action.disabled = state.selling.has(item.interesseId);
        action.addEventListener('click', () => sell(item));
      }
      return [identity, dt(item.dataCriacao), badge, action];
    }, filter ? 'Nenhum interesse com este status.' : 'Nenhum interesse registrado.');
  }
  function renderSales() {
    const total = state.vendas.reduce((sum, sale) => sum + (Number.isFinite(Number(sale.valor)) ? Number(sale.valor) : 0), 0);
    $('vendas-total').textContent = `${state.vendas.length} ${state.vendas.length === 1 ? 'venda' : 'vendas'} · ${moeda(total)}`;
    table('vendas', ['Livro / cliente', 'Data da venda', 'Valor'], state.vendas, sale => [titleCell(bookTitle(sale), `${sale.emailCliente || ''} · ${sale.vendaId}`), dt(sale.dataVenda), moeda(sale.valor)], 'Nenhuma venda efetivada.');
  }
  async function load(resource) {
    // Uma consulta pós-mudança nunca pode ser descartada por outra em andamento.
    while (state.requests.has(resource)) await state.requests.get(resource);
    const request = loadResource(resource);
    state.requests.set(resource, request);
    try { return await request; }
    finally { if (state.requests.get(resource) === request) state.requests.delete(resource); }
  }
  async function loadResource(resource) {
    const ids = resource === 'livros' ? ['catalogo-estado', 'estoque-estado'] : [`${resource}-estado`];
    ids.forEach(id => notice(id, 'Carregando…'));
    try {
      const data = await api.list(resource);
      if (!Array.isArray(data.itens) || data.itens.some(item => !item || typeof item !== 'object')) throw new Error('Resposta inválida: a listagem não contém os itens esperados.');
      state[resource] = data.itens;
      state.loaded.add(resource);
      if (resource === 'livros') {
        state.livros.sort((a, b) => String(a.titulo).localeCompare(String(b.titulo), 'pt-BR', { sensitivity: 'base' }));
        if (!selectedBook()) state.selected = null;
        renderCatalogue(); renderStock(); updateSelection();
        if (state.loaded.has('interesses')) renderInterests();
      } else if (resource === 'interesses') renderInterests(); else renderSales();
      ids.forEach(id => notice(id, ''));
    } catch (error) {
      ids.forEach(id => notice(id, `${error.message}${state.loaded.has(resource) ? ' Exibindo a última consulta; os dados podem estar desatualizados.' : ''}`, 'error'));
    }
  }
  async function refreshStaff() {
    const button = $('atualizar-gestao'); button.disabled = true; button.textContent = 'Atualizando…';
    try { await Promise.all(['livros', 'interesses', 'vendas'].map(load)); }
    finally { button.disabled = false; button.textContent = 'Atualizar dados'; }
  }
  function fillEntry() {
    const form = $('form-cadastro'); const book = state.livros.find(item => item.livroId === $('livro-existente').value);
    for (const field of ['titulo', 'autor', 'preco', 'ano', 'condicao']) form.elements[field].value = book ? (book[field] ?? '') : '';
    form.elements.quantidade.value = '1'; notice('cadastro-resultado', '');
  }
  async function sell(item) {
    if (state.selling.has(item.interesseId)) return;
    if (!window.confirm(`Efetivar a venda de “${bookTitle(item)}” para ${item.emailCliente}? Confirme apenas após concluir o atendimento. Esta ação não pode ser desfeita nesta tela.`)) return;
    state.selling.add(item.interesseId); renderInterests();
    try {
      const data = await api.post('efetivar', { interesseId: item.interesseId });
      // Bloqueia novo envio imediatamente, mesmo se a atualização seguinte falhar.
      item.status = 'VENDIDO';
      await Promise.all([load('interesses'), load('vendas')]);
      notice('venda-resultado', `${data.mensagem || 'Venda efetivada.'} ${data.venda?.vendaId || ''}`, 'success');
    } catch (error) { notice('venda-resultado', error.message, 'error'); }
    finally { state.selling.delete(item.interesseId); renderInterests(); }
  }
  $('form-pedido').addEventListener('submit', async event => {
    event.preventDefault(); if (state.pedidoBusy) return;
    const form = event.currentTarget;
    let payload;
    try { payload = clientePayload({ ...formData(form), livroId: state.selected }); }
    catch (error) { notice('pedido-resultado', error.message, 'error'); return; }
    state.pedidoBusy = true; lock(form, true); renderCatalogue();
    notice('pedido-resultado', 'Registrando seu pedido…');
    try {
      const data = await api.post('solicitar', payload);
      const message = data.status === 'RESERVADO' ? 'Um exemplar foi reservado para você.' : 'Interesse registrado. Vamos avisar quando houver uma chegada.';
      notice('pedido-resultado', `${message} Protocolo: ${data.interesseId || 'não informado'}. ${data.emailEnviado ? 'Publicação do aviso aceita pelo serviço; isso não comprova entrega.' : 'Nenhuma publicação de aviso foi confirmada. Seu pedido permanece registrado.'}`, 'success');
      await load('livros');
      if (state.staffLoaded) await load('interesses');
    } catch (error) { notice('pedido-resultado', error.message, 'error'); }
    finally { state.pedidoBusy = false; lock(form, false); updateSelection(); renderCatalogue(); }
  });
  $('form-cadastro').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget;
    if (form.getAttribute('aria-busy') === 'true') return;
    let payload;
    try { payload = cadastroPayload({ ...formData(form), livroId: $('livro-existente').value }); }
    catch (error) { notice('cadastro-resultado', error.message, 'error'); return; }
    lock(form, true); notice('cadastro-resultado', 'Registrando entrada…');
    try {
      const data = await api.post('cadastrar', payload);
      form.reset();
      notice('cadastro-resultado', `${data.mensagem || 'Entrada registrada.'} ${data.livro?.livroId || ''} · Estoque disponível após reservas: ${data.livro?.quantidade ?? 'não informado'}. Clientes reservados: ${data.clientesReservados ?? 'não informado'}. Publicações de aviso aceitas: ${data.clientesNotificados ?? 0} (não comprova entrega).`, 'success');
      await Promise.all([load('livros'), load('interesses')]);
    } catch (error) { notice('cadastro-resultado', error.message, 'error'); }
    finally { lock(form, false); }
  });
  const tabs = ['cliente', 'colaborador'];
  function activateTab(name) {
    tabs.forEach(tab => {
      const active = tab === name;
      $(`tab-${tab}`).setAttribute('aria-selected', String(active)); $(`tab-${tab}`).tabIndex = active ? 0 : -1; $(tab).hidden = !active;
    });
    if (name === 'colaborador' && !state.staffLoaded) { state.staffLoaded = true; refreshStaff(); }
  }
  tabs.forEach((name, index) => {
    const tab = $(`tab-${name}`);
    tab.addEventListener('click', () => activateTab(name));
    tab.addEventListener('keydown', event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? 1 : 1 - index;
      activateTab(tabs[next]); $(`tab-${tabs[next]}`).focus();
    });
  });
  $('busca').addEventListener('input', renderCatalogue);
  $('filtro-interesses').addEventListener('change', renderInterests);
  $('livro-existente').addEventListener('change', fillEntry);
  $('atualizar-catalogo').addEventListener('click', async event => {
    const button = event.currentTarget; button.disabled = true; button.textContent = 'Atualizando…';
    try { await load('livros'); } finally { button.disabled = false; button.textContent = 'Atualizar'; }
  });
  $('atualizar-gestao').addEventListener('click', refreshStaff);
  $('local-banner').hidden = window.SEBO_CONFIG?.AMBIENTE !== 'local';
  const missing = ['URL_LISTAR', 'URL_SOLICITAR', 'URL_CADASTRAR', 'URL_EFETIVAR'].filter(key => !window.SEBO_CONFIG?.[key]);
  if (missing.length) notice('config-alert', `Ambiente não configurado. Copie frontend/config.example.js para frontend/config.js e preencha: ${missing.join(', ')}. Nenhum dado de demonstração é exibido.`, 'warning');
  load('livros');
})();

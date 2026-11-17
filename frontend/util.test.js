'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { esc, moeda, dt, cadastroPayload, clientePayload, createApi } = require('./util.js');
const fs = require('node:fs');
const vm = require('node:vm');

test('utilitários também são exportados no navegador e resolvem o origin real', async () => {
  const window = { location: { href: 'http://192.168.1.10:8080/index.html' } };
  vm.runInNewContext(fs.readFileSync(require.resolve('./util.js'), 'utf8'), { window, URL, AbortController, setTimeout, clearTimeout });
  assert.equal(typeof window.SeboUtil.esc, 'function');
  assert.equal(typeof window.SeboUtil.moeda, 'function');
  assert.equal(typeof window.SeboUtil.dt, 'function');
  let requested;
  await window.SeboUtil.createApi({ URL_LISTAR: '/api/listar' }, async url => { requested = url; return { ok: true, json: async () => ({ itens: [] }) }; }).list('livros');
  assert.equal(new URL(requested).origin, 'http://192.168.1.10:8080');
});

test('markup mantém referências DOM válidas e não usa handlers ou HTML dinâmico', () => {
  const html = fs.readFileSync(require.resolve('./index.html'), 'utf8');
  const app = fs.readFileSync(require.resolve('./app.js'), 'utf8');
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length, 'IDs devem ser únicos');
  for (const [, id] of app.matchAll(/\$\('([^']+)'\)/g)) assert.ok(ids.includes(id), `ID ausente: ${id}`);
  assert.doesNotMatch(html, /\son(?:click|submit|error|load)\s*=/i);
  assert.doesNotMatch(app, /\.innerHTML\s*=|insertAdjacentHTML|document\.write\(/);
  assert.match(html, /Ambiente local emulado · dados em memória · nenhum e-mail real enviado/);
});

test('esc neutraliza os cinco caracteres HTML sem perder texto', () => {
  assert.equal(esc(`<img src="x" onerror='alert(1)'>&`), '&lt;img src=&quot;x&quot; onerror=&#39;alert(1)&#39;&gt;&amp;');
  assert.equal(esc(null), '');
});
test('moeda formata BRL e não transforma ausência ou infinito em preço', () => {
  assert.match(moeda(12.5), /12,50/);
  assert.match(moeda(0), /0,00/);
  for (const value of [null, '', Infinity, NaN, undefined]) assert.equal(moeda(value), '—');
});
test('dt aceita ISO e rejeita data ausente ou inválida', () => {
  assert.match(dt('2026-03-20T12:30:00Z'), /20\/03\/2026/);
  for (const value of [null, '', 'sem data', undefined]) assert.equal(dt(value), '—');
});
test('cadastro valida quantidade inteira, preço finito e campos obrigatórios', () => {
  const base = { titulo: ' Livro ', autor: ' Autor ', quantidade: '2', preco: '12.50', ano: '', condicao: '' };
  assert.deepEqual(cadastroPayload(base), { titulo: 'Livro', autor: 'Autor', quantidade: 2, preco: 12.5 });
  for (const quantidade of ['1.5', '0', '-1', '', 'Infinity', true]) assert.throws(() => cadastroPayload({ ...base, quantidade }));
  for (const preco of ['', '-1', 'NaN', 'Infinity', true]) assert.throws(() => cadastroPayload({ ...base, preco }));
  assert.throws(() => cadastroPayload({ ...base, titulo: '  ' }));
  assert.throws(() => cadastroPayload({ ...base, ano: '2020.5' }));
  assert.equal(cadastroPayload({ ...base, livroId: ' LIV-ABCD1234 ', ano: '2000' }).livroId, 'LIV-ABCD1234');
});
test('solicitação exige livro e e-mail, normaliza e preserva nome opcional', () => {
  assert.deepEqual(clientePayload({ livroId: ' LIV-1 ', emailCliente: ' EU@EXAMPLE.COM ', nomeCliente: ' Ana ' }), { livroId: 'LIV-1', emailCliente: 'eu@example.com', nomeCliente: 'Ana' });
  assert.throws(() => clientePayload({ livroId: '', emailCliente: 'a@b.com' }));
  assert.throws(() => clientePayload({ livroId: 'x', emailCliente: 'invalido' }));
});
test('API recusa configuração ausente e URL insegura antes da rede', async () => {
  const fetcher = () => { throw new Error('não deve chamar'); };
  await assert.rejects(createApi({}, fetcher).list('livros'), /config\.js/);
  await assert.rejects(createApi({ URL_LISTAR: 'javascript:alert(1)' }, fetcher).list('livros'), /URL/);
  await assert.rejects(createApi({ URL_LISTAR: '/\\\\evil.example/path' }, fetcher).list('livros'), /URL inválida/);
});
test('API permite rotas locais no mesmo origin sem aceitar esquemas arbitrários', async () => {
  const calls = [];
  const api = createApi({ URL_LISTAR: '/api/listar', URL_CADASTRAR: '/api/cadastrar' }, async (url) => { calls.push(url); return { ok: true, json: async () => ({ itens: [] }) }; });
  await api.list('livros');
  assert.equal(new URL(calls[0]).pathname, '/api/listar');
  await api.post('cadastrar', {});
  assert.equal(new URL(calls[1]).pathname, '/api/cadastrar');
});
test('API monta query e POST JSON dos contratos', async () => {
  const calls = [];
  const api = createApi({ URL_LISTAR: 'https://example.com/?base=1', URL_SOLICITAR: 'https://example.com/pedido' }, async (...args) => { calls.push(args); return { ok: true, json: async () => ({ itens: [], total: 0 }) }; });
  await api.list('livros');
  assert.equal(new URL(calls[0][0]).searchParams.get('recurso'), 'livros');
  assert.equal(new URL(calls[0][0]).searchParams.get('base'), '1');
  await api.post('solicitar', { livroId: 'x' });
  assert.equal(calls[1][1].method, 'POST');
  assert.equal(calls[1][1].headers['Content-Type'], 'application/json');
  assert.equal(calls[1][1].body, '{"livroId":"x"}');
});
test('API comunica erro do servidor, rede/CORS e resposta inválida', async () => {
  const config = { URL_LISTAR: 'https://example.com' };
  await assert.rejects(createApi(config, async () => ({ ok: false, status: 409, json: async () => ({ erro: 'Já existe interesse ativo.' }) })).list('livros'), /Já existe interesse ativo/);
  await assert.rejects(createApi(config, async () => { throw new TypeError('Failed to fetch'); }).list('livros'), /rede.*CORS/i);
  await assert.rejects(createApi(config, async () => ({ ok: true, json: async () => { throw new Error('html'); } })).list('livros'), /resposta.*JSON/i);
});

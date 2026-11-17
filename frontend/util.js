(function (root) {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function moeda(value) {
    if (value == null || value === '' || !Number.isFinite(Number(value))) return '—';
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(Number(value));
  }
  function dt(value) {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
  }
  function text(value, label, max = 300) {
    const result = String(value ?? '').trim();
    if (!result || result.length > max) throw new Error(`${label}: preencha até ${max} caracteres.`);
    return result;
  }
  function number(value, label, min, integer) {
    const parsed = Number(value);
    if (typeof value === 'boolean' || value == null || String(value).trim() === '' || !Number.isFinite(parsed) || parsed < min || (integer && !Number.isSafeInteger(parsed))) throw new Error(`${label}: informe ${integer ? 'um número inteiro' : 'um valor numérico'} maior ou igual a ${min}.`);
    return parsed;
  }
  function cadastroPayload(input) {
    const result = { titulo: text(input.titulo, 'Título'), autor: text(input.autor, 'Autor'), quantidade: number(input.quantidade, 'Quantidade', 1, true), preco: number(input.preco, 'Preço', 0, false) };
    if (String(input.livroId ?? '').trim()) result.livroId = text(input.livroId, 'Código', 100);
    if (String(input.ano ?? '').trim()) result.ano = number(input.ano, 'Ano', 1, true);
    if (String(input.condicao ?? '').trim()) result.condicao = text(input.condicao, 'Condição', 100);
    return result;
  }
  function clientePayload(input) {
    const result = { livroId: text(input.livroId, 'Selecione um livro', 100), emailCliente: text(input.emailCliente, 'E-mail', 254).toLowerCase() };
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(result.emailCliente)) throw new Error('Informe um e-mail válido.');
    if (String(input.nomeCliente ?? '').trim()) result.nomeCliente = text(input.nomeCliente, 'Nome', 150);
    return result;
  }
  function createApi(config = {}, fetcher = (...args) => fetch(...args)) {
    async function request(key, body, resource) {
      if (!config[key]) throw new Error(`Configuração ausente: defina ${key} em frontend/config.js a partir de config.example.js.`);
      let url;
      try {
        const relative = /^\/(?!\/)/.test(config[key]);
        const base = root?.location?.href || 'http://localhost/';
        url = relative ? new URL(config[key], base) : new URL(config[key]);
        if (relative && url.origin !== new URL(base).origin) throw new Error();
        if (url.protocol !== 'https:' && !(url.protocol === 'http:' && (relative || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)))) throw new Error();
      }
      catch { throw new Error(`URL inválida em ${key}. Use HTTPS (ou HTTP local para testes).`); }
      if (resource) url.searchParams.set('recurso', resource);
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 20000);
      let response;
      try {
        response = await fetcher(url.toString(), { method: body === undefined ? 'GET' : 'POST', headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: controller.signal, credentials: 'omit' });
        let data;
        try { data = await response.json(); } catch { throw new Error('O serviço retornou uma resposta inválida (esperado JSON).'); }
        if (!response.ok) throw new Error(data.erro || data.mensagem || `O serviço retornou HTTP ${response.status}.`);
        if (!data || typeof data !== 'object') throw new Error('O serviço retornou uma resposta inválida.');
        return data;
      } catch (error) {
        if (!response) throw new Error('Não foi possível conectar ao serviço. Verifique sua rede, as URLs e a configuração de CORS. Se um envio foi interrompido, atualize os dados antes de tentar novamente.');
        throw error;
      } finally { clearTimeout(timeout); }
    }
    return { list: resource => request('URL_LISTAR', undefined, resource), post: (action, body) => {
      const key = { solicitar: 'URL_SOLICITAR', cadastrar: 'URL_CADASTRAR', efetivar: 'URL_EFETIVAR' }[action];
      if (!key) return Promise.reject(new Error('Operação desconhecida.'));
      return request(key, body);
    } };
  }
  const api = { esc, moeda, dt, cadastroPayload, clientePayload, createApi };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SeboUtil = api;
})(typeof window !== 'undefined' ? window : null);

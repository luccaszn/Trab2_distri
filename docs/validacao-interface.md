# Validação da interface

## Escopo

Chromium real (Chrome headless via Playwright), desktop 1440×1050 e celular 390×844. Backend real da aplicação com DynamoDB/SNS emulados com Moto, isolado em processo local. Sem chamadas ou e-mails AWS reais.

## Exercitado

- Catálogo, busca, seleção, pedido disponível e conflito de pedido duplicado.
- Aba Colaborador, confirmação e registro de venda, atualização do histórico.
- Pedido sem estoque, chegada de exemplares, atendimento do pendente e contagem de reservas/publicações aceita.
- Cadastro de título contendo HTML malicioso: exibido literalmente; nenhum elemento/script injetado executou.
- Configuração ausente e falha de rede: mensagens visíveis, sem catálogo fictício.
- Largura de documento nos dois tamanhos: sem overflow horizontal global nos estados testados.
- Nenhum erro JavaScript não tratado observado nos dois testes de navegador.

## Problemas corrigidos na integração

| Problema | Severidade / classe | Correção e verificação |
|---|---|---|
| Schemas ausentes / caminho do servidor local diferente do backend | Alta / funcional | Schemas extraídos do template e compartilhados por deploy, testes e servidor; HTTP e browser reexecutados |
| Seed AWS diferente dos quatro títulos documentados | Média / integração | Fonte única infra/livros_seed.json; teste verifica quantidade e preservação de itens existentes |
| Aviso da chegada imprimia lista de e-mails no lugar de contagem | Baixa / conteúdo | UI mostra clientesReservados e clientesNotificados; browser verifica números |

## Evidências

- `evidencias/cliente-desktop.png`
- `evidencias/cliente-mobile.png`
- `evidencias/colaborador-desktop.png`
- `resultados_testes.txt`

As capturas foram revisadas visualmente. São evidências locais, não prints AWS. Os testes não são auditoria completa de acessibilidade, teste de carga, autenticação nem prova de recebimento SNS. A função de browser integrada do Hermes encontrou bloqueio por o navegador padrão ser Zen; a alternativa real usada foi Chrome via Playwright, sem alterar o navegador padrão.

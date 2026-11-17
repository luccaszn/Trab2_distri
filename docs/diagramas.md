# Diagramas da aplicação

Os blocos Mermaid abaixo podem ser renderizados no GitHub, em um editor compatível ou no Mermaid Live Editor. As setas representam chamadas e dependências, não uma VPC: a solução não usa EC2, NAT ou RDS.

## Diagrama em blocos

```mermaid
flowchart TB
    C[Cliente] --> UI[Interface web estática]
    O[Colaborador] --> UI
    UI -->|GET / Function URL| L[sebo-listar-livros]
    UI -->|POST / Function URL| S[sebo-solicitar-livro]
    UI -->|POST / Function URL| A[sebo-cadastrar-livro]
    UI -->|POST / Function URL| V[sebo-efetivar-venda]
    L --> DB[(DynamoDB\nLivros / Interesses / Vendas)]
    S -->|Transação de reserva + interesse| DB
    A -->|Entrada de estoque + fila| DB
    V -->|Transação de venda| DB
    S --> SNS[SNS sebo-notificacoes]
    A --> SNS
    SNS -->|emailCliente + assinatura confirmada| E[E-mail do cliente]
    K[Lambda Layer sebo-common] -.-> L
    K -.-> S
    K -.-> A
    K -.-> V
```

## Diagrama UML de sequência

```mermaid
sequenceDiagram
    actor C as Cliente
    participant UI as Interface web
    participant S as Lambda solicitar
    participant D as DynamoDB
    participant N as SNS
    Note over C,N: Fluxos A/B — pedido de livro
    C->>UI: Seleciona livro e informa e-mail
    UI->>S: POST livroId, emailCliente, nomeCliente
    S->>S: Valida e normaliza dados
    S->>D: Lê livro e verifica interesse ativo
    alt Livro ausente / entrada inválida / duplicado
        S-->>UI: 404 / 400 / 409
    else Há exemplar disponível
        S->>D: Transação: estoque -1 + interesse RESERVADO + dedupe
        D-->>S: Commit ou conflito (retry limitado)
        S->>N: Publish com emailCliente
        alt SNS aceita publicação
            N-->>C: E-mail para comparecer à livraria
            S->>D: Registra dataNotificacao
            S-->>UI: RESERVADO, emailEnviado=true
        else Falha na publicação
            S-->>UI: RESERVADO, emailEnviado=false
            Note over S,D: Reserva permanece - não há rollback do estoque por falha SNS
        end
    else Sem exemplar
        S->>D: Transação: interesse PENDENTE + dedupe
        S-->>UI: PENDENTE, sem e-mail agora
    end
```

### Chegada e atendimento da fila

```mermaid
sequenceDiagram
    actor O as Colaborador
    actor C as Cliente
    participant UI as Interface web
    participant A as Lambda cadastrar
    participant D as DynamoDB
    participant N as SNS
    Note over O,N: Chegada de livros — atendimento da fila
    O->>UI: Registra chegada e quantidade
    UI->>A: POST cadastro/entrada
    A->>D: Lê livro e versão
    A->>D: Scan consistente e paginado dos pendentes
    A->>A: Ordena FIFO e seleciona até o estoque / limite 99
    A->>D: Transação: soma entrada, abate reservas e muda selecionados para RESERVADO
    D-->>A: Commit ou conflito (relê e recalcula)
    loop Para cada reserva confirmada
        A->>N: Publish disponibilidade
        N-->>C: E-mail de chegada (assinatura confirmada)
    end
    A-->>UI: Estoque final e publicações aceitas
```

### Efetivação da venda

```mermaid
sequenceDiagram
    actor O as Colaborador
    participant UI as Interface web
    participant V as Lambda efetivar
    participant D as DynamoDB
    Note over O,D: Fluxo C — efetivação presencial da venda
    O->>UI: Efetivar interesse RESERVADO
    UI->>V: POST interesseId
    V->>D: Lê interesse e valor capturado na reserva
    V->>D: Transação: RESERVADO para VENDIDO + grava venda + libera dedupe
    alt Estado já alterado
        V-->>UI: 409 e statusAtual
    else Commit
        V-->>UI: Venda registrada
    end
```

**Leitura importante:** `Publish` aceito não comprova entrega na caixa de entrada. O SNS depende de assinatura confirmada, filtro correspondente e processamento do provedor de e-mail. Os testes locais emulam os serviços; a entrega real precisa ser conferida na AWS e na caixa postal.

# Discord Support Bot – Caveira Sistemas

Este projeto contém um bot de suporte técnico para Discord, desenvolvido em Python com `discord.py`, responsável por automatizar o atendimento inicial de problemas relacionados a sistemas internos da empresa.

O bot cria tópicos de atendimento (threads), conduz o usuário por um fluxo de diagnóstico automatizado e, quando necessário, encaminha o chamado para a equipe responsável.

Além disso, o bot integra com N8N para registro e automação de fluxos de suporte.

---

## Principais Funcionalidades

### 📌 Abertura de chamados automatizada

Usuários podem abrir chamados diretamente no Discord. Ao iniciar um atendimento, o bot:

- cria uma thread privada de suporte
- solicita informações iniciais sobre o problema
- registra os dados do atendimento

### 🧠 Diagnóstico automatizado

O bot conduz o usuário por um fluxo interativo de diagnóstico, utilizando:

- botões
- formulários
- perguntas sequenciais

Dependendo das respostas do usuário, o bot pode:

- sugerir ações de solução
- coletar mais informações
- encaminhar o chamado para a equipe técnica

### ⚠️ Identificação automática de erros

O bot possui uma base de soluções (`solutions.json`) contendo códigos de erro e suas respectivas resoluções.

Quando o usuário informa um erro:

1. O bot tenta identificar automaticamente o código
2. Procura na base de soluções
3. Caso encontre:
   - envia a solução diretamente no privado do usuário
   - registra o evento
   - encerra o atendimento automático

Caso não encontre solução, o chamado é encaminhado para a equipe de suporte humano.

### 👥 Encaminhamento para equipes responsáveis

Dependendo do tipo de problema, o bot pode acionar automaticamente equipes como:

- ChatGuru
- Whom
- Suporte técnico geral
- ClickUp Support

Isso é feito através da menção automática de cargos específicos no Discord.

### 📝 Registro de diagnóstico

Durante o atendimento, o bot registra cada etapa do diagnóstico:

- tipo de problema
- ações tentadas
- código de erro informado
- solução encontrada ou não

Essas informações são organizadas em um payload estruturado, que posteriormente pode ser enviado para integrações externas.

### 🔗 Integração com N8N

O bot envia dados de atendimento para um webhook do N8N, permitindo:

- automação de processos
- criação de registros de suporte
- integração com outros sistemas internos

---

## Estrutura do Projeto

```
.
├── caveira-sistemas.py
├── caveira-contato.py
├── caveira-suporte.py
├── solutions.json
├── .gitignore
```

### `caveira-sistemas.py`

Arquivo principal do bot. Responsável por:

- conexão com o Discord
- criação de threads de suporte
- fluxo de diagnóstico automatizado
- interação com usuários via botões e formulários
- comunicação com o webhook do N8N

### `solutions.json`

Base de conhecimento utilizada pelo bot. Contém códigos de erro e possíveis soluções utilizadas para resposta automática aos usuários.

---

## Variáveis de Ambiente

O projeto utiliza um arquivo `.env` para armazenar credenciais sensíveis. Exemplo:

```env
DISCORD_TOKEN=seu_token_do_bot
N8N_WEBHOOK_URL=https://webhook-n8n
GROQ_API_KEY=sua_chave_da_groq
AI_MODEL=openai/gpt-oss-20b
```

### Atendimento e diagnóstico com IA

Em Equipamentos, a conversa com IA começa automaticamente quando o chamado é
aberto. Em Sistemas, ela começa assim que o solicitante escolhe o tipo do
problema; E-mail, Google Drive, 3c+, Falepaco e Robôs/Automações também usam a
mesma conversa após coletarem seus dados iniciais. O comando `!ajuda` permanece
como alternativa caso a inicialização automática falhe. A IA faz perguntas
curtas, sugere ações seguras e acompanha as respostas.

Quando o problema for resolvido ou o solicitante confirmar que deseja
atendimento humano, o bot publica um resumo com diagnóstico, tentativas
realizadas, situação atual, próximos passos e prioridade sugerida. Casos
complexos, permissões e o limite automático apenas fazem a IA oferecer a
intervenção; ninguém é acionado sem a confirmação explícita do solicitante.
Atendentes também podem gerar esse material a qualquer momento com `!resumo`.
`!encerrar_ia` encerra manualmente a conversa e gera o mesmo resumo. O comando
`!ia` continua disponível para uma análise pontual feita por atendentes.

Antes de consultar a Groq, o bot remove do contexto CPF, e-mail, telefone,
links, identificadores, credenciais e nomes conhecidos dos participantes.

No encerramento humano, `!logs` (Equipamentos) e `!sistema` (Sistemas) exigem
categoria da solução, resultado final e uma descrição curta do que foi feito.
Esses dados seguem no payload do n8n e também no histórico textual enviado ao
ClickUp, usando as chaves `solucao_final` e `resultado_final`.

O contexto institucional usado pela IA fica em
`knowledge_base/institutional.json`. POPs podem ser adicionados em
`knowledge_base/pops/`, organizados por setor, nos formatos `.md`, `.txt` ou
`.json`. Em cada atendimento, o bot inclui as regras institucionais e seleciona
localmente somente os trechos de POP relacionados ao assunto. Não coloque
credenciais nem dados pessoais nessa base.

Os POPs de teste atuais incluem suporte tecnológico/ChatGuru, fundamentos de
Operações e Sistemas, triagem de Auxílio-Acidente e comunicação de
Documentação. Os conteúdos previdenciários servem apenas para triagem e próximo
passo: a IA não fornece parecer jurídico, não analisa exames ou documentos e
nunca pede senha Gov.br, códigos, CPF, número de benefício ou anexos sensíveis.

Quando a pessoa informa um código de erro, o bot procura primeiro o código nos
POPs internos e redige a resposta com base na orientação encontrada. Se o código
não existir na base, ele consulta resultados públicos usando somente o nome do
sistema e o código — nunca o conteúdo completo do chamado. Essa consulta pode
ser desativada com `ERROR_WEB_SEARCH_ENABLED=false` no `.env`; resultados
externos são tratados como informação a confirmar, não como procedimento oficial.

Com `CLICKUP_KNOWLEDGE_ENABLED=true` (padrão), o bot também atualiza em segundo
plano uma base agregada de soluções históricas do ClickUp a cada 360 minutos.
Ele lê somente as listas configuradas, não altera tarefas e ignora título,
comentários e anexos. Da descrição, aproveita somente linhas explicitamente
rotuladas como sistema, problema, solução ou resultado; os padrões entram como
referência a validar, nunca como POP aprovado automaticamente. Ajustes opcionais
no `.env`:

```env
CLICKUP_KNOWLEDGE_ENABLED=true
CLICKUP_KNOWLEDGE_REFRESH_MINUTES=360
CLICKUP_KNOWLEDGE_MAX_PAGES=20
```

### Histórico de chamados no ClickUp

Para habilitar uma leitura **somente de consulta** das listas usadas para
análise de problemas recorrentes, configure no `.env`:

```env
CLICKUP_API_TOKEN=pk_seu_token
CLICKUP_SUPPORT_LIST_IDS=123456789,987654321
```

Teste a conexão sem exibir títulos ou descrições dos chamados:

```powershell
.\.venv\Scripts\python.exe scripts\clickup_read_check.py
```

O token nunca deve ser enviado no Discord, no chat ou incluído em arquivos
versionados. A consulta não cria, edita nem exclui tarefas.

Todos os comandos de IA são bloqueados em chamados de
Recuperar Contato. Toda resposta deve ser validada por um atendente humano.

---

## Tecnologias Utilizadas

- Python
- discord.py
- asyncio
- requests
- dotenv
- JSON
- N8N (automação de fluxos)

---

## Objetivo do Projeto

O bot foi desenvolvido para:

- reduzir o volume de atendimentos manuais
- automatizar diagnósticos simples
- organizar chamados técnicos no Discord
- integrar suporte com sistemas de automação

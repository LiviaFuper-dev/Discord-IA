# POPs dos setores

Esta pasta recebe os Procedimentos Operacionais Padrão usados pela IA do suporte.

Formatos aceitos automaticamente:

- `.md`
- `.txt`
- `.json`

Organize os arquivos em subpastas por setor, por exemplo:

```text
knowledge_base/pops/
├── equipamentos/
│   └── troca-de-monitor.md
├── sistemas/
│   └── acesso-ao-email.md
└── atendimento/
    └── encaminhamento-juridico.md
```

Cada POP deve informar, sempre que possível:

1. título e setor responsável;
2. quando o procedimento se aplica;
3. perguntas iniciais;
4. passos permitidos para o solicitante;
5. critérios de interrupção e segurança;
6. quando e para quem escalar;
7. data da última revisão.

Não inclua senhas, tokens, chaves, dados de clientes ou outros segredos. A IA
seleciona somente os trechos mais relacionados ao chamado atual.

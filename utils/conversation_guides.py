"""Roteiros internos para transformar os antigos formulários em conversa.

Os itens abaixo não são respostas prontas. São objetivos de coleta usados pelo
prompt da IA; ela deve escolher somente o próximo item relevante e perguntar em
linguagem natural, aproveitando o que a pessoa já informou.
"""

from __future__ import annotations

import re


def _find(text: str, pattern: str) -> str:
    match = re.search(pattern, text or "", flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def build_conversation_guide(initial_context: str) -> str:
    """Retorna um roteiro curto e específico para o sistema do chamado."""
    raw = str(initial_context or "")
    system = _find(raw, r"(?:Sistema|Área):\s*([^\.\n]+)")
    problem = _find(raw, r"Tipo de problema selecionado:\s*([^\.\n]+)")
    subsystem = _find(raw, r"Subsistema:\s*([^\.\n]+)")
    lowered = f"{system} {problem} {subsystem}".lower()

    if "inss" in lowered and "automa" in lowered:
        items = (
            "1) confirmar se faltam documentos no download; "
            "2) descobrir se ocorre em um cliente, vários ou todos; "
            "3) saber se é sempre o mesmo documento ou se varia; "
            "4) pedir o nome do documento e a mensagem exibida, sem dados do cliente; "
            "5) pedir print somente se a pessoa tiver condições de enviar."
        )
    elif "chatguru" in lowered and "automa" in lowered:
        items = (
            "1) confirmar se o robô não baixa imagens; "
            "2) descobrir se não baixa nenhuma ou apenas algumas; "
            "3) perguntar quando começou e em qual etapa ocorre; "
            "4) pedir texto/código do erro e print, sem dados sensíveis."
        )
    elif "chatguru" in lowered:
        items = (
            "1) perguntar o que a pessoa tentava fazer no ChatGuru; "
            "2) identificar se a página não carrega, está lenta, mostra erro ou aviso; "
            "3) quando houver erro, pedir o código que aparece antes da mensagem; "
            "4) perguntar se cache, Ctrl+F5, espera de cinco minutos e reinício do computador já foram tentados; "
            "5) pedir print da tela inteira, sem dados sensíveis."
        )
    elif "automa" in lowered or "planilha" in lowered or "robô" in lowered:
        items = (
            "1) perguntar qual automação e qual resultado era esperado; "
            "2) saber o que aconteceu de fato e desde quando; "
            "3) perguntar se ocorre em um caso ou em vários; "
            "4) pedir a mensagem/código do erro e print, sem dados sensíveis."
        )
    elif "falepaco" in lowered:
        items = (
            "1) confirmar se a dificuldade é baixar, instalar ou abrir o Falepaco; "
            "2) perguntar qual mensagem aparece e em que etapa; "
            "3) verificar se o download já foi tentado novamente; "
            "4) se for senha, orientar o gestor; nunca pedir a senha."
        )
    elif "e-mail" in lowered or "email" in lowered or "google drive" in lowered:
        items = (
            "1) identificar se não consegue entrar, enviar, receber, abrir ou localizar algo; "
            "2) perguntar se ocorre no navegador ou em outro aplicativo; "
            "3) pedir o texto/código do erro e quando começou; "
            "4) confirmar se outras pessoas têm o mesmo problema; nunca pedir senha."
        )
    elif "3c+" in lowered:
        items = (
            "1) perguntar o que a pessoa precisa fazer no 3c+; "
            "2) saber o que aparece de diferente e desde quando; "
            "3) pedir texto/código do erro ou print, sem dados pessoais; "
            "4) confirmar se afeta somente um caso ou vários."
        )
    elif "whom" in lowered:
        items = (
            "1) perguntar qual ação não funciona no Whom; "
            "2) verificar se a extensão mostra aviso vermelho ou amarelo; "
            "3) perguntar o que aparece ao clicar em Status; "
            "4) perguntar se cache, Ctrl+F5, espera de cinco minutos e reinício do computador já foram tentados; "
            "5) pedir texto/código do aviso e print, sem dados sensíveis."
        )
    elif "clickup" in lowered:
        items = (
            "1) perguntar se o ClickUp inteiro, uma lista ou uma tarefa está lento; "
            "2) identificar a ação que demora ou não conclui e desde quando; "
            "3) perguntar se Ctrl+F5, cache, espera de cinco minutos, reinício do computador e outro navegador já foram tentados; "
            "4) confirmar se outras pessoas têm o mesmo problema; "
            "5) pedir texto/código do erro e print, sem dados sensíveis."
        )
    else:
        items = (
            "1) perguntar o que a pessoa tentava fazer; "
            "2) perguntar o que apareceu de diferente e desde quando; "
            "3) perguntar se já tentou atualizar, limpar cache ou reiniciar, sem repetir; "
            "4) pedir texto/código do erro ou print, sem dados sensíveis."
        )

    if "permiss" in lowered or "cadastro" in lowered:
        items = (
            "1) identificar exatamente qual acesso ou cadastro é necessário; "
            "2) perguntar se a pessoa já teve esse acesso e qual mensagem aparece; "
            "3) confirmar a urgência (alta, média ou baixa); "
            "4) não sugerir cache/atualização e só oferecer TI após confirmação explícita."
        )

    return (
        "ROTEIRO INTERNO DO FLUXO ORIGINAL (não mostre esta lista): "
        + items
        + " Use como checklist, pule itens já respondidos, faça uma pergunta textual por vez, "
        "não apresente alternativas em botões e não repita a mesma pergunta."
    )

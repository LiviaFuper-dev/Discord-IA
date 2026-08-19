from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output" / "pdf" / "comparativo-custos-ia-bot-suporte.pdf"

NAVY = colors.HexColor("#17233B")
BLUE = colors.HexColor("#3559E0")
CYAN = colors.HexColor("#17A7A0")
LIGHT_BLUE = colors.HexColor("#EEF3FF")
LIGHT_GRAY = colors.HexColor("#F4F6F8")
MID_GRAY = colors.HexColor("#667085")
DARK = colors.HexColor("#202838")
GREEN = colors.HexColor("#1A7F55")
WHITE = colors.white


def money(value: float) -> str:
    return f"US$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=30,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleCustom",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#DDE5FF"),
        ),
        "h1": ParagraphStyle(
            "H1Custom",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2Custom",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=15,
            textColor=BLUE,
            spaceBefore=5,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.3,
            leading=13.2,
            textColor=DARK,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "SmallCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=MID_GRAY,
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.3,
            leading=13,
            leftIndent=11,
            firstLineIndent=-7,
            bulletIndent=0,
            textColor=DARK,
            spaceAfter=3,
        ),
        "callout": ParagraphStyle(
            "CalloutCustom",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=NAVY,
            backColor=LIGHT_BLUE,
            borderColor=BLUE,
            borderWidth=0.8,
            borderPadding=9,
            spaceBefore=5,
            spaceAfter=10,
        ),
        "recommendation": ParagraphStyle(
            "RecommendationCustom",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=17,
            textColor=WHITE,
            backColor=GREEN,
            borderColor=GREEN,
            borderWidth=1,
            borderPadding=12,
            spaceBefore=8,
            spaceAfter=10,
        ),
        "source": ParagraphStyle(
            "SourceCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.2,
            leading=9.5,
            textColor=MID_GRAY,
            leftIndent=8,
            firstLineIndent=-8,
            spaceAfter=4,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.7,
            leading=9.5,
            textColor=WHITE,
            alignment=TA_CENTER,
        ),
        "table_cell": ParagraphStyle(
            "TableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.7,
            leading=9.5,
            textColor=DARK,
            alignment=TA_CENTER,
        ),
        "table_cell_left": ParagraphStyle(
            "TableCellLeft",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.7,
            leading=9.5,
            textColor=DARK,
            alignment=TA_LEFT,
        ),
    }


def P(text, style):
    return Paragraph(text, style)


def bullet(text, styles):
    return P(f"- {text}", styles["bullet"])


def styled_table(data, widths, styles, *, highlight_row=None):
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D7DCE5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for row in range(1, len(data)):
        commands.append(("BACKGROUND", (0, row), (-1, row), WHITE if row % 2 else LIGHT_GRAY))
    if highlight_row is not None:
        commands.extend([
            ("BACKGROUND", (0, highlight_row), (-1, highlight_row), colors.HexColor("#E8F7F0")),
            ("BOX", (0, highlight_row), (-1, highlight_row), 1.1, GREEN),
        ])
    table.setStyle(TableStyle(commands))
    return table


def decorate_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    if doc.page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 15 * mm, width, 15 * mm, stroke=0, fill=1)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 8.5)
        canvas.drawString(17 * mm, height - 9.5 * mm, "COMPARATIVO DE CUSTOS DE IA")
    canvas.setStrokeColor(colors.HexColor("#D7DCE5"))
    canvas.line(17 * mm, 13 * mm, width - 17 * mm, 13 * mm)
    canvas.setFillColor(MID_GRAY)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(17 * mm, 8.5 * mm, "Estimativa para o bot interno de suporte")
    canvas.drawRightString(width - 17 * mm, 8.5 * mm, f"Página {doc.page}")
    canvas.restoreState()


def build_pdf():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    styles = build_styles()
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        title="Comparativo de custos de IA para o bot de suporte",
        author="Equipe de Sistemas",
        subject="Estimativa de custos e recomendação de modelo de IA",
    )
    story = []

    cover = Table(
        [[P("COMPARATIVO DE CUSTOS<br/>DE IA PARA O BOT DE SUPORTE", styles["title"])],
         [P("Valores, estimativas de consumo e recomendação para o teste em produção", styles["subtitle"])],
         [P("Atualizado em 5 de agosto de 2026", styles["subtitle"])]],
        colWidths=[176 * mm],
        rowHeights=[46 * mm, 18 * mm, 13 * mm],
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 15 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 13 * mm),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.HexColor("#6172A8")),
    ]))
    story.extend([cover, Spacer(1, 12 * mm)])
    story.append(P(
        "<b>Conclusão executiva</b><br/>Para o bot atual, a opção recomendada é o "
        "<b>Groq Developer com GPT-OSS 120B</b>. O modelo mantém baixo custo, alta "
        "velocidade e exige pouca alteração no projeto existente.",
        styles["recommendation"],
    ))
    story.append(Spacer(1, 5 * mm))
    story.append(P(
        "Este documento utiliza preços públicos por token e uma simulação conservadora "
        "do fluxo atual. Os valores finais variam conforme o tamanho do histórico, número "
        "de mensagens, cache, câmbio e impostos.",
        styles["body"],
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(P("Destaques", styles["h1"]))
    story.append(bullet("O plano gratuito da Groq é adequado para desenvolvimento, mas os limites de tokens podem interromper atendimentos reais.", styles))
    story.append(bullet("Mil chamados completos custariam aproximadamente US$ 5,66 no GPT-OSS 120B, segundo as premissas desta simulação.", styles))
    story.append(bullet("O ChatGPT Plus ou Business não cobre o consumo da API utilizada pelo bot.", styles))
    story.append(bullet("Para leitura de prints, recomenda-se um modelo com visão acionado somente quando houver imagem.", styles))
    story.append(PageBreak())

    story.append(P("1. Como a cobrança funciona", styles["h1"]))
    story.append(P(
        "As APIs cobram principalmente pelos tokens de <b>entrada</b> e de <b>saída</b>. "
        "A entrada inclui o prompt, o histórico do chamado, os POPs e as mensagens. "
        "A saída corresponde ao texto produzido pela IA.",
        styles["body"],
    ))
    story.append(bullet("Os preços abaixo são informados por 1 milhão de tokens.", styles))
    story.append(bullet("Na Groq Developer não há mensalidade fixa: a cobrança ocorre conforme o uso.", styles))
    story.append(bullet("ChatGPT e API possuem cobranças separadas.", styles))

    story.append(P("2. Valores por modelo", styles["h1"]))
    pricing_rows = [
        [P("Modelo", styles["table_header"]), P("Entrada / 1M", styles["table_header"]), P("Saída / 1M", styles["table_header"]), P("Avaliação para o bot", styles["table_header"])],
        [P("Groq GPT-OSS 20B", styles["table_cell_left"]), P("US$ 0,075", styles["table_cell"]), P("US$ 0,30", styles["table_cell"]), P("Muito barato, porém menos consistente", styles["table_cell_left"])],
        [P("Groq GPT-OSS 120B", styles["table_cell_left"]), P("US$ 0,15", styles["table_cell"]), P("US$ 0,60", styles["table_cell"]), P("Melhor custo-benefício atual", styles["table_cell_left"])],
        [P("OpenAI GPT-5.6 Luna", styles["table_cell_left"]), P("US$ 0,20", styles["table_cell"]), P("US$ 1,20", styles["table_cell"]), P("Eficiente para alto volume", styles["table_cell_left"])],
        [P("Gemini 3.5 Flash-Lite", styles["table_cell_left"]), P("US$ 0,30", styles["table_cell"]), P("US$ 2,50", styles["table_cell"]), P("Multimodal, com custo maior", styles["table_cell_left"])],
        [P("OpenAI GPT-5.6 Terra", styles["table_cell_left"]), P("US$ 2,00", styles["table_cell"]), P("US$ 12,00", styles["table_cell"]), P("Qualidade maior; excesso para a triagem", styles["table_cell_left"])],
    ]
    story.append(styled_table(pricing_rows, [43 * mm, 29 * mm, 29 * mm, 65 * mm], styles, highlight_row=2))
    story.append(Spacer(1, 3 * mm))
    story.append(P(
        "A OpenAI posiciona o GPT-5.6 Luna para alto volume, o Terra para equilíbrio "
        "entre capacidade e custo e o Sol para trabalhos de capacidade máxima.",
        styles["small"],
    ))

    story.append(P("3. Premissas da estimativa", styles["h1"]))
    story.append(P(
        "A simulação considera um chamado com até <b>8 respostas da IA</b>, média de "
        "<b>4.000 tokens de entrada</b> e <b>180 tokens de saída</b> em cada resposta. "
        "Isso representa aproximadamente 32.000 tokens de entrada e 1.440 de saída por chamado.",
        styles["callout"],
    ))
    story.append(PageBreak())

    story.append(P("4. Estimativa mensal", styles["h1"]))
    estimates = {
        "Groq GPT-OSS 20B": (1.416, 2.832, 14.16),
        "Groq GPT-OSS 120B": (2.832, 5.664, 28.32),
        "OpenAI GPT-5.6 Luna": (4.064, 8.128, 40.64),
        "Gemini 3.5 Flash-Lite": (6.60, 13.20, 66.00),
        "OpenAI GPT-5.6 Terra": (40.64, 81.28, 406.40),
    }
    estimate_rows = [[
        P("Modelo", styles["table_header"]),
        P("500 chamados", styles["table_header"]),
        P("1.000 chamados", styles["table_header"]),
        P("5.000 chamados", styles["table_header"]),
    ]]
    for model, values in estimates.items():
        estimate_rows.append([
            P(model, styles["table_cell_left"]),
            P(money(values[0]), styles["table_cell"]),
            P(money(values[1]), styles["table_cell"]),
            P(money(values[2]), styles["table_cell"]),
        ])
    story.append(styled_table(estimate_rows, [49 * mm, 39 * mm, 39 * mm, 39 * mm], styles, highlight_row=2))
    story.append(Spacer(1, 4 * mm))
    story.append(P(
        "Usando apenas como exemplo um câmbio de R$ 5,50 por dólar, 1.000 chamados "
        "no GPT-OSS 120B custariam aproximadamente <b>R$ 31,15</b>, antes de impostos "
        "e variação cambial.",
        styles["callout"],
    ))
    story.append(P(
        "O custo pode ser menor quando o cache reaproveita partes repetidas do prompt. "
        "Na Groq, a entrada em cache do GPT-OSS custa 50% menos.",
        styles["body"],
    ))

    story.append(P("5. Por que o plano gratuito acaba rápido", styles["h1"]))
    story.append(P(
        "Os limites gratuitos publicados para o GPT-OSS 120B incluem 30 requisições por "
        "minuto, 1.000 por dia, 8.000 tokens por minuto e 200.000 tokens por dia. Como "
        "o bot envia histórico, regras e POPs, o limite de tokens tende a ser atingido "
        "antes do limite de requisições.",
        styles["body"],
    ))
    story.append(P(
        "Na simulação deste relatório, o teto diário de 200 mil tokens comportaria "
        "aproximadamente seis atendimentos completos. Os limites exatos devem ser "
        "confirmados no painel da organização.",
        styles["small"],
    ))

    story.append(P("6. Recomendação", styles["h1"]))
    story.append(P(
        "<b>Adotar Groq Developer com GPT-OSS 120B para o teste real.</b><br/>"
        "A diferença de preço em relação ao 20B é pequena, enquanto o ganho esperado "
        "de consistência no acompanhamento dos POPs e da conversa é mais relevante.",
        styles["recommendation"],
    ))
    story.append(Spacer(1, 5 * mm))
    story.append(bullet("Definir limite inicial de US$ 20 por mês.", styles))
    story.append(bullet("Criar alertas de consumo em 50%, 75% e 90%.", styles))
    story.append(bullet("Acompanhar volume e qualidade durante duas a quatro semanas.", styles))
    story.append(bullet("Usar um modelo com visão apenas quando houver print ou anexo.", styles))
    story.append(P(
        "O GPT-OSS 120B servido pela Groq é textual. A futura leitura de imagens deve "
        "ser implementada como uma rota separada, mantendo o custo principal da conversa baixo.",
        styles["body"],
    ))

    story.append(PageBreak())
    story.append(P("Fontes oficiais", styles["h1"]))
    sources = [
        ("Groq - preços", "https://groq.com/pricing"),
        ("Groq - cobrança e plano Developer", "https://console.groq.com/docs/billing-faqs"),
        ("Groq - limites gratuitos", "https://console.groq.com/docs/rate-limits"),
        ("Groq - cache de prompt", "https://console.groq.com/docs/prompt-caching"),
        ("Groq - GPT-OSS 120B", "https://console.groq.com/docs/model/openai/gpt-oss-120b"),
        ("Groq - limites de gastos", "https://console.groq.com/docs/spend-limits"),
        ("OpenAI - preços da API", "https://developers.openai.com/api/docs/pricing"),
        ("OpenAI - guia da família GPT-5.6", "https://developers.openai.com/api/docs/guides/latest-model.md"),
        ("OpenAI - ChatGPT Business e API", "https://help.openai.com/en/articles/8792828-what-is-chatgpt-team"),
        ("Google - preços da API Gemini", "https://ai.google.dev/gemini-api/docs/pricing"),
    ]
    for title, url in sources:
        story.append(P(f'- <b>{title}</b><br/><link href="{url}" color="#3559E0">{url}</link>', styles["source"]))
    story.append(Spacer(1, 8 * mm))
    story.append(P(
        "Nota: preços, modelos, limites e condições podem mudar. Antes da contratação, "
        "confirme os valores nas páginas oficiais e no painel da conta.",
        styles["callout"],
    ))

    doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    return OUTPUT


if __name__ == "__main__":
    print(build_pdf())

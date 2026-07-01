import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta
import base64, json

st.set_page_config(
    page_title="Pousada OS",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = get_supabase()

# ─── FORMATAÇÃO E VALIDAÇÃO ───────────────────────────────────────────────────

def formatar_cpf_cnpj(valor):
    nums = ''.join(filter(str.isdigit, valor))
    if len(nums) <= 11:
        nums = nums[:11]
        if len(nums) == 11:
            return f"{nums[:3]}.{nums[3:6]}.{nums[6:9]}-{nums[9:]}"
    else:
        nums = nums[:14]
        if len(nums) == 14:
            return f"{nums[:2]}.{nums[2:5]}.{nums[5:8]}/{nums[8:12]}-{nums[12:]}"
    return valor

def validar_cpf(cpf):
    nums = ''.join(filter(str.isdigit, cpf))
    if len(nums) != 11 or len(set(nums)) == 1:
        return False
    soma = sum(int(nums[i]) * (10 - i) for i in range(9))
    d1 = (soma * 10 % 11) % 10
    if d1 != int(nums[9]):
        return False
    soma = sum(int(nums[i]) * (11 - i) for i in range(10))
    d2 = (soma * 10 % 11) % 10
    return d2 == int(nums[10])

def validar_cnpj(cnpj):
    nums = ''.join(filter(str.isdigit, cnpj))
    if len(nums) != 14 or len(set(nums)) == 1:
        return False
    pesos1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    pesos2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    soma = sum(int(nums[i]) * pesos1[i] for i in range(12))
    d1 = 0 if soma % 11 < 2 else 11 - soma % 11
    if d1 != int(nums[12]):
        return False
    soma = sum(int(nums[i]) * pesos2[i] for i in range(13))
    d2 = 0 if soma % 11 < 2 else 11 - soma % 11
    return d2 == int(nums[13])

def validar_cpf_cnpj(valor):
    nums = ''.join(filter(str.isdigit, valor))
    if len(nums) == 11:
        return validar_cpf(valor)
    elif len(nums) == 14:
        return validar_cnpj(valor)
    return False

def formatar_telefone(valor):
    nums = ''.join(filter(str.isdigit, valor))
    nums = nums[:11]
    if len(nums) == 11:
        return f"({nums[:2]}) {nums[2:7]}-{nums[7:]}"
    elif len(nums) == 10:
        return f"({nums[:2]}) {nums[2:6]}-{nums[6:]}"
    return valor

def formatar_data(valor):
    """Converte DDMMAAAA ou DD/MM/AAAA para DD/MM/AAAA"""
    nums = ''.join(filter(str.isdigit, valor))
    if len(nums) == 8:
        return f"{nums[:2]}/{nums[2:4]}/{nums[4:]}"
    return valor

# ─── VALOR POR EXTENSO ────────────────────────────────────────────────────────

def valor_por_extenso(valor):
    unidades = ["", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
                "dez", "onze", "doze", "treze", "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove"]
    dezenas = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
    centenas = ["", "cem", "duzentos", "trezentos", "quatrocentos", "quinhentos",
                "seiscentos", "setecentos", "oitocentos", "novecentos"]

    def por_extenso_ate_999(n):
        if n == 0: return ""
        elif n == 100: return "cem"
        elif n < 20: return unidades[n]
        elif n < 100:
            d, u = divmod(n, 10)
            return dezenas[d] + (" e " + unidades[u] if u else "")
        else:
            c, resto = divmod(n, 100)
            parte_c = centenas[c]
            parte_r = por_extenso_ate_999(resto)
            return parte_c + (" e " + parte_r if parte_r else "")

    reais = int(valor)
    centavos = round((valor - reais) * 100)

    if reais == 0 and centavos == 0:
        return "zero reais"

    partes = []
    if reais > 0:
        if reais == 1:
            partes.append("um real")
        elif reais < 1000:
            partes.append(por_extenso_ate_999(reais) + " reais")
        elif reais < 1000000:
            mil, resto = divmod(reais, 1000)
            txt = ("um mil" if mil == 1 else por_extenso_ate_999(mil) + " mil")
            if resto:
                txt += " e " + por_extenso_ate_999(resto)
            partes.append(txt + " reais")
    if centavos > 0:
        partes.append(por_extenso_ate_999(centavos) + (" centavo" if centavos == 1 else " centavos"))

    return " e ".join(partes)

# ─── FUNÇÕES DE APOIO ─────────────────────────────────────────────────────────

def obter_operadoras():
    try:
        res = supabase.table("operadoras").select("nome").order("nome").execute()
        nomes = [r["nome"] for r in res.data]
        return nomes if nomes else ["Nenhuma cadastrada"]
    except Exception:
        return ["Erro ao carregar"]

def obter_categorias():
    try:
        res = supabase.table("categorias_despesa").select("nome, destino").order("destino").execute()
        return [f"{r['nome']} ({r['destino']})" for r in res.data]
    except Exception:
        return []

def extrair_destino(categoria_formatada):
    if "(" in categoria_formatada and ")" in categoria_formatada:
        partes = categoria_formatada.split(" (")
        nome = partes[0]
        destino = partes[1].replace(")", "")
        return nome, destino
    return categoria_formatada, "Pousada"

def buscar_hospede_por_nome(nome):
    try:
        res = supabase.table("hospedes").select("*").ilike("nome", f"%{nome}%").execute()
        return res.data
    except Exception:
        return []

def buscar_todos_hospedes():
    try:
        res = supabase.table("hospedes").select("*").order("nome").execute()
        return res.data
    except Exception:
        return []

def buscar_hospedagens_do_hospede(hospede_id):
    try:
        res = supabase.table("lancamentos").select("*").eq("hospede_id", hospede_id).eq("tipo", "Receita").order("id", desc=True).execute()
        return res.data
    except Exception:
        return []

def salvar_hospede(dados):
    try:
        res = supabase.table("hospedes").insert(dados).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Erro ao salvar hóspede: {e}")
        return None

# ─── GERADOR DE RECIBO HTML ───────────────────────────────────────────────────

def gerar_recibo_html(hospede, lancamento, numero_recibo):
    valor = lancamento.get("valor", 0)
    extenso = valor_por_extenso(valor)
    data = lancamento.get("data", "")
    pagamento = lancamento.get("modalidade", "")
    observacao = lancamento.get("observacao", "") or ""

    nome = hospede.get("nome", "")
    cpf = hospede.get("cpf", "") or ""
    celular = hospede.get("celular", "") or ""

    # Carregar logo como base64
    logo_tag = ""
    try:
        import os
        logo_path = "Pousada_Jaguaruana.png"
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            logo_tag = f'<img src="data:image/png;base64,{logo_b64}" class="logo">'
    except Exception:
        pass

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: Arial, sans-serif; background: #fff; }}
  .recibo {{
    width: 148mm;
    min-height: 105mm;
    margin: 10mm auto;
    padding: 8mm 10mm;
    border: 1px solid #ccc;
    font-size: 11pt;
  }}
  .header {{
    display: flex;
    align-items: center;
    gap: 12px;
    border-bottom: 1.5px solid #333;
    padding-bottom: 8px;
    margin-bottom: 10px;
  }}
  .logo {{ width: 70px; height: 70px; object-fit: contain; }}
  .pousada-info h2 {{ font-size: 13pt; margin-bottom: 2px; }}
  .pousada-info p {{ font-size: 8.5pt; color: #444; line-height: 1.5; }}
  .titulo {{
    text-align: center;
    font-size: 12pt;
    font-weight: bold;
    letter-spacing: 1px;
    margin-bottom: 3px;
    text-transform: uppercase;
  }}
  .numero {{ text-align: center; font-size: 9pt; color: #555; margin-bottom: 10px; }}
  .secao-titulo {{
    font-size: 8pt;
    font-weight: bold;
    text-transform: uppercase;
    color: #666;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }}
  .secao {{ margin-bottom: 8px; }}
  .linha {{
    display: flex;
    justify-content: space-between;
    font-size: 10pt;
    padding: 2px 0;
    border-bottom: 0.5px solid #ddd;
  }}
  .linha span:first-child {{ color: #555; }}
  .obs-campo {{ font-size: 10pt; padding: 2px 0; border-bottom: 0.5px solid #ddd; }}
  .obs-label {{ color: #555; display: block; }}
  .total-box {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #f5f5f5;
    padding: 7px 10px;
    margin: 10px 0 3px;
    border-radius: 4px;
  }}
  .total-label {{ font-size: 11pt; font-weight: bold; }}
  .total-valor {{ font-size: 15pt; font-weight: bold; }}
  .extenso {{ text-align: right; font-size: 9pt; color: #555; font-style: italic; margin-bottom: 14px; }}
  .assinatura {{ margin-top: 20px; text-align: center; }}
  .assinatura-linha {{ border-top: 1px solid #333; width: 55%; margin: 28px auto 4px; }}
  .assinatura p {{ font-size: 9pt; color: #555; }}
  .rodape {{
    text-align: center;
    font-size: 8pt;
    color: #888;
    margin-top: 14px;
    border-top: 0.5px solid #ddd;
    padding-top: 6px;
  }}
  @media print {{
    body {{ margin: 0; }}
    .recibo {{ border: none; margin: 0; width: 100%; }}
  }}
</style>
</head>
<body>
<div class="recibo">
  <div class="header">
    {logo_tag}
    <div class="pousada-info">
      <h2>Pousada Jaguaruana</h2>
      <p>
        Tv. Getúlio Vargas, 407 - Centro - Jaguaruana-CE<br>
        Tel: (88) 99906-2681 / 99906-2689<br>
        CNPJ: 05.275.909/0001-76
      </p>
    </div>
  </div>

  <div class="titulo">Recibo de Hospedagem</div>
  <div class="numero">Nº {numero_recibo:04d} &nbsp;·&nbsp; Emitido em {datetime.now().strftime("%d/%m/%Y")}</div>

  <div class="secao">
    <div class="secao-titulo">Dados do hóspede</div>
    <div class="linha"><span>Nome</span><span>{nome}</span></div>
    {"<div class='linha'><span>CPF</span><span>" + cpf + "</span></div>" if cpf else ""}
    {"<div class='linha'><span>Celular</span><span>" + celular + "</span></div>" if celular else ""}
  </div>

  <div class="secao">
    <div class="secao-titulo">Dados da hospedagem</div>
    <div class="linha"><span>Data</span><span>{data}</span></div>
    <div class="linha"><span>Pagamento</span><span>{pagamento}</span></div>
    <div class="obs-campo">
      <span class="obs-label">Observação</span>
      {observacao if observacao else "&nbsp;"}
    </div>
  </div>

  <div class="total-box">
    <span class="total-label">Total pago</span>
    <span class="total-valor">R$ {valor:,.2f}</span>
  </div>
  <div class="extenso">({extenso})</div>

  <div class="assinatura">
    <div class="assinatura-linha"></div>
    <p>Responsável pela pousada</p>
  </div>

  <div class="rodape">Documento emitido pela Pousada Jaguaruana · Jaguaruana-CE</div>
</div>
<script>window.onload = function() {{ window.print(); }}</script>
</body>
</html>"""
    return html

# ─── FECHAMENTO MENSAL AUTOMÁTICO ────────────────────────────────────────────

def verificar_fechamento_mensal():
    hoje = datetime.now()
    # Só executa no dia 1° do mês
    if hoje.day != 1:
        return

    # Mês anterior
    primeiro_mes_atual = hoje.replace(day=1)
    ultimo_mes_ant = primeiro_mes_atual - timedelta(days=1)
    mes_ant_str = ultimo_mes_ant.strftime("%m/%Y")
    dia1_str    = hoje.strftime("%d/%m/%Y")

    # Verificar se já foi feito o lançamento de saldo anterior para este mês
    chave = f"Saldo Anterior {mes_ant_str}"
    ja_feito = supabase.table("lancamentos").select("id").eq("local", chave).execute().data
    if ja_feito:
        return  # já transferiu, não duplica

    # Calcular saldo do mês anterior (todos os lançamentos daquele mês)
    fmt = "%d/%m/%Y"
    mes_ini = ultimo_mes_ant.replace(day=1).strftime(fmt)
    mes_fim = ultimo_mes_ant.strftime(fmt)

    todos = supabase.table("lancamentos").select("*").execute().data
    rec_ant  = 0.0
    desp_ant = 0.0
    saldo_ant_transfer = 0.0

    for r in todos:
        try:
            dt = datetime.strptime(r["data"], fmt)
        except Exception:
            continue
        dt_ini = datetime.strptime(mes_ini, fmt)
        dt_fim = datetime.strptime(mes_fim, fmt)
        # Incluir saldo anterior do próprio mês anterior (se houver)
        if r.get("local","").startswith("Saldo Anterior") and dt_ini <= dt <= dt_fim:
            if r["tipo"] == "Receita":
                saldo_ant_transfer += r["valor"]
            else:
                saldo_ant_transfer -= r["valor"]
        elif dt_ini <= dt <= dt_fim:
            if r["tipo"] == "Receita":
                rec_ant += r["valor"]
            elif r["tipo"] == "Despesa" and not r.get("local","").startswith("Saldo Anterior"):
                desp_ant += r["valor"]

    saldo_final = rec_ant - desp_ant + saldo_ant_transfer

    if saldo_final == 0:
        return  # nada a transferir

    if saldo_final > 0:
        supabase.table("lancamentos").insert({
            "data": dia1_str,
            "tipo": "Receita",
            "valor": round(saldo_final, 2),
            "local": chave,
            "sub_local": "Pousada",
            "descricao": f"Saldo transferido do mês {mes_ant_str}",
            "quarto": None,
        }).execute()
    else:
        supabase.table("lancamentos").insert({
            "data": dia1_str,
            "tipo": "Despesa",
            "valor": round(abs(saldo_final), 2),
            "local": chave,
            "sub_local": "Pousada",
            "descricao": f"Saldo negativo transferido do mês {mes_ant_str}",
        }).execute()

# ─── TEMAS / APARÊNCIA ────────────────────────────────────────────────────────

TEMAS = {
    "dark_profissional": {
        "nome": "Dark Profissional",
        "emoji": "🌑",
        "desc": "Azul elétrico + fundo escuro. Moderno, reduz cansaço visual.",
        "css": """
            [data-testid="stSidebar"] { background: #1a1a2e !important; }
            [data-testid="stSidebar"] * { color: #c0c0dd !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #378ADD !important; font-weight: 600; }
            .stButton>button { background: #378ADD; color: #fff; border: none; }
            .stButton>button:hover { background: #185FA5; }
            [data-testid="stAppViewContainer"] { background: #0f0f1a; }
            [data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2,[data-testid="stAppViewContainer"] h3 { color: #e0e0ff; }
            [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label { color: #a0a0cc; }
            [data-testid="stForm"] { background: #1a1a2e; border: 1px solid #2a2a4a; border-radius: 10px; padding: 16px; }
            [data-testid="stMetric"] { background: #1a1a2e; border-radius: 8px; padding: 12px; }
        """
    },
    "dark_esmeralda": {
        "nome": "Dark Esmeralda",
        "emoji": "🌿",
        "desc": "Verde esmeralda + fundo escuro. Sofisticado e único.",
        "css": """
            [data-testid="stSidebar"] { background: #0d1f1a !important; }
            [data-testid="stSidebar"] * { color: #7abfa8 !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #1D9E75 !important; font-weight: 600; }
            .stButton>button { background: #1D9E75; color: #fff; border: none; }
            .stButton>button:hover { background: #0F6E56; }
            [data-testid="stAppViewContainer"] { background: #0a0f0e; }
            [data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2,[data-testid="stAppViewContainer"] h3 { color: #d0ffe8; }
            [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label { color: #6aaa90; }
            [data-testid="stForm"] { background: #0d1f1a; border: 1px solid #1a3a30; border-radius: 10px; padding: 16px; }
            [data-testid="stMetric"] { background: #0d1f1a; border-radius: 8px; padding: 12px; }
        """
    },
    "dark_dourado": {
        "nome": "Dark Vinho & Dourado",
        "emoji": "✨",
        "desc": "Dourado + fundo escuro quente. Elegante e sofisticado.",
        "css": """
            [data-testid="stSidebar"] { background: #1f0f0f !important; }
            [data-testid="stSidebar"] * { color: #c09060 !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #EF9F27 !important; font-weight: 600; }
            .stButton>button { background: #BA7517; color: #fff; border: none; }
            .stButton>button:hover { background: #854F0B; }
            [data-testid="stAppViewContainer"] { background: #0f0a0a; }
            [data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2,[data-testid="stAppViewContainer"] h3 { color: #ffe8cc; }
            [data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] label { color: #a07050; }
            [data-testid="stForm"] { background: #1f0f0f; border: 1px solid #3a1a1a; border-radius: 10px; padding: 16px; }
            [data-testid="stMetric"] { background: #1f0f0f; border-radius: 8px; padding: 12px; }
        """
    },
    "claro_moderno": {
        "nome": "Claro Moderno",
        "emoji": "☀️",
        "desc": "Azul + fundo branco. Limpo e profissional.",
        "css": """
            [data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #e5e5ea; }
            [data-testid="stSidebar"] * { color: #444 !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #185FA5 !important; font-weight: 600; }
            .stButton>button { background: #185FA5; color: #fff; border: none; }
            .stButton>button:hover { background: #0C447C; }
            [data-testid="stAppViewContainer"] { background: #f5f5f7; }
            [data-testid="stMetric"] { background: #ffffff; border-radius: 8px; padding: 12px; border: 1px solid #e5e5ea; }
        """
    },
    "claro_rosa": {
        "nome": "Claro Rosê",
        "emoji": "🌸",
        "desc": "Rosa suave + branco. Delicado e acolhedor.",
        "css": """
            [data-testid="stSidebar"] { background: #fff0f5 !important; border-right: 1px solid #f4c0d1; }
            [data-testid="stSidebar"] * { color: #993556 !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #D4537E !important; font-weight: 600; }
            .stButton>button { background: #D4537E; color: #fff; border: none; }
            .stButton>button:hover { background: #993556; }
            [data-testid="stAppViewContainer"] { background: #fff8fb; }
            [data-testid="stMetric"] { background: #ffffff; border-radius: 8px; padding: 12px; border: 1px solid #f4c0d1; }
            [data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2 { color: #72243E; }
        """
    },
    "claro_verde": {
        "nome": "Claro Natural",
        "emoji": "🍃",
        "desc": "Verde natural + branco. Tranquilo e fresco.",
        "css": """
            [data-testid="stSidebar"] { background: #f0faf5 !important; border-right: 1px solid #9FE1CB; }
            [data-testid="stSidebar"] * { color: #0F6E56 !important; }
            [data-testid="stSidebarNav"] a[aria-selected="true"] span { color: #1D9E75 !important; font-weight: 600; }
            .stButton>button { background: #1D9E75; color: #fff; border: none; }
            .stButton>button:hover { background: #0F6E56; }
            [data-testid="stAppViewContainer"] { background: #f5fdf9; }
            [data-testid="stMetric"] { background: #ffffff; border-radius: 8px; padding: 12px; border: 1px solid #9FE1CB; }
            [data-testid="stAppViewContainer"] h1,[data-testid="stAppViewContainer"] h2 { color: #085041; }
        """
    },
}

def aplicar_tema():
    tema_id = st.session_state.get("tema_ativo", "dark_profissional")
    tema = TEMAS.get(tema_id, TEMAS["dark_profissional"])
    st.markdown(f"<style>{tema['css']}</style>", unsafe_allow_html=True)

def salvar_tema(tema_id):
    st.session_state["tema_ativo"] = tema_id
    try:
        existe = supabase.table("configuracoes").select("id").eq("chave", "tema").execute().data
        if existe:
            supabase.table("configuracoes").update({"valor": tema_id}).eq("chave", "tema").execute()
        else:
            supabase.table("configuracoes").insert({"chave": "tema", "valor": tema_id}).execute()
    except Exception:
        pass

def carregar_tema_salvo():
    if "tema_ativo" not in st.session_state:
        try:
            res = supabase.table("configuracoes").select("valor").eq("chave", "tema").execute().data
            if res:
                st.session_state["tema_ativo"] = res[0]["valor"]
            else:
                st.session_state["tema_ativo"] = "dark_profissional"
        except Exception:
            st.session_state["tema_ativo"] = "dark_profissional"

# ─── TELA EXTRATO ─────────────────────────────────────────────────────────────

def tela_extrato():
    st.title("📊 Extrato — Mês Atual")

    hoje = datetime.now()
    mes_atual_str = hoje.strftime("%m/%Y")
    fmt = "%d/%m/%Y"
    mes_ini = hoje.replace(day=1).strftime(fmt)
    mes_fim = hoje.strftime(fmt)
    dt_ini  = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    dt_fim  = hoje.replace(hour=23, minute=59, second=59, microsecond=0)

    # Buscar todos os lançamentos do mês atual
    todos = supabase.table("lancamentos").select("*").order("id", desc=True).execute().data
    lancamentos_mes = []
    for r in todos:
        try:
            dt = datetime.strptime(r["data"], fmt)
        except Exception:
            continue
        if dt_ini <= dt <= dt_fim:
            lancamentos_mes.append(r)

    # Separar saldo anterior dos demais
    saldo_anterior = 0.0
    lancamento_saldo_ant = None
    receitas_mes  = []
    despesas_mes  = []

    for r in lancamentos_mes:
        if r.get("local", "").startswith("Saldo Anterior"):
            if r["tipo"] == "Receita":
                saldo_anterior += r["valor"]
            else:
                saldo_anterior -= r["valor"]
            lancamento_saldo_ant = r
        elif r["tipo"] == "Receita":
            receitas_mes.append(r)
        else:
            despesas_mes.append(r)

    total_rec  = sum(r["valor"] for r in receitas_mes)
    total_desp = sum(r["valor"] for r in despesas_mes)
    saldo      = total_rec - total_desp + saldo_anterior

    # Cards
    col1, col2, col3 = st.columns(3)
    col1.metric("Receitas", f"R$ {total_rec:,.2f}")
    col2.metric("Despesas", f"R$ {total_desp:,.2f}")
    cor_saldo = "red" if saldo < 0 else "inherit"
    col3.markdown(
        f"<div style='font-size:14px;color:#888;margin-bottom:4px'>Saldo</div>"
        f"<div style='font-size:28px;font-weight:700;color:{cor_saldo}'>R$ {saldo:,.2f}</div>",
        unsafe_allow_html=True
    )

    st.divider()

    # Linha de saldo anterior destacada (se existir)
    if lancamento_saldo_ant:
        sinal = "+" if saldo_anterior >= 0 else ""
        cor_sa = "#28a745" if saldo_anterior >= 0 else "#dc3545"
        st.markdown(
            f"<div style='background:#f0f4ff;border-left:4px solid #1a1a2e;"
            f"padding:10px 16px;border-radius:4px;margin-bottom:8px;"
            f"display:flex;justify-content:space-between;align-items:center;'>"
            f"<span style='font-weight:600;color:#1a1a2e;'>📅 Saldo Anterior ({lancamento_saldo_ant['data']})</span>"
            f"<span style='font-weight:700;font-size:16px;color:{cor_sa}'>{sinal}R$ {saldo_anterior:,.2f}</span>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.subheader(f"Lançamentos de {mes_atual_str}")

    todos_mes = receitas_mes + despesas_mes
    todos_mes_ord = sorted(todos_mes, key=lambda r: r["id"], reverse=True)

    if not todos_mes_ord:
        st.info("Nenhum lançamento neste mês ainda.")
        return

    for row in todos_mes_ord:
        cor   = "🟢" if row["tipo"] == "Receita" else "🔴"
        texto = f"Hospedagem Q{row['quarto']}" if row["tipo"] == "Receita" else f"{row['local']} ({row['sub_local']})"
        obs   = f" — {row['descricao']}" if row.get("descricao") else ""
        col_data, col_tipo, col_valor, col_desc, col_acao = st.columns([1.2, 1, 1.2, 3, 0.5])
        col_data.caption(row["data"])
        col_tipo.write(f"{cor} {row['tipo']}")
        col_valor.write(f"**R$ {row['valor']:,.2f}**")
        col_desc.write(f"{texto}{obs}")
        if col_acao.button("🗑️", key=f"del_{row['id']}", help="Excluir"):
            supabase.table("lancamentos").delete().eq("id", row["id"]).execute()
            st.success("Registro excluído.")
            st.rerun()

# ─── TELA HOSPEDAGEM ──────────────────────────────────────────────────────────

def tela_hospedagem():
    st.title("🏨 Check-in / Receita")

    if "hospede_selecionado" not in st.session_state:
        st.session_state.hospede_selecionado = None
    if "mostrar_cadastro_rapido" not in st.session_state:
        st.session_state.mostrar_cadastro_rapido = False

    # Busca de hóspede
    st.subheader("🔍 Buscar hóspede")
    nome_busca = st.text_input("Digite o nome do hóspede", key="busca_hospede_hosp")

    if nome_busca and len(nome_busca) >= 2:
        resultados = buscar_hospede_por_nome(nome_busca)
        if resultados:
            opcoes = {f"{r['nome']} — CPF: {r.get('cpf','') or 'não informado'}": r for r in resultados}
            opcoes["+ Cadastrar novo hóspede"] = None
            escolha = st.selectbox("Selecione o hóspede", list(opcoes.keys()), key="sel_hospede")
            if escolha == "+ Cadastrar novo hóspede":
                st.session_state.hospede_selecionado = None
                st.session_state.mostrar_cadastro_rapido = True
            else:
                st.session_state.hospede_selecionado = opcoes[escolha]
                st.session_state.mostrar_cadastro_rapido = False
        else:
            st.warning("Nenhum hóspede encontrado.")
            if st.button("+ Cadastrar novo hóspede", key="btn_novo_hosp"):
                st.session_state.mostrar_cadastro_rapido = True
                st.session_state.hospede_selecionado = None

    # Cadastro rápido
    if st.session_state.mostrar_cadastro_rapido:
        st.divider()
        st.subheader("📋 Cadastrar novo hóspede")
        with st.form("form_cadastro_rapido", enter_to_submit=False):
            c1, c2 = st.columns(2)
            novo_nome   = c1.text_input("Nome completo *")
            novo_nasc   = c2.text_input("Data de nascimento", placeholder="DD/MM/AAAA")
            c3, c4 = st.columns(2)
            novo_rg     = c3.text_input("RG")
            novo_cpf    = c4.text_input("CPF / CNPJ", placeholder="000.000.000-00 ou 00.000.000/0000-00")
            c5, c6 = st.columns(2)
            novo_tel    = c5.text_input("Telefone fixo", placeholder="(00) 0000-0000")
            novo_cel    = c6.text_input("Celular", placeholder="(00) 00000-0000")
            salvar_novo = st.form_submit_button("✅ Salvar e usar este hóspede")
        if salvar_novo:
            if not novo_nome:
                st.warning("Informe o nome do hóspede.")
            elif novo_cpf and not validar_cpf_cnpj(novo_cpf):
                st.error("CPF/CNPJ inválido. Verifique os números digitados.")
            else:
                cpf_fmt = formatar_cpf_cnpj(novo_cpf) if novo_cpf else ""
                tel_fmt = formatar_telefone(novo_tel) if novo_tel else ""
                cel_fmt = formatar_telefone(novo_cel) if novo_cel else ""
                nasc_fmt = formatar_data(novo_nasc) if novo_nasc else ""
                h = salvar_hospede({"nome": novo_nome, "data_nascimento": nasc_fmt,
                                    "rg": novo_rg, "cpf": cpf_fmt,
                                    "telefone": tel_fmt, "celular": cel_fmt})
                if h:
                    st.session_state.hospede_selecionado = h
                    st.session_state.mostrar_cadastro_rapido = False
                    st.success(f"Hóspede '{novo_nome}' cadastrado!")
                    st.rerun()

    # Dados do hóspede selecionado
    if st.session_state.hospede_selecionado:
        h = st.session_state.hospede_selecionado
        st.success(f"✅ Hóspede: **{h['nome']}** | CPF: {h.get('cpf') or '—'} | Cel: {h.get('celular') or '—'}")

    st.divider()
    st.subheader("🏨 Dados da hospedagem")

    # Mapa de hóspedes padrão por tipo
    _qtd_por_tipo = {"Individual": 1, "Duplo": 2, "Triplo": 3, "Quádruplo": 4, "Aberto": 1}

    # Quarto e Tipo ficam fora do form para permitir atualização dinâmica dos hóspedes
    col3, col4 = st.columns(2)
    quarto_ext = col3.text_input("Quarto", placeholder="Ex: 3", key="quarto_ext")
    tipo_quarto = col4.selectbox(
        "Tipo",
        ["Individual", "Duplo", "Triplo", "Quádruplo", "Aberto"],
        key="tipo_quarto_sel"
    )
    qtd_default = _qtd_por_tipo.get(tipo_quarto, 1)

    with st.form("form_hospedagem", clear_on_submit=True):
        col1, col2 = st.columns(2)
        data        = col1.text_input("Data", value=datetime.now().strftime("%d/%m/%Y"))
        valor_texto = col2.text_input("Valor total R$", placeholder="0,00")

        col5, col6 = st.columns(2)
        pagamento   = col5.selectbox("Forma de pagamento", ["Dinheiro/Pix", "Cartão"])
        hospedes    = col6.number_input("Hóspedes", min_value=1, max_value=20, value=qtd_default)

        observacao  = st.text_input("Observação (opcional)", placeholder="Ex: café da manhã incluso, pet friendly...")

        operadora  = None
        modalidade = None
        if pagamento == "Cartão":
            st.markdown("**Dados do cartão**")
            col7, col8 = st.columns(2)
            operadora  = col7.selectbox("Operadora", obter_operadoras())
            modalidade = col8.selectbox("Modalidade", ["Crédito", "Débito"])

        salvar = st.form_submit_button("✅ Salvar receita", use_container_width=True)

    if salvar:
        try:
            valor = float(valor_texto.replace(",", "."))
            quarto = st.session_state.get("quarto_ext", "")
            if not quarto:
                st.warning("Informe o número do quarto.")
                return

            hospede_id = st.session_state.hospede_selecionado["id"] if st.session_state.hospede_selecionado else None

            tipo_quarto_val = st.session_state.get("tipo_quarto_sel", "Individual")
            res = supabase.table("lancamentos").insert({
                "data": data, "tipo": "Receita", "valor": valor,
                "local": "Hospedagem", "sub_local": "Pousada",
                "quarto": quarto, "tipo_quarto": tipo_quarto_val,
                "hospedes": int(hospedes), "modalidade": pagamento,
                "operadora": operadora if pagamento == "Cartão" else None,
                "hospede_id": hospede_id,
                "observacao": observacao
            }).execute()

            if pagamento == "Cartão" and operadora:
                r2 = supabase.table("operadoras").select("taxa_debito, taxa_credito").eq("nome", operadora).execute()
                if r2.data:
                    taxa_perc = r2.data[0]["taxa_debito"] if modalidade == "Débito" else r2.data[0]["taxa_credito"]
                    if taxa_perc > 0:
                        v_taxa = valor * (taxa_perc / 100)
                        supabase.table("lancamentos").insert({
                            "data": data, "tipo": "Despesa", "valor": v_taxa,
                            "local": "TAXA CARTÃO", "sub_local": "Pousada",
                            "descricao": f"Taxa {taxa_perc}% - {operadora} (Qrt {quarto})"
                        }).execute()

            st.success("✅ Receita registrada com sucesso!")
            st.session_state.hospede_selecionado = None

        except ValueError:
            st.error("Valor inválido. Use apenas números, ex: 320,00")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# ─── TELA DESPESAS ────────────────────────────────────────────────────────────

def tela_despesas():
    st.title("💸 Lançar despesa")
    categorias = obter_categorias()
    if not categorias:
        st.warning("Nenhuma categoria cadastrada. Acesse **Configurações** para adicionar.")
        return
    with st.form("form_despesa", clear_on_submit=True):
        categoria_sel = st.selectbox("Categoria", categorias)
        nome_cat, destino = extrair_destino(categoria_sel)
        cor_destino = "🟡" if destino == "Casa" else "🔵"
        st.caption(f"{cor_destino} Destino: **{destino}**")
        col1, col2 = st.columns(2)
        data        = col1.text_input("Data", value=datetime.now().strftime("%d/%m/%Y"))
        valor_texto = col2.text_input("Valor R$", placeholder="0,00")
        descricao = st.text_input("Descrição / Obs", placeholder="Ex: Ref. mês maio")
        salvar = st.form_submit_button("✅ Salvar despesa", use_container_width=True)
    if salvar:
        try:
            valor = float(valor_texto.replace(",", "."))
            supabase.table("lancamentos").insert({
                "data": data, "tipo": "Despesa", "valor": valor,
                "local": nome_cat, "sub_local": destino, "descricao": descricao
            }).execute()
            st.success("✅ Despesa registrada com sucesso!")
            st.rerun()
        except ValueError:
            st.error("Valor inválido. Use apenas números, ex: 85,00")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# ─── TELA MAPA ────────────────────────────────────────────────────────────────

def tela_mapa():
    st.title("🗺️ Mapa do dinheiro")
    hoje = datetime.now()
    mes_str = hoje.strftime("%m/%Y")
    todos = supabase.table("lancamentos").select("*").execute().data
    dados = [r for r in todos if r.get("data", "").endswith(mes_str)]
    total_rec     = sum(r["valor"] for r in dados if r["tipo"] == "Receita")
    gasto_casa    = sum(r["valor"] for r in dados if r["tipo"] == "Despesa" and r["sub_local"] == "Casa")
    gasto_pousada = sum(r["valor"] for r in dados if r["tipo"] == "Despesa" and r["sub_local"] == "Pousada")
    hosp_total    = sum(r["hospedes"] or 0 for r in dados if r["tipo"] == "Receita")
    st.metric("Total de hóspedes", int(hosp_total))
    col1, col2, col3 = st.columns(3)
    col1.metric("Entradas",      f"R$ {total_rec:,.2f}")
    col2.metric("Gasto casa",    f"R$ {gasto_casa:,.2f}")
    col3.metric("Gasto pousada", f"R$ {gasto_pousada:,.2f}")
    st.divider()
    col_quartos, col_casa, col_pousada = st.columns(3)
    with col_quartos:
        st.markdown("**🟢 Receita por quarto**")
        receitas = [r for r in dados if r["tipo"] == "Receita"]
        quartos = {}
        for r in receitas:
            q = r.get("quarto") or "?"
            quartos[q] = quartos.get(q, 0) + r["valor"]
        for q, v in sorted(quartos.items()):
            st.write(f"Quarto {q} — R$ {v:,.2f}")
    with col_casa:
        st.markdown("**🟡 Contas da casa**")
        casa = {}
        for r in dados:
            if r["tipo"] == "Despesa" and r["sub_local"] == "Casa":
                casa[r["local"]] = casa.get(r["local"], 0) + r["valor"]
        for local, v in casa.items():
            st.write(f"{local} — R$ {v:,.2f}")
    with col_pousada:
        st.markdown("**🔵 Contas da pousada**")
        pousada = {}
        for r in dados:
            if r["tipo"] == "Despesa" and r["sub_local"] == "Pousada":
                pousada[r["local"]] = pousada.get(r["local"], 0) + r["valor"]
        for local, v in pousada.items():
            st.write(f"{local} — R$ {v:,.2f}")

# ─── TELA RELATÓRIOS ──────────────────────────────────────────────────────────

def tela_relatorios():
    st.title("📑 Relatórios")
    col1, col2, col3, col4 = st.columns(4)
    data_ini  = col1.text_input("Data inicial", value=(datetime.now() - timedelta(days=30)).strftime("%d/%m/%Y"))
    data_fim  = col2.text_input("Data final",   value=datetime.now().strftime("%d/%m/%Y"))
    destino_f = col3.selectbox("Destino", ["Ambos", "Pousada", "Casa"])
    tipo_f    = col4.selectbox("Tipo", ["Tudo", "Apenas Receitas", "Apenas Despesas"])
    quarto_f  = st.text_input("Filtrar por quarto (opcional)", placeholder="Ex: 3")
    if st.button("🔍 Gerar relatório", use_container_width=True):
        fmt = "%d/%m/%Y"
        try:
            dt_ini = datetime.strptime(data_ini, fmt)
            dt_fim = datetime.strptime(data_fim, fmt)
        except ValueError:
            st.error("Formato de data inválido. Use DD/MM/AAAA.")
            return
        todos = supabase.table("lancamentos").select("*").order("id").execute().data
        filtrados = []
        for item in todos:
            try:
                dt_item = datetime.strptime(item["data"], fmt)
                if not (dt_ini <= dt_item <= dt_fim): continue
                if destino_f != "Ambos" and item.get("sub_local") != destino_f: continue
                if tipo_f == "Apenas Receitas" and item["tipo"] != "Receita": continue
                if tipo_f == "Apenas Despesas" and item["tipo"] != "Despesa": continue
                if quarto_f:
                    if item["tipo"] == "Receita" and str(item.get("quarto")) != quarto_f: continue
                    elif item["tipo"] == "Despesa": continue
                filtrados.append(item)
            except Exception:
                continue
        if not filtrados:
            st.warning("Nenhum registro encontrado.")
            return
        t_rec  = sum(i["valor"] for i in filtrados if i["tipo"] == "Receita")
        t_desp = sum(i["valor"] for i in filtrados if i["tipo"] == "Despesa")
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Receitas", f"R$ {t_rec:,.2f}")
        col_b.metric("Despesas", f"R$ {t_desp:,.2f}")
        col_c.metric("Saldo",    f"R$ {t_rec - t_desp:,.2f}")
        st.divider()
        for item in filtrados:
            cor   = "🟢" if item["tipo"] == "Receita" else "🔴"
            texto = f"Qrt {item.get('quarto')}" if item["tipo"] == "Receita" else item["local"]
            obs   = f" — {item['descricao']}" if item.get("descricao") else ""
            st.write(f"{cor} `{item['data']}` R$ {item['valor']:,.2f} · {texto}{obs}")

        # ── Exportar relatório ──────────────────────────────────────────────
        st.divider()
        st.subheader("📤 Exportar relatório")

        linhas_html = ""
        for item in filtrados:
            cor_badge = "#28a745" if item["tipo"] == "Receita" else "#dc3545"
            texto_item = f"Qrt {item.get('quarto')}" if item["tipo"] == "Receita" else item["local"]
            obs_item   = f" — {item.get('descricao','')}" if item.get("descricao") else ""
            linhas_html += f"""
            <tr>
              <td>{item['data']}</td>
              <td><span style="background:{cor_badge};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{item['tipo']}</span></td>
              <td style="text-align:right">R$ {item['valor']:,.2f}</td>
              <td>{texto_item}{obs_item}</td>
            </tr>"""

        html_rel = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Relatório Pousada Jaguaruana</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 20px; color: #333; }}
  h2 {{ color: #1a1a2e; }}
  .filtros {{ font-size: 12px; color: #666; margin-bottom: 16px; }}
  .resumo {{ display: flex; gap: 24px; margin-bottom: 20px; }}
  .card {{ background: #f5f5f5; border-radius: 8px; padding: 12px 20px; min-width: 140px; }}
  .card .label {{ font-size: 11px; color: #888; text-transform: uppercase; }}
  .card .valor {{ font-size: 18px; font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th {{ background: #1a1a2e; color: #fff; padding: 8px 10px; text-align: left; font-size: 12px; }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; font-size: 13px; }}
  tr:hover {{ background: #f9f9f9; }}
  .rodape {{ margin-top: 20px; font-size: 11px; color: #aaa; text-align: center; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h2>📑 Relatório — Pousada Jaguaruana</h2>
  <div class="filtros">
    Período: {data_ini} a {data_fim} &nbsp;|&nbsp;
    Destino: {destino_f} &nbsp;|&nbsp;
    Tipo: {tipo_f}
    {f" &nbsp;|&nbsp; Quarto: {quarto_f}" if quarto_f else ""}
  </div>
  <div class="resumo">
    <div class="card"><div class="label">Receitas</div><div class="valor" style="color:#28a745">R$ {t_rec:,.2f}</div></div>
    <div class="card"><div class="label">Despesas</div><div class="valor" style="color:#dc3545">R$ {t_desp:,.2f}</div></div>
    <div class="card"><div class="label">Saldo</div><div class="valor">R$ {t_rec - t_desp:,.2f}</div></div>
  </div>
  <table>
    <thead><tr><th>Data</th><th>Tipo</th><th>Valor</th><th>Descrição</th></tr></thead>
    <tbody>{linhas_html}</tbody>
  </table>
  <div class="rodape">Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")} · Pousada Jaguaruana · Jaguaruana-CE</div>
  <script>
    // Remover botões ao imprimir
  </script>
</body>
</html>"""

        col_exp1, col_exp2 = st.columns(2)
        with col_exp1:
            b64_html = base64.b64encode(html_rel.encode("utf-8")).decode()
            nome_arq = f"relatorio_{data_ini.replace('/','')}__{data_fim.replace('/','')}.html"
            st.download_button(
                label="⬇️ Exportar como HTML",
                data=html_rel.encode("utf-8"),
                file_name=nome_arq,
                mime="text/html",
                use_container_width=True
            )
        with col_exp2:
            import streamlit.components.v1 as components
            b64_rel = base64.b64encode(html_rel.encode("utf-8")).decode("utf-8")
            components.html(f'''
                <script>
                function abrirRelatorio() {{
                    var b64 = "{b64_rel}";
                    var bin = atob(b64);
                    var bytes = new Uint8Array(bin.length);
                    for (var i = 0; i < bin.length; i++) {{ bytes[i] = bin.charCodeAt(i); }}
                    var blob = new Blob([bytes], {{type: "text/html; charset=utf-8"}});
                    var url = URL.createObjectURL(blob);
                    window.open(url, "_blank");
                }}
                </script>
                <button onclick="abrirRelatorio()" style="
                    width:100%;padding:9px 0;cursor:pointer;
                    background:#1a1a2e;color:#fff;border:none;border-radius:6px;
                    font-size:14px;font-weight:600;">
                    🖨️ Visualizar / Imprimir (PDF)
                </button>
            ''', height=55)

# ─── TELA CADASTRO DE HÓSPEDES ────────────────────────────────────────────────

def tela_cadastro_hospedes():
    st.title("👥 Cadastro de Hóspedes")

    # Limpar recibo somente quando vier de outra tela (não em rerun interno)
    if st.session_state.get("_pagina_anterior") != "cadastro_hospedes":
        st.session_state["recibo_aberto"] = False
        if "recibo_html" in st.session_state:
            del st.session_state["recibo_html"]
    st.session_state["_pagina_anterior"] = "cadastro_hospedes"

    aba_lista, aba_novo = st.tabs(["📋 Lista de hóspedes", "➕ Novo hóspede"])

    with aba_novo:
        with st.form("form_novo_hospede", clear_on_submit=True, enter_to_submit=False):
            c1, c2 = st.columns(2)
            nome   = c1.text_input("Nome completo *")
            nasc   = c2.text_input("Data de nascimento", placeholder="DD/MM/AAAA")
            c3, c4 = st.columns(2)
            rg     = c3.text_input("RG")
            cpf    = c4.text_input("CPF / CNPJ", placeholder="000.000.000-00 ou 00.000.000/0000-00")
            c5, c6 = st.columns(2)
            tel    = c5.text_input("Telefone fixo", placeholder="(00) 0000-0000")
            cel    = c6.text_input("Celular", placeholder="(00) 00000-0000")
            salvar = st.form_submit_button("✅ Cadastrar hóspede", use_container_width=True)
        if salvar:
            if not nome:
                st.warning("Informe o nome do hóspede.")
            elif cpf and not validar_cpf_cnpj(cpf):
                st.error("CPF/CNPJ inválido. Verifique os números digitados.")
            else:
                cpf_fmt = formatar_cpf_cnpj(cpf) if cpf else ""
                tel_fmt = formatar_telefone(tel) if tel else ""
                cel_fmt = formatar_telefone(cel) if cel else ""
                nasc_fmt = formatar_data(nasc) if nasc else ""
                h = salvar_hospede({"nome": nome, "data_nascimento": nasc_fmt,
                                    "rg": rg, "cpf": cpf_fmt,
                                    "telefone": tel_fmt, "celular": cel_fmt})
                if h:
                    st.success(f"Hóspede '{nome}' cadastrado com sucesso!")

    with aba_lista:
        busca = st.text_input("🔍 Buscar por nome", placeholder="Digite o nome...")
        todos = buscar_todos_hospedes()
        if busca:
            todos = [h for h in todos if busca.lower() in h["nome"].lower()]

        if not todos:
            st.info("Nenhum hóspede encontrado.")
            return

        st.markdown(f"**{len(todos)} hóspede(s) encontrado(s)**")
        st.divider()

        for h in todos:
            with st.expander(f"👤 {h['nome']} — CPF: {h.get('cpf') or 'não informado'}"):

                # Editar ficha
                col_edit, col_del = st.columns([5, 1])
                with col_edit:
                    with st.form(f"form_edit_{h['id']}"):
                        st.markdown("**Editar ficha**")
                        c1, c2 = st.columns(2)
                        e_nome = c1.text_input("Nome", value=h["nome"], key=f"nome_{h['id']}")
                        e_nasc = c2.text_input("Nascimento", value=h.get("data_nascimento") or "", key=f"nasc_{h['id']}")
                        c3, c4 = st.columns(2)
                        e_rg   = c3.text_input("RG",  value=h.get("rg") or "", key=f"rg_{h['id']}")
                        e_cpf  = c4.text_input("CPF / CNPJ", value=h.get("cpf") or "", placeholder="000.000.000-00", key=f"cpf_{h['id']}")
                        c5, c6 = st.columns(2)
                        e_tel  = c5.text_input("Telefone", value=h.get("telefone") or "", placeholder="(00) 0000-0000", key=f"tel_{h['id']}")
                        e_cel  = c6.text_input("Celular",  value=h.get("celular") or "", placeholder="(00) 00000-0000", key=f"cel_{h['id']}")
                        salvar_edit = st.form_submit_button("💾 Salvar alterações")
                    if salvar_edit:
                        if e_cpf and not validar_cpf_cnpj(e_cpf):
                            st.error("CPF/CNPJ inválido. Verifique os números digitados.")
                        else:
                            cpf_fmt = formatar_cpf_cnpj(e_cpf) if e_cpf else ""
                            tel_fmt = formatar_telefone(e_tel) if e_tel else ""
                            cel_fmt = formatar_telefone(e_cel) if e_cel else ""
                            nasc_fmt = formatar_data(e_nasc) if e_nasc else ""
                            supabase.table("hospedes").update({
                                "nome": e_nome, "data_nascimento": nasc_fmt,
                                "rg": e_rg, "cpf": cpf_fmt,
                                "telefone": tel_fmt, "celular": cel_fmt
                            }).eq("id", h["id"]).execute()
                            st.success("Ficha atualizada!")
                            st.rerun()

                with col_del:
                    st.markdown("&nbsp;")
                    if st.button("🗑️ Excluir", key=f"del_h_{h['id']}"):
                        supabase.table("hospedes").delete().eq("id", h["id"]).execute()
                        st.success("Hóspede excluído.")
                        st.rerun()

                # Histórico de hospedagens
                st.divider()
                st.markdown("**📅 Histórico de hospedagens**")
                hospedagens = buscar_hospedagens_do_hospede(h["id"])

                if not hospedagens:
                    st.caption("Nenhuma hospedagem registrada para este hóspede.")
                else:
                    for i, lanc in enumerate(hospedagens):
                        ultima = " 🔹 *última*" if i == 0 else ""
                        col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns([1.2, 1, 1.2, 2, 1.5])
                        col_h1.caption(lanc["data"])
                        col_h2.write(f"Qrt {lanc.get('quarto','?')}")
                        col_h3.write(f"R$ {lanc['valor']:,.2f}")
                        col_h4.caption(lanc.get("observacao") or "—")

                        # Editar observação + gerar recibo
                        with col_h5:
                            with st.popover(f"⚙️ Ações{ultima}"):
                                st.markdown(f"**Hospedagem de {lanc['data']}**")
                                nova_obs = st.text_input("Observação", value=lanc.get("observacao") or "",
                                                         key=f"obs_{lanc['id']}")
                                if st.button("💾 Salvar obs.", key=f"sobs_{lanc['id']}"):
                                    supabase.table("lancamentos").update({"observacao": nova_obs}).eq("id", lanc["id"]).execute()
                                    st.success("Observação salva!")
                                    st.rerun()

                                st.divider()
                                if st.button("🧾 Gerar recibo", key=f"rec_{lanc['id']}"):
                                    lanc_atualizado = supabase.table("lancamentos").select("*").eq("id", lanc["id"]).execute().data[0]
                                    html_recibo = gerar_recibo_html(h, lanc_atualizado, lanc["id"])
                                    st.session_state["recibo_html"] = html_recibo
                                    st.session_state["recibo_aberto"] = True
                                    st.rerun()

        if st.session_state.get("recibo_aberto") and st.session_state.get("recibo_html"):
            import streamlit.components.v1 as components
            st.divider()
            st.subheader("🧾 Recibo gerado")
            st.caption("Use Ctrl+P / Cmd+P no navegador para imprimir, ou salve como PDF pela caixa de impressão.")
            components.html(st.session_state["recibo_html"], height=650, scrolling=True)
            if st.button("✖️ Fechar recibo", key="fechar_recibo_cad"):
                del st.session_state["recibo_html"]
                st.session_state["recibo_aberto"] = False
                st.rerun()

# ─── TELA CONFIGURAÇÕES ───────────────────────────────────────────────────────

def tela_configuracoes():
    st.title("⚙️ Configurações")
    aba_cartoes, aba_categorias, aba_backup, aba_temas = st.tabs(["Cartões / Máquinas", "Categorias de gasto", "💾 Backup", "🎨 Temas"])
    with aba_cartoes:
        with st.form("form_operadora", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            nome_op   = col1.text_input("Nome da operadora", placeholder="Ex: Cielo")
            taxa_deb  = col2.number_input("Taxa débito (%)",  min_value=0.0, max_value=20.0, step=0.1, format="%.2f")
            taxa_cred = col3.number_input("Taxa crédito (%)", min_value=0.0, max_value=20.0, step=0.1, format="%.2f")
            add_op = st.form_submit_button("Adicionar operadora")
        if add_op and nome_op:
            try:
                supabase.table("operadoras").upsert({"nome": nome_op, "taxa_debito": taxa_deb, "taxa_credito": taxa_cred}).execute()
                st.success(f"Operadora '{nome_op}' salva!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
        st.subheader("Operadoras cadastradas")
        ops = supabase.table("operadoras").select("*").execute().data
        for op in ops:
            col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 0.5])
            col1.write(op["nome"])
            col2.caption(f"Débito: {op['taxa_debito']}%")
            col3.caption(f"Crédito: {op['taxa_credito']}%")
            if col4.button("🗑️", key=f"del_op_{op['id']}"):
                supabase.table("operadoras").delete().eq("id", op["id"]).execute()
                st.rerun()
    with aba_categorias:
        with st.form("form_categoria", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nome_cat = col1.text_input("Nome da categoria", placeholder="Ex: Energia elétrica")
            destino  = col2.selectbox("Destino", ["Pousada", "Casa"])
            add_cat = st.form_submit_button("Adicionar categoria")
        if add_cat and nome_cat:
            try:
                supabase.table("categorias_despesa").insert({"nome": nome_cat, "destino": destino}).execute()
                st.success(f"Categoria '{nome_cat}' adicionada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")
        st.subheader("Categorias cadastradas")
        cats = supabase.table("categorias_despesa").select("*").order("destino").execute().data
        for cat in cats:
            col1, col2, col3 = st.columns([3, 1.5, 0.5])
            col1.write(cat["nome"])
            col2.caption(cat["destino"])
            if col3.button("🗑️", key=f"del_cat_{cat['id']}"):
                supabase.table("categorias_despesa").delete().eq("id", cat["id"]).execute()
                st.rerun()

    with aba_backup:
        st.subheader("💾 Backup geral dos dados")
        st.caption("Baixa todos os lançamentos e hóspedes cadastrados até o momento em um arquivo Excel.")

        if st.button("📥 Gerar backup agora", use_container_width=True, type="primary"):
            try:
                import io, csv

                # Buscar dados
                lancamentos = supabase.table("lancamentos").select("*").order("id").execute().data
                hospedes    = supabase.table("hospedes").select("*").order("nome").execute().data

                # ── CSV Lançamentos ──
                buf_lanc = io.StringIO()
                writer = csv.writer(buf_lanc)
                writer.writerow(["ID", "Data", "Tipo", "Valor (R$)", "Local", "Sub-local",
                                  "Quarto", "Tipo Quarto", "Hospedes", "Modalidade",
                                  "Operadora", "Descricao", "Observacao", "Hospede ID"])
                for r in lancamentos:
                    writer.writerow([
                        r.get("id"), r.get("data"), r.get("tipo"),
                        r.get("valor"), r.get("local"), r.get("sub_local"),
                        r.get("quarto"), r.get("tipo_quarto"), r.get("hospedes"),
                        r.get("modalidade"), r.get("operadora"),
                        r.get("descricao"), r.get("observacao"), r.get("hospede_id")
                    ])

                # ── CSV Hóspedes ──
                buf_hosp = io.StringIO()
                writer2 = csv.writer(buf_hosp)
                writer2.writerow(["ID", "Nome", "Data Nascimento", "RG", "CPF/CNPJ", "Telefone", "Celular"])
                for h in hospedes:
                    writer2.writerow([
                        h.get("id"), h.get("nome"), h.get("data_nascimento"),
                        h.get("rg"), h.get("cpf"), h.get("telefone"), h.get("celular")
                    ])

                agora = datetime.now().strftime('%d%m%Y_%H%M')
                st.success(f"✅ Backup gerado com {len(lancamentos)} lançamentos e {len(hospedes)} hóspedes.")

                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    st.download_button(
                        label="⬇️ Baixar Lançamentos (CSV)",
                        data=buf_lanc.getvalue().encode("utf-8-sig"),
                        file_name=f"lancamentos_{agora}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col_b2:
                    st.download_button(
                        label="⬇️ Baixar Hóspedes (CSV)",
                        data=buf_hosp.getvalue().encode("utf-8-sig"),
                        file_name=f"hospedes_{agora}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

            except Exception as e:
                st.error(f"Erro ao gerar backup: {e}")

        st.divider()
        st.subheader("📤 Restaurar backup")
        st.warning("⚠️ A restauração **adiciona** os registros do arquivo ao banco. Não apaga dados existentes. Use apenas se perdeu registros.")

        tipo_restore = st.radio("O que deseja restaurar?",
                                ["Lançamentos", "Hóspedes"], horizontal=True,
                                key="tipo_restore")

        arquivo = st.file_uploader(
            f"Selecione o arquivo CSV de {tipo_restore}",
            type=["csv"], key="arquivo_restore"
        )

        if arquivo:
            import io, csv as csvlib
            conteudo = arquivo.read().decode("utf-8-sig")
            reader = list(csvlib.DictReader(io.StringIO(conteudo)))
            st.info(f"📄 Arquivo lido: **{len(reader)} registros** encontrados.")

            if "confirmar_restore" not in st.session_state:
                st.session_state["confirmar_restore"] = False

            if not st.session_state["confirmar_restore"]:
                if st.button("🔄 Iniciar restauração", type="primary", use_container_width=True):
                    st.session_state["confirmar_restore"] = True
                    st.rerun()
            else:
                st.error("⚠️ **Confirma a restauração?** Isso vai inserir os registros no banco de dados.")
                col_sim, col_nao = st.columns(2)
                with col_nao:
                    if st.button("❌ Cancelar", use_container_width=True):
                        st.session_state["confirmar_restore"] = False
                        st.rerun()
                with col_sim:
                    if st.button("✅ Sim, restaurar", type="primary", use_container_width=True):
                        try:
                            inseridos = 0
                            erros = 0

                            if tipo_restore == "Lançamentos":
                                for row in reader:
                                    try:
                                        dados = {
                                            "data":        row.get("Data") or None,
                                            "tipo":        row.get("Tipo") or None,
                                            "valor":       float(row["Valor (R$)"]) if row.get("Valor (R$)") else 0,
                                            "local":       row.get("Local") or None,
                                            "sub_local":   row.get("Sub-local") or None,
                                            "quarto":      row.get("Quarto") or None,
                                            "tipo_quarto": row.get("Tipo Quarto") or None,
                                            "hospedes":    int(row["Hospedes"]) if row.get("Hospedes") else None,
                                            "modalidade":  row.get("Modalidade") or None,
                                            "operadora":   row.get("Operadora") or None,
                                            "descricao":   row.get("Descricao") or None,
                                            "observacao":  row.get("Observacao") or None,
                                            "hospede_id":  int(row["Hospede ID"]) if row.get("Hospede ID") else None,
                                        }
                                        supabase.table("lancamentos").insert(dados).execute()
                                        inseridos += 1
                                    except Exception:
                                        erros += 1

                            else:  # Hóspedes
                                for row in reader:
                                    try:
                                        dados = {
                                            "nome":             row.get("Nome") or None,
                                            "data_nascimento":  row.get("Data Nascimento") or None,
                                            "rg":               row.get("RG") or None,
                                            "cpf":              row.get("CPF/CNPJ") or None,
                                            "telefone":         row.get("Telefone") or None,
                                            "celular":          row.get("Celular") or None,
                                        }
                                        supabase.table("hospedes").insert(dados).execute()
                                        inseridos += 1
                                    except Exception:
                                        erros += 1

                            st.session_state["confirmar_restore"] = False
                            if inseridos > 0:
                                st.success(f"✅ Restauração concluída! {inseridos} registro(s) importado(s)." +
                                           (f" {erros} erro(s) ignorado(s)." if erros else ""))
                            else:
                                st.error("Nenhum registro foi importado. Verifique o arquivo.")
                        except Exception as e:
                            st.error(f"Erro na restauração: {e}")

    with aba_temas:
        st.subheader("🎨 Aparência do sistema")
        st.caption("Clique em um tema para aplicar imediatamente. A escolha fica salva.")

        tema_atual = st.session_state.get("tema_ativo", "dark_profissional")

        cols = st.columns(3)
        for idx, (tid, t) in enumerate(TEMAS.items()):
            col = cols[idx % 3]
            with col:
                ativo = tema_atual == tid
                borda = "3px solid #378ADD" if ativo else "1px solid #ddd"
                badge = " ✓ Ativo" if ativo else ""
                st.markdown(
                    f"""<div style='border:{borda};border-radius:10px;padding:14px 12px;
                        margin-bottom:8px;background:var(--color-background-secondary);'>
                        <div style='font-size:22px;'>{t['emoji']}</div>
                        <div style='font-weight:600;font-size:14px;color:var(--color-text-primary);
                             margin:4px 0 2px;'>{t['nome']}{badge}</div>
                        <div style='font-size:12px;color:var(--color-text-secondary);'>{t['desc']}</div>
                    </div>""",
                    unsafe_allow_html=True
                )
                if not ativo:
                    if st.button(f"Aplicar", key=f"tema_{tid}", use_container_width=True):
                        salvar_tema(tid)
                        st.success(f"Tema '{t['nome']}' aplicado!")
                        st.rerun()
                else:
                    st.markdown(
                        "<div style='text-align:center;font-size:12px;color:#378ADD;"
                        "padding:4px;'>Tema atual</div>",
                        unsafe_allow_html=True
                    )

# ─── NAVEGAÇÃO PRINCIPAL ──────────────────────────────────────────────────────

# ─── TELA DE LOGIN ───────────────────────────────────────────────────────────

def tela_login():
    # Carregar logo como base64
    logo_html = ""
    try:
        import os
        if os.path.exists("Pousada_Jaguaruana.png"):
            with open("Pousada_Jaguaruana.png", "rb") as f:
                logo_b64 = base64.b64encode(f.read()).decode()
            logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="max-width:200px;margin-bottom:16px;">'
        else:
            logo_html = '<div style="font-size:22px;font-weight:700;color:#1a1a2e;margin-bottom:8px;">🏨 Pousada Jaguaruana</div>'
    except Exception:
        logo_html = '<div style="font-size:22px;font-weight:700;color:#1a1a2e;margin-bottom:8px;">🏨 Pousada Jaguaruana</div>'

    st.markdown(f"""
        <style>
        .login-box {{
            max-width: 380px;
            margin: 80px auto 0;
            padding: 40px;
            background: #fff;
            border-radius: 12px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.10);
            text-align: center;
        }}
        .login-sub {{ font-size: 14px; color: #888; margin-bottom: 28px; }}
        </style>
        <div class="login-box">
            {logo_html}
            <div class="login-sub">Digite a senha para acessar o sistema</div>
        </div>
    """, unsafe_allow_html=True)

    col_c, col_m, col_c2 = st.columns([1, 1.5, 1])
    with col_m:
        senha = st.text_input("Senha", type="password", placeholder="••••••••",
                              key="input_senha", label_visibility="collapsed")
        entrar = st.button("Entrar", use_container_width=True)

        if entrar or (senha and st.session_state.get("_tentou_login")):
            st.session_state["_tentou_login"] = True
            senha_correta = st.secrets.get("APP_PASSWORD", "pousada2024")
            if senha == senha_correta:
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("Senha incorreta. Tente novamente.")

def main():
    if not st.session_state.get("autenticado"):
        tela_login()
        return

    # Carregar e aplicar tema salvo
    carregar_tema_salvo()
    aplicar_tema()

    # Verificar fechamento mensal automático ao abrir o sistema
    verificar_fechamento_mensal()

    st.sidebar.image("Pousada_Jaguaruana.png", use_container_width=True)
    tema_atual = st.session_state.get("tema_ativo", "dark_profissional")
    blend = "screen" if tema_atual.startswith("dark") else "multiply"
    st.markdown(f"""
        <style>
        [data-testid="stSidebar"] img {{
            background: transparent !important;
            mix-blend-mode: {blend};
        }}
        </style>
    """, unsafe_allow_html=True)
    st.sidebar.markdown("---")

    pagina = st.sidebar.radio(
        "Menu",
        ["🏨 Hospedagem", "👥 Cadastro de Hóspedes", "💸 Despesas",
         "📊 Extrato", "🗺️ Mapa do dinheiro", "📑 Relatórios", "⚙️ Configurações"],
        label_visibility="collapsed"
    )

    if pagina != "👥 Cadastro de Hóspedes":
        st.session_state["_pagina_anterior"] = pagina

    if pagina == "🏨 Hospedagem":
        tela_hospedagem()
    elif pagina == "👥 Cadastro de Hóspedes":
        tela_cadastro_hospedes()
    elif pagina == "💸 Despesas":
        tela_despesas()
    elif pagina == "📊 Extrato":
        tela_extrato()
    elif pagina == "🗺️ Mapa do dinheiro":
        tela_mapa()
    elif pagina == "📑 Relatórios":
        tela_relatorios()
    elif pagina == "⚙️ Configurações":
        tela_configuracoes()

if __name__ == "__main__":
    main()

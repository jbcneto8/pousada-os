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

# ─── TELA EXTRATO ─────────────────────────────────────────────────────────────

def tela_extrato():
    st.title("📊 Extrato geral")
    lancamentos = supabase.table("lancamentos").select("*").order("id", desc=True).execute().data
    total_rec  = sum(r["valor"] for r in lancamentos if r["tipo"] == "Receita")
    total_desp = sum(r["valor"] for r in lancamentos if r["tipo"] == "Despesa")
    saldo      = total_rec - total_desp
    col1, col2, col3 = st.columns(3)
    col1.metric("Receitas",  f"R$ {total_rec:,.2f}")
    col2.metric("Despesas",  f"R$ {total_desp:,.2f}")
    col3.metric("Saldo",     f"R$ {saldo:,.2f}", delta=f"R$ {saldo:,.2f}")
    if saldo < 0:
        st.markdown(
            "<style>[data-testid='stMetricValue']:last-of-type { color: red !important; }</style>",
            unsafe_allow_html=True
        )
    st.divider()
    st.subheader("Lançamentos")
    if not lancamentos:
        st.info("Nenhum lançamento encontrado.")
        return
    for row in lancamentos:
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
    dados = supabase.table("lancamentos").select("*").execute().data
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
            if st.button("🖨️ Visualizar / Imprimir (PDF)", use_container_width=True):
                st.session_state["relatorio_html"] = html_rel

    if st.session_state.get("relatorio_html"):
        st.subheader("🖨️ Prévia do relatório")
        st.caption("Use Ctrl+P / Cmd+P para imprimir ou salvar como PDF.")
        import streamlit.components.v1 as components
        components.html(st.session_state["relatorio_html"], height=600, scrolling=True)
        if st.button("✖️ Fechar prévia", key="fechar_rel"):
            del st.session_state["relatorio_html"]
            st.rerun()

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
    aba_cartoes, aba_categorias = st.tabs(["Cartões / Máquinas", "Categorias de gasto"])
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

# ─── NAVEGAÇÃO PRINCIPAL ──────────────────────────────────────────────────────

def main():
    st.sidebar.image("Pousada_Jaguaruana.png", use_container_width=True)
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

import streamlit as st
from supabase import create_client, Client
from datetime import datetime, timedelta

# ─── CONFIGURAÇÃO DA PÁGINA ───────────────────────────────────────────────────

st.set_page_config(
    page_title="Pousada OS",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── CONEXÃO SUPABASE ─────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = get_supabase()

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


# ─── TELAS ────────────────────────────────────────────────────────────────────

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

    st.divider()
    st.subheader("Lançamentos")

    if not lancamentos:
        st.info("Nenhum lançamento encontrado. Comece registrando uma receita ou despesa.")
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


def tela_hospedagem():
    st.title("🏨 Check-in / Receita")

    with st.form("form_hospedagem", clear_on_submit=True):
        col1, col2 = st.columns(2)
        data        = col1.text_input("Data", value=datetime.now().strftime("%d/%m/%Y"))
        valor_texto = col2.text_input("Valor total R$", placeholder="0,00")

        col3, col4 = st.columns(2)
        quarto      = col3.text_input("Quarto", placeholder="Ex: 3")
        tipo_quarto = col4.selectbox("Tipo", ["Individual", "Duplo", "Triplo", "Quádruplo", "Aberto"])

        col5, col6 = st.columns(2)
        pagamento   = col5.selectbox("Forma de pagamento", ["Dinheiro/Pix", "Cartão"])
        hospedes    = col6.number_input("Hóspedes", min_value=1, max_value=20, value=1)

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
            if not quarto:
                st.warning("Informe o número do quarto.")
                return

            supabase.table("lancamentos").insert({
                "data": data, "tipo": "Receita", "valor": valor,
                "local": "Hospedagem", "sub_local": "Pousada",
                "quarto": quarto, "tipo_quarto": tipo_quarto,
                "hospedes": int(hospedes), "modalidade": pagamento,
                "operadora": operadora if pagamento == "Cartão" else None
            }).execute()

            if pagamento == "Cartão" and operadora:
                res = supabase.table("operadoras").select("taxa_debito, taxa_credito").eq("nome", operadora).execute()
                if res.data:
                    taxa_perc = res.data[0]["taxa_debito"] if modalidade == "Débito" else res.data[0]["taxa_credito"]
                    if taxa_perc > 0:
                        v_taxa = valor * (taxa_perc / 100)
                        supabase.table("lancamentos").insert({
                            "data": data, "tipo": "Despesa", "valor": v_taxa,
                            "local": "TAXA CARTÃO", "sub_local": "Pousada",
                            "descricao": f"Taxa {taxa_perc}% - {operadora} (Qrt {quarto})"
                        }).execute()

            st.success("✅ Receita registrada com sucesso!")
            st.rerun()

        except ValueError:
            st.error("Valor inválido. Use apenas números, ex: 320,00")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")


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
                if not (dt_ini <= dt_item <= dt_fim):
                    continue
                if destino_f != "Ambos" and item.get("sub_local") != destino_f:
                    continue
                if tipo_f == "Apenas Receitas" and item["tipo"] != "Receita":
                    continue
                if tipo_f == "Apenas Despesas" and item["tipo"] != "Despesa":
                    continue
                if quarto_f:
                    if item["tipo"] == "Receita" and str(item.get("quarto")) != quarto_f:
                        continue
                    elif item["tipo"] == "Despesa":
                        continue
                filtrados.append(item)
            except Exception:
                continue

        if not filtrados:
            st.warning("Nenhum registro encontrado para os filtros selecionados.")
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
        ["📊 Extrato", "🏨 Hospedagem", "💸 Despesas", "🗺️ Mapa do dinheiro", "📑 Relatórios", "⚙️ Configurações"],
        label_visibility="collapsed"
    )

    if pagina == "📊 Extrato":
        tela_extrato()
    elif pagina == "🏨 Hospedagem":
        tela_hospedagem()
    elif pagina == "💸 Despesas":
        tela_despesas()
    elif pagina == "🗺️ Mapa do dinheiro":
        tela_mapa()
    elif pagina == "📑 Relatórios":
        tela_relatorios()
    elif pagina == "⚙️ Configurações":
        tela_configuracoes()


if __name__ == "__main__":
    main()

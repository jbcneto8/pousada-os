import streamlit as st
import sqlite3
import os
from datetime import datetime, timedelta

# ─── CONFIGURAÇÃO DA PÁGINA ───────────────────────────────────────────────────

st.set_page_config(
    page_title="Pousada OS",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── BANCO DE DADOS ───────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "pousada.db")


def get_conexao():
    """Retorna uma conexão com o banco de dados."""
    return sqlite3.connect(DB_PATH)


def configurar_banco():
    """Cria as tabelas se ainda não existirem."""
    with get_conexao() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lancamentos (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                data       TEXT,
                tipo       TEXT,
                valor      REAL,
                local      TEXT,
                sub_local  TEXT,
                quarto     TEXT,
                tipo_quarto TEXT,
                hospedes   INTEGER,
                operadora  TEXT,
                modalidade TEXT,
                descricao  TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS operadoras (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                nome          TEXT UNIQUE,
                taxa_debito   REAL,
                taxa_credito  REAL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorias_despesa (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                nome    TEXT,
                destino TEXT
            )
        ''')

        # Migração segura: adiciona coluna destino se não existir
        try:
            cursor.execute("SELECT destino FROM categorias_despesa LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(
                "ALTER TABLE categorias_despesa ADD COLUMN destino TEXT DEFAULT 'Pousada'"
            )

        conn.commit()


# ─── FUNÇÕES DE APOIO ─────────────────────────────────────────────────────────

def obter_operadoras():
    """Retorna lista de nomes de operadoras cadastradas."""
    try:
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome FROM operadoras ORDER BY nome")
            resultado = [row[0] for row in cursor.fetchall()]
            return resultado if resultado else ["Nenhuma cadastrada"]
    except Exception:
        return ["Erro ao carregar"]


def obter_categorias():
    """Retorna lista formatada 'Nome (Destino)' de categorias de despesa."""
    try:
        with get_conexao() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT nome, destino FROM categorias_despesa ORDER BY destino, nome"
            )
            resultado = cursor.fetchall()
            return [f"{row[0]} ({row[1]})" for row in resultado] if resultado else []
    except Exception:
        return []


def extrair_destino(categoria_formatada):
    """Extrai nome limpo e destino de uma string 'Nome (Destino)'."""
    if "(" in categoria_formatada and ")" in categoria_formatada:
        partes = categoria_formatada.split(" (")
        nome = partes[0]
        destino = partes[1].replace(")", "")
        return nome, destino
    return categoria_formatada, "Pousada"


# ─── TELAS ────────────────────────────────────────────────────────────────────

def tela_extrato():
    st.title("📊 Extrato geral")

    with get_conexao() as conn:
        cursor = conn.cursor()
        total_rec  = cursor.execute("SELECT SUM(valor) FROM lancamentos WHERE tipo='Receita'").fetchone()[0] or 0
        total_desp = cursor.execute("SELECT SUM(valor) FROM lancamentos WHERE tipo='Despesa'").fetchone()[0] or 0
        saldo      = total_rec - total_desp

    col1, col2, col3 = st.columns(3)
    col1.metric("Receitas",  f"R$ {total_rec:,.2f}")
    col2.metric("Despesas",  f"R$ {total_desp:,.2f}")
    col3.metric("Saldo",     f"R$ {saldo:,.2f}", delta=f"R$ {saldo:,.2f}")

    st.divider()
    st.subheader("Lançamentos")

    with get_conexao() as conn:
        cursor = conn.cursor()
        lancamentos = cursor.execute(
            """SELECT id, data, tipo, valor, local, sub_local, descricao, quarto
               FROM lancamentos ORDER BY id DESC"""
        ).fetchall()

    if not lancamentos:
        st.info("Nenhum lançamento encontrado. Comece registrando uma receita ou despesa.")
        return

    for row in lancamentos:
        id_l, data, tipo, valor, local, sub_local, descricao, quarto = row
        cor    = "🟢" if tipo == "Receita" else "🔴"
        texto  = f"Hospedagem Q{quarto}" if tipo == "Receita" else f"{local} ({sub_local})"
        obs    = f" — {descricao}" if descricao else ""

        col_data, col_tipo, col_valor, col_desc, col_acao = st.columns([1.2, 1, 1.2, 3, 0.5])
        col_data.caption(data)
        col_tipo.write(f"{cor} {tipo}")
        col_valor.write(f"**R$ {valor:,.2f}**")
        col_desc.write(f"{texto}{obs}")

        if col_acao.button("🗑️", key=f"del_{id_l}", help="Excluir"):
            with get_conexao() as conn:
                conn.execute("DELETE FROM lancamentos WHERE id=?", (id_l,))
                conn.commit()
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

        # Campos de cartão aparecem apenas se necessário
        operadora = None
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

            with get_conexao() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO lancamentos
                       (data, tipo, valor, local, sub_local, quarto, tipo_quarto, hospedes, modalidade, operadora)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (data, "Receita", valor, "Hospedagem", "Pousada",
                     quarto, tipo_quarto, int(hospedes), pagamento,
                     operadora if pagamento == "Cartão" else None)
                )

                # Lança taxa de cartão automaticamente
                if pagamento == "Cartão" and operadora:
                    cursor.execute(
                        "SELECT taxa_debito, taxa_credito FROM operadoras WHERE nome=?",
                        (operadora,)
                    )
                    taxas = cursor.fetchone()
                    if taxas:
                        taxa_perc = taxas[0] if modalidade == "Débito" else taxas[1]
                        if taxa_perc > 0:
                            v_taxa = valor * (taxa_perc / 100)
                            cursor.execute(
                                """INSERT INTO lancamentos
                                   (data, tipo, valor, local, sub_local, descricao)
                                   VALUES (?,?,?,?,?,?)""",
                                (data, "Despesa", v_taxa, "TAXA CARTÃO", "Pousada",
                                 f"Taxa {taxa_perc}% - {operadora} (Qrt {quarto})")
                            )
                conn.commit()

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
            with get_conexao() as conn:
                conn.execute(
                    """INSERT INTO lancamentos
                       (data, tipo, valor, local, sub_local, descricao)
                       VALUES (?,?,?,?,?,?)""",
                    (data, "Despesa", valor, nome_cat, destino, descricao)
                )
                conn.commit()
            st.success("✅ Despesa registrada com sucesso!")
            st.rerun()

        except ValueError:
            st.error("Valor inválido. Use apenas números, ex: 85,00")
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")


def tela_mapa():
    st.title("🗺️ Mapa do dinheiro")

    with get_conexao() as conn:
        cursor = conn.cursor()
        total_rec     = cursor.execute("SELECT SUM(valor) FROM lancamentos WHERE tipo='Receita'").fetchone()[0] or 0
        gasto_casa    = cursor.execute("SELECT SUM(valor) FROM lancamentos WHERE tipo='Despesa' AND sub_local='Casa'").fetchone()[0] or 0
        gasto_pousada = cursor.execute("SELECT SUM(valor) FROM lancamentos WHERE tipo='Despesa' AND sub_local='Pousada'").fetchone()[0] or 0
        hosp_total    = cursor.execute("SELECT SUM(hospedes) FROM lancamentos WHERE tipo='Receita'").fetchone()[0] or 0

    st.metric("Total de hóspedes", int(hosp_total))

    col1, col2, col3 = st.columns(3)
    col1.metric("Entradas",       f"R$ {total_rec:,.2f}")
    col2.metric("Gasto casa",     f"R$ {gasto_casa:,.2f}")
    col3.metric("Gasto pousada",  f"R$ {gasto_pousada:,.2f}")

    st.divider()
    col_quartos, col_casa, col_pousada = st.columns(3)

    with get_conexao() as conn:
        cursor = conn.cursor()

        with col_quartos:
            st.markdown("**🟢 Receita por quarto**")
            rows = cursor.execute(
                "SELECT quarto, SUM(valor) FROM lancamentos WHERE tipo='Receita' GROUP BY quarto ORDER BY CAST(quarto AS INTEGER)"
            ).fetchall()
            for quarto, valor in rows:
                st.write(f"Quarto {quarto} — R$ {valor:,.2f}")

        with col_casa:
            st.markdown("**🟡 Contas da casa**")
            rows = cursor.execute(
                "SELECT local, SUM(valor) FROM lancamentos WHERE tipo='Despesa' AND sub_local='Casa' GROUP BY local"
            ).fetchall()
            for local, valor in rows:
                st.write(f"{local} — R$ {valor:,.2f}")

        with col_pousada:
            st.markdown("**🔵 Contas da pousada**")
            rows = cursor.execute(
                "SELECT local, SUM(valor) FROM lancamentos WHERE tipo='Despesa' AND sub_local='Pousada' GROUP BY local"
            ).fetchall()
            for local, valor in rows:
                st.write(f"{local} — R$ {valor:,.2f}")


def tela_relatorios():
    st.title("📑 Relatórios")

    col1, col2, col3, col4 = st.columns(4)
    data_ini    = col1.text_input("Data inicial", value=(datetime.now() - timedelta(days=30)).strftime("%d/%m/%Y"))
    data_fim    = col2.text_input("Data final",   value=datetime.now().strftime("%d/%m/%Y"))
    destino_f   = col3.selectbox("Destino", ["Ambos", "Pousada", "Casa"])
    tipo_f      = col4.selectbox("Tipo", ["Tudo", "Apenas Receitas", "Apenas Despesas"])

    quarto_f = st.text_input("Filtrar por quarto (opcional)", placeholder="Ex: 3")

    if st.button("🔍 Gerar relatório", use_container_width=True):
        fmt = "%d/%m/%Y"
        try:
            dt_ini = datetime.strptime(data_ini, fmt)
            dt_fim = datetime.strptime(data_fim, fmt)
        except ValueError:
            st.error("Formato de data inválido. Use DD/MM/AAAA.")
            return

        with get_conexao() as conn:
            cursor = conn.cursor()
            todos = cursor.execute(
                "SELECT data, valor, tipo, local, sub_local, descricao, quarto, hospedes FROM lancamentos ORDER BY id ASC"
            ).fetchall()

        filtrados = []
        for item in todos:
            try:
                dt_item = datetime.strptime(item[0], fmt)
                if not (dt_ini <= dt_item <= dt_fim):
                    continue
                if destino_f != "Ambos" and item[4] != destino_f:
                    continue
                if tipo_f == "Apenas Receitas" and item[2] != "Receita":
                    continue
                if tipo_f == "Apenas Despesas" and item[2] != "Despesa":
                    continue
                if quarto_f and quarto_f != "0":
                    if item[2] == "Receita" and str(item[6]) != quarto_f:
                        continue
                    elif item[2] == "Despesa":
                        continue
                filtrados.append(item)
            except Exception:
                continue

        if not filtrados:
            st.warning("Nenhum registro encontrado para os filtros selecionados.")
            return

        t_rec  = sum(i[1] for i in filtrados if i[2] == "Receita")
        t_desp = sum(i[1] for i in filtrados if i[2] == "Despesa")

        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Receitas",  f"R$ {t_rec:,.2f}")
        col_b.metric("Despesas",  f"R$ {t_desp:,.2f}")
        col_c.metric("Saldo",     f"R$ {t_rec - t_desp:,.2f}")

        st.divider()
        for item in filtrados:
            data, valor, tipo, local, sub_local, descricao, quarto, _ = item
            cor   = "🟢" if tipo == "Receita" else "🔴"
            texto = f"Qrt {quarto}" if tipo == "Receita" else local
            obs   = f" — {descricao}" if descricao else ""
            st.write(f"{cor} `{data}` R$ {valor:,.2f} · {texto}{obs}")


def tela_configuracoes():
    st.title("⚙️ Configurações")

    aba_cartoes, aba_categorias = st.tabs(["Cartões / Máquinas", "Categorias de gasto"])

    # ── ABA: CARTÕES ──────────────────────────────────────────────────────────
    with aba_cartoes:
        with st.form("form_operadora", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            nome_op    = col1.text_input("Nome da operadora", placeholder="Ex: Cielo")
            taxa_deb   = col2.number_input("Taxa débito (%)",  min_value=0.0, max_value=20.0, step=0.1, format="%.2f")
            taxa_cred  = col3.number_input("Taxa crédito (%)", min_value=0.0, max_value=20.0, step=0.1, format="%.2f")
            add_op = st.form_submit_button("Adicionar operadora")

        if add_op and nome_op:
            try:
                with get_conexao() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO operadoras (nome, taxa_debito, taxa_credito) VALUES (?,?,?)",
                        (nome_op, taxa_deb, taxa_cred)
                    )
                    conn.commit()
                st.success(f"Operadora '{nome_op}' salva!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        st.subheader("Operadoras cadastradas")
        with get_conexao() as conn:
            ops = conn.execute("SELECT id, nome, taxa_debito, taxa_credito FROM operadoras").fetchall()

        for op_id, nome, td, tc in ops:
            col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 0.5])
            col1.write(nome)
            col2.caption(f"Débito: {td}%")
            col3.caption(f"Crédito: {tc}%")
            if col4.button("🗑️", key=f"del_op_{op_id}"):
                with get_conexao() as conn:
                    conn.execute("DELETE FROM operadoras WHERE id=?", (op_id,))
                    conn.commit()
                st.rerun()

    # ── ABA: CATEGORIAS ───────────────────────────────────────────────────────
    with aba_categorias:
        with st.form("form_categoria", clear_on_submit=True):
            col1, col2 = st.columns(2)
            nome_cat   = col1.text_input("Nome da categoria", placeholder="Ex: Energia elétrica")
            destino    = col2.selectbox("Destino", ["Pousada", "Casa"])
            add_cat = st.form_submit_button("Adicionar categoria")

        if add_cat and nome_cat:
            try:
                with get_conexao() as conn:
                    conn.execute(
                        "INSERT INTO categorias_despesa (nome, destino) VALUES (?,?)",
                        (nome_cat, destino)
                    )
                    conn.commit()
                st.success(f"Categoria '{nome_cat}' adicionada!")
                st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

        st.subheader("Categorias cadastradas")
        with get_conexao() as conn:
            cats = conn.execute("SELECT id, nome, destino FROM categorias_despesa ORDER BY destino, nome").fetchall()

        for cat_id, nome, destino in cats:
            col1, col2, col3 = st.columns([3, 1.5, 0.5])
            col1.write(nome)
            col2.caption(destino)
            if col3.button("🗑️", key=f"del_cat_{cat_id}"):
                with get_conexao() as conn:
                    conn.execute("DELETE FROM categorias_despesa WHERE id=?", (cat_id,))
                    conn.commit()
                st.rerun()


# ─── NAVEGAÇÃO PRINCIPAL ──────────────────────────────────────────────────────

def main():
    configurar_banco()

    st.sidebar.title("🏨 Pousada OS")
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

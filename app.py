import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px

from conexao import carregar_dados_view, consultar_estoque_ao_vivo
from components.kpis import renderizar_kpis
from components.graficos import renderizar_dashboards
from utils.formatadores import ler_css
from utils.exportador import gerar_excel
from utils.auth import verificar_senha, botao_logout

# ==========================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==========================================================
st.set_page_config(page_title="Recomendação de Compras 1.0 (Beta)", page_icon="🛒", layout="wide", initial_sidebar_state="collapsed")

css = ler_css("assets/style.css")
if css:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# ==========================================================
# BARREIRA DE SEGURANÇA (TELA DE LOGIN)
# ==========================================================
if not verificar_senha():
    st.stop()

# ============================================================
# CABEÇALHO DA INTERFACE (LOGO + SUBTÍTULO) - SÓ APARECE LOGADO
# ============================================================
logo_url = "https://grupocontauto.com.br/wp-content/uploads/2022/05/LOGO-Grupo-Contauto-branco-300x81.png"
st.markdown(f"""
    <div class="logo-container"><img src="{logo_url}" class="logo-img"></div>
    <div class="main-subtitle">Estação de Compras Winthor • Gestão de Estoque • Recomendação 1.0 (Beta)</div>
""", unsafe_allow_html=True)

# ==========================================================
# 2. CARGA DE DADOS
# ==========================================================
try:
    with st.spinner("Sincronizando com o ERP Winthor..."):
        df_base = carregar_dados_view()
        if not df_base.empty:
            df_base["OVERSTOCK"] = (df_base["ESTOQUE_DISPONIVEL"] > 0) & (df_base["DIAS_SEM_VENDA"] >= 60)
except Exception as e:
    st.error(f"Erro de conexão com o banco: {e}")
    st.stop()

# ==========================================================
# 3. BARRA DE FILTROS FIXA (Topo)
# ==========================================================
with st.container(border=True):
    st.markdown("<div style='font-weight: 700; color: gray; margin-bottom: 5px;'>🔎 Filtros Globais</div>", unsafe_allow_html=True)
    
    # LINHA 1: Buscas Principais (Trocamos Saldo Físico por Seção)
    c1, c2, c3, c4 = st.columns(4)
    with c1: texto_busca = st.text_input("Buscar Produto", placeholder="Cód ou Nome")
    with c2: filial_sel = st.multiselect("Filial", sorted(df_base["CODFILIAL"].dropna().unique().tolist()) if not df_base.empty else [])
    with c3: depto_sel = st.multiselect("Departamento", sorted(df_base["DEPARTAMENTO"].dropna().unique().tolist()) if not df_base.empty else [])
    with c4: secao_sel = st.multiselect("Seção", sorted(df_base["SECAO"].dropna().unique().tolist()) if not df_base.empty else [])

    # LINHA 2: Marca, Fornecedor e Atualização
    c5, c6, c7, c8 = st.columns([1.5, 1.5, 0.5, 0.5])
    with c5: marca_sel = st.multiselect("Marca", sorted(df_base["MARCA"].dropna().astype(str).unique().tolist()) if not df_base.empty else [])
    with c6: fornec_sel = st.multiselect("Fornecedor (Cadastro)", sorted(df_base["FORNECEDOR"].dropna().astype(str).unique().tolist()) if not df_base.empty else [])
    with c7:
        st.markdown("<br>", unsafe_allow_html=True)
        st.button("🚪 Sair", use_container_width=True, on_click=botao_logout)
        
    with c8: 
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Atualizar", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
# Aplica os filtros GLOBAIS
mask = pd.Series(True, index=df_base.index)
if texto_busca:
    termo = texto_busca.lower().strip()
    mask &= (df_base["DESCRICAO"].str.lower().str.contains(termo, na=False) | df_base["CODPROD"].astype(str).str.contains(termo, na=False))
if filial_sel: mask &= df_base["CODFILIAL"].isin(filial_sel)
if depto_sel: mask &= df_base["DEPARTAMENTO"].isin(depto_sel)
if secao_sel: mask &= df_base["SECAO"].isin(secao_sel) # <--- Nova regra de filtro aplicada aqui
if marca_sel: mask &= df_base["MARCA"].isin(marca_sel)
if fornec_sel: mask &= df_base["FORNECEDOR"].isin(fornec_sel)

df_filtrado = df_base.loc[mask].copy()

# ==========================================================
# 4. PAINEL GERENCIAL (KPIs e Gráficos)
# ==========================================================
renderizar_kpis(df_filtrado)

depto_clicado, filial_clicada = renderizar_dashboards(df_filtrado)

if depto_clicado:
    st.warning(f"👆 **Filtro Automático (Ruptura):** Exibindo dados apenas do Departamento **{depto_clicado}**.")
    df_filtrado = df_filtrado[df_filtrado["DEPARTAMENTO"] == depto_clicado]

if filial_clicada:
    st.warning(f"👆 **Filtro Automático (Atenção):** Exibindo dados apenas da **Filial {filial_clicada}**.")
    df_filtrado = df_filtrado[df_filtrado["CODFILIAL"].astype(str) == str(filial_clicada)]

st.write("---")

# ==========================================================
# 5. NAVEGAÇÃO DE ABAS
# ==========================================================
aba_selecionada = st.radio(
    "Navegação",
    options=["🚨 Urgências (Comprar)", "⚠️ Prevenção (Atenção)", "🚚 Fechamento por Fornecedor", "📦 Raio-X da Rede", "💸 Dinheiro Parado", "🌡️ Termômetro de Itens"],
    horizontal=True, label_visibility="collapsed"
)

# Dicionário de explicações de negócio para cada aba
if aba_selecionada == "🚨 Urgências (Comprar)":
    texto_subtitulo = "🚨 PRODUTOS EM RUPTURA IMEDIATA OU ESTOQUE ZERADO"
    texto_titulo = "Foco em reposição urgente para evitar perda de vendas e atender pedidos imediatamente."

elif aba_selecionada == "⚠️ Prevenção (Atenção)":
    texto_subtitulo = "⚠️ ALERTA DE ESTOQUE CRÍTICO OU BAIXO"
    texto_titulo = "Produtos que ainda possuem saldo, mas correm risco de ruptura futura com base na velocidade de giro."

elif aba_selecionada == "🚚 Fechamento por Fornecedor":
    texto_subtitulo = "🚚 AGRUPAMENTO DE DEMANDAS PARA FECHAMENTO DE CARGA"
    texto_titulo = "Necessidades acumuladas consolidadas por parceiro comercial. Ideal para atingir peso ou valor mínimo de pedido."

elif aba_selecionada == "📦 Raio-X da Rede":
    texto_subtitulo = "📦 ANÁLISE COMPLETA 360° POR SKU"
    texto_titulo = "Rastreamento do item pesquisado acima. Mostra a distribuição física, dias sem venda e excessos em cada filial."

elif aba_selecionada == "💸 Dinheiro Parado":
    valor_total_parado = 0.0
    if not df_filtrado.empty and "OVERSTOCK" in df_filtrado.columns:
        df_over_legenda = df_filtrado[df_filtrado["OVERSTOCK"] == True]
        coluna_custo = "CUSTO_ULT_ENTRADA"
        if coluna_custo in df_over_legenda.columns:
            valor_total_parado = (df_over_legenda["ESTOQUE_DISPONIVEL"] * df_over_legenda[coluna_custo]).sum()
            
    valor_formatado = f"{valor_total_parado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    texto_subtitulo = "💸 ANÁLISE DE ENVELHECIMENTO DE ESTOQUE (AGING) — ITENS PARADOS HÁ MAIS DE 90 DIAS"
    texto_titulo = f"Custo Total Acumulado em Capital Imobilizado: R$ {valor_formatado}"

elif aba_selecionada == "🌡️ Termômetro de Itens":
    texto_subtitulo = "🌡️ TERMÔMETRO DE IMPORTAÇÃO E TENDÊNCIA DE LONGO PRAZO"
    texto_titulo = "Identificação de produtos quentes para ampliação de estoque e frios com alto risco de obsolescência."

st.markdown(f"""
    <div class="banner-orientacao">
        <span class="banner-subtitle" style="display: block; margin-bottom: 2px;">{texto_subtitulo}</span>
        <h2 class="banner-title" style="font-size: 1.15rem !important; font-weight: 600 !important; opacity: 0.9;">{texto_titulo}</h2>
    </div>
""", unsafe_allow_html=True)

# ==========================================================
# 6. EXIBIÇÃO DAS TELAS
# ==========================================================
cfg_colunas_compras = {
    "CODFILIAL": st.column_config.NumberColumn("Filial", alignment="center"),
    "CLASSIFICACAO_GIRO": st.column_config.Column("Nível de Giro", alignment="center"),
    "DIAS_SEM_VENDA": st.column_config.NumberColumn("Dias S/ Venda", alignment="center"),
    "ESTOQUE_DISPONIVEL": st.column_config.NumberColumn("Estoque", alignment="center"),
    "GIRO_TRIMESTRE": st.column_config.NumberColumn("Giro 3 Meses", alignment="center"),
    "GIRO_SEMESTRE": st.column_config.NumberColumn("Giro 6 Meses", alignment="center"),
    "GIRO_ANO": st.column_config.NumberColumn("Giro Ano", alignment="center"),
    "SUGESTAO_30_DIAS": st.column_config.NumberColumn("Sug. 30D", alignment="center"),
    "SUGESTAO_60_DIAS": st.column_config.NumberColumn("Sug. 60D", alignment="center"),
    "SUGESTAO_90_DIAS": st.column_config.NumberColumn("Sug. 90D", alignment="center")
}

cols_exibicao_compras = [
    "CODFILIAL", "CODPROD", "DESCRICAO", "ESTOQUE_DISPONIVEL", 
    "CLASSIFICACAO_GIRO", "DIAS_SEM_VENDA", 
    "GIRO_TRIMESTRE", "GIRO_SEMESTRE", "GIRO_ANO", 
    "SUGESTAO_30_DIAS", "SUGESTAO_60_DIAS", "SUGESTAO_90_DIAS"
]

if aba_selecionada == "🚨 Urgências (Comprar)":
    df_urgencia = df_filtrado[df_filtrado["STATUS"] == "COMPRAR"].copy()
    if df_urgencia.empty:
        st.success("Nenhuma urgência encontrada.")
    else:
        st.dataframe(df_urgencia[cols_exibicao_compras].sort_values(by="SUGESTAO_30_DIAS", ascending=False), use_container_width=True, hide_index=True, height=450, column_config=cfg_colunas_compras)

elif aba_selecionada == "⚠️ Prevenção (Atenção)":
    df_prevencao = df_filtrado[df_filtrado["STATUS"] == "ATENCAO"].copy()
    if df_prevencao.empty:
        st.success("Nenhum item em alerta de atenção.")
    else:
        st.dataframe(df_prevencao[cols_exibicao_compras].sort_values(by="SUGESTAO_30_DIAS", ascending=False), use_container_width=True, hide_index=True, height=450, column_config=cfg_colunas_compras)

elif aba_selecionada == "🚚 Fechamento por Fornecedor":
    st.markdown("#### Agrupamento de Necessidades por Fornecedor")
    df_fornec = df_filtrado[df_filtrado["STATUS"].isin(["COMPRAR", "ATENCAO"])].copy()
    
    if df_fornec.empty:
        st.info("Nenhuma necessidade de compra pendente para fechar carga.")
    else:
        resumo_fornec = df_fornec.groupby("FORNECEDOR", as_index=False).agg(
            QTD_SKUs=("CODPROD", "nunique"),
            TOTAL_SUGERIDO_30D=("SUGESTAO_30_DIAS", "sum"),
            TOTAL_SUGERIDO_60D=("SUGESTAO_60_DIAS", "sum"),
            VALOR_ESTIMADO_30D=("CUSTO_ULT_ENTRADA", lambda x: (x * df_fornec.loc[x.index, "SUGESTAO_30_DIAS"]).sum())
        ).sort_values("TOTAL_SUGERIDO_30D", ascending=False)
        
        st.dataframe(
            resumo_fornec, use_container_width=True, hide_index=True,
            column_config={
                "QTD_SKUs": st.column_config.NumberColumn("Skus Únicos p/ Pedir", alignment="center"),
                "TOTAL_SUGERIDO_30D": st.column_config.NumberColumn("Volume 30D (Un)", alignment="center"),
                "TOTAL_SUGERIDO_60D": st.column_config.NumberColumn("Volume 60D (Un)", alignment="center"),
                "VALOR_ESTIMADO_30D": st.column_config.NumberColumn("Custo Estimado 30D (R$)", format="R$ %.2f")
            }
        )
        st.caption("👈 Use o filtro 'Fornecedor (Cadastro)' no topo da tela para isolar os SKUs específicos.")

elif aba_selecionada == "📦 Raio-X da Rede":
    if not texto_busca: 
        st.warning("👈 Digite o código ou nome de um produto na pesquisa para ver o Raio-X.")
    else:
        if df_filtrado.empty: 
            st.error("Produto não encontrado.")
        else:
            st.success(f"### 🔎 Analisando: {df_filtrado['DESCRICAO'].iloc[0]}")
            df_raiox = df_filtrado[["CODFILIAL", "ESTOQUE_DISPONIVEL", "GIRO_TRIMESTRE", "DIAS_SEM_VENDA", "STATUS_VISUAL", "OVERSTOCK"]].copy()
            df_raiox["ALERTA"] = df_raiox["OVERSTOCK"].map({True: "🚨 EXCESSO", False: "✅ SAUDÁVEL"})
            st.dataframe(df_raiox.drop(columns=["OVERSTOCK"]).sort_values(by="CODFILIAL"), use_container_width=True, hide_index=True)

elif aba_selecionada == "💸 Dinheiro Parado":
    df_over = df_filtrado[df_filtrado["OVERSTOCK"] == True].copy()
    if df_over.empty:
        st.success("Ótima notícia! Nenhum produto com dinheiro parado nas condições atuais.")
    else:
        def classificar_idade(dias):
            if 90 <= dias < 120: return "90 a 119 dias"
            elif 120 <= dias < 150: return "120 a 149 dias"
            elif dias >= 150: return "150+ dias (Prejuízo)"
            else: return "60 a 89 dias"

        df_over["FAIXA_IDADE"] = df_over["DIAS_SEM_VENDA"].apply(classificar_idade)
        df_grafico = df_over[df_over["DIAS_SEM_VENDA"] >= 90].copy()
        
        if not df_grafico.empty:
            st.markdown("#### 📊 Envelhecimento do Estoque (Aging)")
            coluna_valor = "CUSTO_ULT_ENTRADA"
            tem_valor_financeiro = coluna_valor in df_grafico.columns
            
            if tem_valor_financeiro:
                df_grafico["IMPACTO"] = df_grafico["ESTOQUE_DISPONIVEL"] * df_grafico[coluna_valor]
                eixo_y = "IMPACTO"
                titulo_grafico = "Impacto Financeiro (R$)"
            else:
                df_grafico["IMPACTO"] = df_grafico["ESTOQUE_DISPONIVEL"]
                eixo_y = "IMPACTO"
                titulo_grafico = "Quantidade Física Parada (Unidades)"
                st.info("💡 **Observação:** Coluna financeira ausente.")

            agrupado = df_grafico.groupby("FAIXA_IDADE", as_index=False)[eixo_y].sum()
            ordem = ["90 a 119 dias", "120 a 149 dias", "150+ dias (Prejuízo)"]
            agrupado["FAIXA_IDADE"] = pd.Categorical(agrupado["FAIXA_IDADE"], categories=ordem, ordered=True)
            agrupado = agrupado.sort_values("FAIXA_IDADE")
            
            cores_aging = {"90 a 119 dias": "#FBBF24", "120 a 149 dias": "#F97316", "150+ dias (Prejuízo)": "#EF4444"}
            fig = px.bar(agrupado, x="FAIXA_IDADE", y=eixo_y, text=eixo_y, color="FAIXA_IDADE", color_discrete_map=cores_aging)
            fig.update_traces(textposition='outside', texttemplate='%{text:,.0f}')
            fig.update_layout(margin=dict(t=20, b=10, l=10, r=10), height=280, showlegend=False, xaxis_title=None, yaxis_title=titulo_grafico)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
            st.write("---")

        st.markdown("#### Detalhamento dos Itens")
        df_over = df_over.sort_values(by="DIAS_SEM_VENDA", ascending=False)
        st.dataframe(
            df_over[["CODFILIAL", "CODPROD", "DESCRICAO", "FAIXA_IDADE", "DIAS_SEM_VENDA", "ESTOQUE_DISPONIVEL", "QTD_VENDIDA"]], 
            use_container_width=True, hide_index=True, height=400,
            column_config={
                "CODFILIAL": st.column_config.NumberColumn("Filial", alignment="center"),
                "FAIXA_IDADE": st.column_config.Column("Classificação", alignment="center"),
                "DIAS_SEM_VENDA": st.column_config.NumberColumn("Dias S/ Venda", alignment="center"),
                "ESTOQUE_DISPONIVEL": st.column_config.NumberColumn("Estoque Físico", alignment="center"),
                "QTD_VENDIDA": st.column_config.NumberColumn("Giro Acumulado", alignment="center")
            }
        )

elif aba_selecionada == "🌡️ Termômetro de Itens":
    df_term = df_filtrado[df_filtrado["CLASSIFICACAO_GIRO"] != "SEM ENTRADA"].copy()
    
    if df_term.empty:
        st.info("Nenhum dado com histórico suficiente para análise de temperatura.")
    else:
        def classificar_temperatura(row):
            if row['DIAS_SEM_VENDA'] <= 15 and row['GIRO_TRIMESTRE'] >= 20: 
                return "🔥 QUENTE (Aumentar Estoque)"
            elif row['DIAS_SEM_VENDA'] <= 45 and row['GIRO_TRIMESTRE'] >= 5: 
                return "⚡ ESTÁVEL (Manter Padrão)"
            elif row['DIAS_SEM_VENDA'] >= 90 or row['GIRO_TRIMESTRE'] == 0: 
                return "❄️ FRIO (Risco de Obsoleto)"
            else: 
                return "☁️ MORNO / SAZONAL"

        df_term["TEMPERATURA"] = df_term.apply(classificar_temperatura, axis=1)
        
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("🔥 Produtos Quentes", len(df_term[df_term["TEMPERATURA"] == "🔥 QUENTE (Aumentar Estoque)"]))
        t2.metric("⚡ Produtos Estáveis", len(df_term[df_term["TEMPERATURA"] == "⚡ ESTÁVEL (Manter Padrão)"]))
        t3.metric("☁️ Produtos Mornos", len(df_term[df_term["TEMPERATURA"] == "☁️ MORNO / SAZONAL"]))
        t4.metric("❄️ Produtos Frios", len(df_term[df_term["TEMPERATURA"] == "❄️ FRIO (Risco de Obsoleto)"]))
        
        st.write("---")
        col_graf, col_texto = st.columns([2.5, 1])
        
        with col_texto:
            st.markdown("<br><br>", unsafe_allow_html=True)
            st.info("""
            **Como ler o gráfico:**
            * **Esquerda/Topo:** Itens que vendem muito e toda hora. Vale a pena ampliar estoque.
            * **Direita/Base:** Itens desacelerando. Cuidado com obsolescência.
            """)
            
        with col_graf:
            cores_temp = {"🔥 QUENTE (Aumentar Estoque)": "#EF4444", "⚡ ESTÁVEL (Manter Padrão)": "#3B82F6", "☁️ MORNO / SAZONAL": "#9CA3AF", "❄️ FRIO (Risco de Obsoleto)": "#8B5CF6"}
            fig = px.scatter(df_term, x="DIAS_SEM_VENDA", y="GIRO_TRIMESTRE", color="TEMPERATURA", color_discrete_map=cores_temp, hover_data=["CODPROD", "DESCRICAO", "ESTOQUE_DISPONIVEL"], opacity=0.7)
            fig.update_xaxes(autorange="reversed", title="Dias Sem Venda (Menor é Melhor)")
            fig.update_yaxes(title="Giro no Trimestre (Maior é Melhor)")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=350)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        
        st.dataframe(
            df_term[["CODFILIAL", "CODPROD", "DESCRICAO", "TEMPERATURA", "DIAS_SEM_VENDA", "GIRO_TRIMESTRE", "SUGESTAO_90_DIAS", "ESTOQUE_DISPONIVEL"]].sort_values(by=["TEMPERATURA", "GIRO_TRIMESTRE"], ascending=[False, False]),
            use_container_width=True, hide_index=True, height=400,
            column_config={
                "CODFILIAL": st.column_config.NumberColumn("Fil", alignment="center"),
                "TEMPERATURA": st.column_config.Column("Temperatura do Item", alignment="center"),
                "DIAS_SEM_VENDA": st.column_config.NumberColumn("Dias S/ Venda", alignment="center"),
                "GIRO_TRIMESTRE": st.column_config.NumberColumn("Giro 90D", alignment="center"),
                "SUGESTAO_90_DIAS": st.column_config.NumberColumn("Sugestão p/ 90D", alignment="center"),
                "ESTOQUE_DISPONIVEL": st.column_config.NumberColumn("Saldo Atual", alignment="center")
            }
        )

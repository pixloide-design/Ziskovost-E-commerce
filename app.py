import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Ziskovost E-commerce | Manažerský panel",
    page_icon="📊",
    layout="wide"
)

# --- STYLOVÁNÍ (Kompletní CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e0e0e0; }
    div[data-testid="stExpander"] { border: 1px solid #d1d1d1; border-radius: 10px; background-color: white; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; font-size: 1.2em; background-color: #007bff; color: white; border: none; }
    .stButton>button:hover { background-color: #0056b3; border: none; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE DAT ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# --- LOGIN SYSTÉM ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený manažerský přístup")
    heslo = st.text_input("Zadejte firemní heslo:", type="password")
    if st.button("Vstoupit do aplikace"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Neplatné heslo!")
        return False
    return True

if st.session_state.authenticated:
    st.title("💰 Analýza ziskovosti e-shopu")

    # --- POŘÁDNÁ NÁPOVĚDA ---
    with st.expander("📖 PODROBNÝ NÁVOD PRO VEDENÍ (Čtěte pozorně)"):
        st.markdown("""
        ### Jak postupovat:
        1. **Fixní náklady:** Vyplňte náklady na **Marketing** a **Dopravu** (celkové faktury bez DPH).
        2. **Import dat:** Nahrajte soubor `orders.csv`. Program spáruje produkty s nákupními cenami.
        3. **Kontrola nákupních cen (NC):** - Program načte existující ceny z Google tabulky. 
            - Pokud produkt cenu nemá (0.00), dopište ji. 
            - **Výpočet odečte ceny u VŠECH prodaných kusů v exportu.**
        4. **Koeficient:** Použijte pro přepočet balení (např. 1 balení = 2.5 m² -> koeficient 2.5).
        """)

    # --- NAČTENÍ DAT Z GOOGLE ---
    try:
        with st.spinner('Synchronizuji data s databází cen...'):
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- 1. FIXNÍ NÁKLADY ---
    st.subheader("🛠️ 1. Nastavení fixních nákladů období")
    col_f1, col_f2 = st.columns(2)
    mkt_cost = col_f1.number_input("Marketing celkem (Kč bez DPH):", min_value=0.0, step=100.0, value=0.0)
    doprava_cost = col_f2.number_input("Doprava celkem (faktura bez DPH):", min_value=0.0, step=100.0, value=0.0)

    # --- 2. NAHRÁNÍ SOUBORU ---
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Vyberte soubor orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava dat pro editor (Všechny unikátní položky z exportu)
        unikaty = df_obj.drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        editor_prep = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_prep['nakupni_cena'] = editor_prep['nakupni_cena'].fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen")
        st.info("Zde jsou všechny produkty z exportu. Program odečte nákupní cenu od každého prodaného kusu.")
        
        # EDITOR S KLÍČEM
        final_editor_df = st.data_editor(
            editor_prep,
            column_config={
                "itemCode": "Kód produktu",
                "itemName": "Název položky",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="master_editor"
        )

        # --- VÝPOČET ---
        if st.button("🚀 PROVÉST KOMPLETNÍ VÝPOČET", type="primary"):
            with st.status("Analyzuji data a počítám nákupní náklady...", expanded=True) as status:
                
                # A) ZÍSKÁNÍ MASTER CENÍKU (Všechny položky: ty z Google i ty změněné)
                master_ceny = editor_prep.copy()
                state = st.session_state["master_editor"]
                
                # Přepsání hodnot těmi z editoru (včetně těch, co už v tabulce byly)
                if "edited_rows" in state:
                    for row_idx_str, changes in state["edited_rows"].items():
                        row_idx = int(row_idx_str)
                        for col_name, new_val in changes.items():
                            master_ceny.loc[row_idx, col_name] = new_val

                # B) PÁROVÁNÍ 1:1 NA CELÝ EXPORT
                # Vymažeme staré sloupce NC z exportu, aby se netloukly
                df_calc = df_obj.drop(columns=[c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns], errors='ignore')
                
                # Spojení exportu s MASTER ceníkem
                final_merged = pd.merge(df_calc, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # C) VÝPOČET NÁKLADŮ
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                
                # Náklad = Množství * NC * Koeficient (pro každý řádek!)
                final_merged['line_cost'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # Sumy
                t_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = final_merged['line_cost'].sum()
                t_hruba_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_hruba_marze - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet dokončen!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            st.header("📊 Finanční výsledky období")
            
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("CELKOVÉ TRŽBY", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            # TADY UŽ TO MUSÍ UKAZOVAT REÁLNÉ ČÍSLO
            res2.metric("NÁKLADY NA ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            res3.metric("HRUBÁ MARŽE", f"{t_hruba_marze:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=p_color)

            if t_zisk > 0:
                st.balloons()
            else:
                st.error("Období končí ve ztrátě.")

            # Detailní rozpis pro kontrolu
            with st.expander("🔍 Detailní kontrola (Každý prodaný kus a jeho nákupní cena)"):
                st.dataframe(final_merged[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'line_cost']], use_container_width=True)

            # Pokus o uložení
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                update_db = pd.concat([pamet_df, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=update_db)
                st.toast("Ceny uloženy na Google Disk!", icon="✅")
            except:
                st.info("💡 Tip: Pro automatické ukládání cen nastavte 'Service Account' v Secrets.")
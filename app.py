import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Ziskovost E-commerce | Manažerský panel",
    page_icon="📊",
    layout="wide"
)

# --- STYLOVÁNÍ ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e0e0e0; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; background-color: #007bff; color: white; border: none; }
    .stButton>button:hover { background-color: #0056b3; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE DAT ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# --- LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený vstup")
    heslo = st.text_input("Zadejte firemní heslo:", type="password")
    if st.button("Přihlásit se"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Nesprávné heslo!")
else:
    # --- HLAVNÍ APLIKACE ---
    st.title("💰 Analýza ziskovosti e-shopu")

    with st.expander("📖 PODROBNÝ NÁVOD PRO VEDENÍ (Tahák)"):
        st.markdown("""
        ### Jak aplikaci používat:
        1. **Fixní náklady:** Vyplňte celkové náklady na **Marketing** a **Dopravu** bez DPH.
        2. **Nahrání exportu:** Vložte soubor `orders.csv` z administrace.
        3. **Kontrola cen (NC):** V tabulce se zobrazí unikátní položky. Pokud mají NC 0.00, dopište je.
           - *Koeficient:* Použijte pro přepočet balení (např. balení 2.5 m² = koeficient 2.5).
        4. **Výpočet:** Tlačítko provede analýzu celého souboru řádek po řádku.
        """)

    # Načtení paměti z Google Tabulky
    try:
        with st.spinner('Načítám data z Google tabulky...'):
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # 1. SEKCE: NÁKLADY
    st.subheader("🛠️ 1. Nastavení fixních nákladů")
    col1, col2 = st.columns(2)
    mkt_cost = col1.number_input("Marketing celkem (Kč bez DPH):", min_value=0.0, step=100.0)
    doprava_cost = col2.number_input("Doprava celkem (faktura bez DPH):", min_value=0.0, step=100.0)

    # 2. SEKCE: SOUBOR
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Očištění a příprava sloupců
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava tabulky pro editor (bez duplicit sloupců z exportu)
        unikaty = df_obj.drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        editor_prep = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_prep['nakupni_cena'] = editor_prep['nakupni_cena'].fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola a doplnění nákupních cen")
        st.info("Zadejte chybějící ceny přímo do tabulky. Tyto změny se použijí pro aktuální výpočet.")
        
        # EDITOR
        final_editor_df = st.data_editor(
            editor_prep,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="cenovy_editor"
        )

        if st.button("🚀 PROVÉST KOMPLETNÍ VÝPOČET", type="primary"):
            with st.status("Provádím hloubkovou analýzu objednávek...", expanded=True) as status:
                
                # --- ZÍSKÁNÍ AKTUALIZOVANÝCH CEN Z EDITORU ---
                state = st.session_state["cenovy_editor"]
                master_ceny = editor_prep.copy()
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            master_ceny.loc[idx, col] = val

                # --- PÁROVÁNÍ A VÝPOČET ---
                # Odstraníme staré sloupce NC z exportu, pokud tam jsou
                cols_to_drop = [c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns]
                df_clean = df_obj.drop(columns=cols_to_drop, errors='ignore')
                
                # Propojíme export s novým ceníkem
                final_df = pd.merge(df_clean, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # Matika: Množství * NC * Koeficient
                final_df['nakupni_cena'] = final_df['nakupni_cena'].fillna(0)
                final_df['koeficient'] = final_df['koeficient'].fillna(1)
                final_df['celkovy_naklad_polozky'] = final_df['itemAmount'] * final_df['nakupni_cena'] * final_df['koeficient']

                # Sumy
                t_trzby = final_df['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = final_df['celkovy_naklad_polozky'].sum()
                t_zisk = t_trzby - t_naklady_zbozi - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet dokončen!", state="complete", expanded=False)

            # --- VIZUALIZACE VÝSLEDKŮ ---
            st.divider()
            st.header("📊 Finanční výsledky období")
            
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("TRŽBY CELKEM", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            r2.metric("NÁKLADY ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            r3.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč")
            
            # Rentabilita
            rentabilita = (t_zisk / t_trzby * 100) if t_trzby > 0 else 0
            r4.metric("RENTABILITA", f"{rentabilita:.1f} %")

            if t_zisk > 0:
                st.balloons()
                st.success("Období je v zisku!")
            else:
                st.error("Období je ve ztrátě!")

            # --- ZÁCHRANNÁ DATA ---
            with st.expander("💾 Správa dat a uložení"):
                st.write("Pokud automatické uložení selhalo, zkopírujte tyto řádky do své Google tabulky:")
                st.dataframe(master_ceny[['itemCode', 'nakupni_cena', 'koeficient']])
                
                # Pokus o automatické uložení (pokud máš Service Account)
                try:
                    from streamlit_gsheets import GSheetsConnection
                    conn = st.connection("gsheets", type=GSheetsConnection)
                    update_db = pd.concat([pamet_df, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                    conn.update(spreadsheet=URL_CSV, data=update_db)
                    st.toast("Data uložena na Google Disk!", icon="✅")
                except:
                    st.info("💡 Tip: Pro automatické ukládání nastavte 'Service Account' v Secrets.")
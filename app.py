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
            st.error("❌ Neplatné heslo! Přístup odepřen.")
else:
    # --- HLAVNÍ APLIKACE ---
    st.title("💰 Analýza ziskovosti e-shopu")

    # --- NÁPOVĚDA ---
    with st.expander("📖 PODROBNÝ NÁVOD PRO VEDENÍ (Čtěte pozorně)"):
        st.markdown("""
        ### Jak postupovat:
        1. **Fixní náklady:** Vyplňte náklady na **Marketing** a **Dopravu** (celkové měsíční faktury bez DPH).
        2. **Import dat:** Nahrajte soubor `orders.csv`. Aplikace spáruje produkty s nákupními cenami.
        3. **Kontrola nákupních cen (NC):** - Pokud svítí u produktu NC 0.00, systém jej nezná. **Dopište cenu přímo do tabulky.**
            - Pokud produkt cenu má, program ji automaticky použije, pokud ji sami nezměníte.
            - **Koeficient:** Použijte pro přepočet balení (např. 1 balení = 2.5 m² -> koeficient 2.5).
        4. **Finální výpočet:** Klikněte na modré tlačítko. Program přepočítá **každý jeden kus** prodaného zboží z exportu.
        """)

    # --- NAČTENÍ DAT Z GOOGLE TABULKY ---
    try:
        with st.spinner('Synchronizuji data s databází cen...'):
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            # Necháme jen poslední zadanou cenu pro každý kód
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        st.warning("Nepodařilo se připojit k databázi cen. Budete muset zadat ceny ručně.")
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- SEKCE 1: FIXNÍ NÁKLADY ---
    st.subheader("🛠️ 1. Nastavení fixních nákladů období")
    col_f1, col_f2 = st.columns(2)
    mkt_cost = col_f1.number_input("Marketing celkem (Kč bez DPH):", min_value=0.0, step=100.0, value=0.0)
    doprava_cost = col_f2.number_input("Doprava celkem (faktura bez DPH):", min_value=0.0, step=100.0, value=0.0)

    # --- SEKCE 2: NAHRÁNÍ SOUBORU ---
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Vyberte soubor orders.csv", type=['csv'])

    if uploaded_file:
        # Načtení nahraného souboru
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Základní čištění dat
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava dat pro editor (unikátní produkty z exportu + jejich ceny z paměti)
        unikaty = df_obj.drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # Spojíme s databází cen
        editor_prep = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_prep['nakupni_cena'] = editor_prep['nakupni_cena'].fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen")
        st.info("Upravte nebo doplňte ceny. Program započítá všechny položky v tabulce.")
        
        # ZOBRAZENÍ TABULKY K ÚPRAVĚ
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

        # --- TLAČÍTKO VÝPOČTU ---
        if st.button("🚀 PROVÉST KOMPLETNÍ VÝPOČET", type="primary"):
            with st.status("Analyzuji tisíce řádků a počítám náklady...", expanded=True) as status:
                
                # A) ZÍSKÁNÍ AKTUÁLNÍCH CEN (včetně změn na obrazovce)
                master_ceny = editor_prep.copy()
                state = st.session_state["master_editor"]
                
                # Pokud uživatel v tabulce něco změnil, musíme to přepsat
                if "edited_rows" in state:
                    for row_idx_str, changes in state["edited_rows"].items():
                        row_idx = int(row_idx_str)
                        for col_name, new_val in changes.items():
                            master_ceny.loc[row_idx, col_name] = new_val

                # B) PŘÍPRAVA EXPORTU PRO SPOJENÍ
                # Vymažeme sloupce NC, pokud už v exportu náhodou jsou (aby se netloukly)
                df_calc = df_obj.drop(columns=[c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns], errors='ignore')
                
                # C) SPOJENÍ 1:1 (každý prodaný kus v exportu dostane svou cenu)
                final_merged = pd.merge(df_calc, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # D) VLASTNÍ VÝPOČET
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                
                # Náklad na řádek = Množství * NC * Koeficient
                final_merged['line_cost'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # Celkové sumy
                t_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = final_merged['line_cost'].sum()
                t_hruba_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_hruba_marze - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet úspěšně dokončen!", state="complete", expanded=False)

            # --- VIZUALIZACE VÝSLEDKŮ ---
            st.divider()
            st.header("📊 Finanční výsledky období")
            
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("CELKOVÉ TRŽBY", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            
            # TADY UŽ TO MUSÍ UKAZOVAT REÁLNÉ ČÍSLO
            res2.metric("NÁKLADY NA ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            
            res3.metric("HRUBÁ MARŽE", f"{t_hruba_marze:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK (EBIT)", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=p_color)

            if t_zisk > 0:
                st.balloons()
                st.success(f"Skvělé! Období končí v zisku {t_zisk:,.0f} Kč.")
            else:
                st.error(f"Pozor! Období končí ve ztrátě {t_zisk:,.0f} Kč.")

            # --- DETAILNÍ ROZPIS PRO KONTROLU ---
            with st.expander("🔍 DETAILNÍ ROZPIS (Kontrola každé položky)"):
                st.write("V této tabulce vidíte, jakou cenu program přiřadil ke každému řádku z vašeho exportu.")
                st.dataframe(final_merged[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'line_cost']], use_container_width=True)

            # --- ULOŽENÍ DO GOOGLE SHEET ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                # Spojíme starou paměť s novými cenami z editoru
                update_db = pd.concat([pamet_df, master_ceny[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=update_db)
                st.toast("Ceník byl úspěšně aktualizován v Google Tabulce.", icon="💾")
            except:
                st.info("💡 Tip: Pro automatické ukládání cen do Google Tabulky je třeba nastavit přístup přes 'Secrets'.")
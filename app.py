import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Ziskovost E-commerce | Manažerský panel",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- KOMPLETNÍ STYLING (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e0e0e0; }
    div[data-testid="stExpander"] { border: 1px solid #d1d1d1; border-radius: 10px; background-color: white; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3.8em; font-weight: bold; font-size: 1.1em; background-color: #007bff; color: white; border: none; transition: 0.3s; }
    .stButton>button:hover { background-color: #0056b3; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    h1, h2, h3 { color: #1e1e1e; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
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
    heslo = st.text_input("Zadejte firemní heslo pro přístup k zisku:", type="password")
    if st.button("VSTOUPIT DO SYSTÉMU"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Neplatné heslo! Přístup odepřen.")
else:
    # --- HLAVNÍ APLIKACE ---
    st.title("💰 Analýza ziskovosti a správa nákladů")

    # --- POŘÁDNÁ ROZPRACOVANÁ NÁPOVĚDA ---
    with st.expander("📖 MANUÁL PRO VEDENÍ (Jak interpretovat výsledky)"):
        col_n1, col_n2 = st.columns(2)
        with col_n1:
            st.markdown("""
            **Základní postup:**
            1. **Fixní náklady:** Zadejte Marketing (Sklik, FB) a Dopravu (měsíční faktura) bez DPH.
            2. **Import:** Nahrajte soubor `orders.csv`. Program spáruje produkty s nákupními cenami v Google tabulce.
            3. **Kontrola NC:** Pokud vidíte u produktu cenu **0.00**, systém jej nezná. Dopište cenu přímo do tabulky na webu.
            """)
        with col_n2:
            st.markdown("""
            **Logika výpočtu:**
            - Program nebere jen unikátní produkty, ale projde **každý jeden prodaný kus** v exportu.
            - **Koeficient:** Pokud prodáváte balení (např. balení dlažby 2.5 m2), nastavte koeficient na 2.5 a cenu zadejte za 1 m2.
            - **Výsledek:** Zobrazí čistý zisk po odečtení zboží, marketingu a dopravy.
            """)

    # --- NAČTENÍ DAT Z GOOGLE ---
    try:
        with st.spinner('Synchronizuji data s Google Cloud...'):
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        st.error("Nepodařilo se načíst databázi cen z Google Sheets.")
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- SEKCE 1: FIXNÍ NÁKLADY ---
    st.subheader("🛠️ 1. Nastavení fixních nákladů období")
    cf1, cf2 = st.columns(2)
    mkt_cost = cf1.number_input("Celkový marketing (Kč bez DPH):", min_value=0.0, step=100.0, value=0.0, help="Sklik, Google Ads, Facebook Ads")
    doprava_cost = cf2.number_input("Faktura od dopravců (Kč bez DPH):", min_value=0.0, step=100.0, value=0.0, help="Celková suma za štítky a přepravu")

    # --- SEKCE 2: NAHRÁNÍ SOUBORU ---
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv z e-shopu", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Standardizace dat
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava editoru pro unikátní položky z exportu
        unikaty = df_obj.drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        editor_prep = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_prep['nakupni_cena'] = editor_prep['nakupni_cena'].fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola a úprava nákupních cen")
        st.info("Upravte ceny v tabulce. Tyto změny se okamžitě promítnou do celkového výpočtu.")
        
        # TABULKA PRO ÚPRAVU S KLÍČEM
        edited_table = st.data_editor(
            editor_prep,
            column_config={
                "itemCode": "Kód",
                "itemName": "Název produktu",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="cenovy_editor_final"
        )

        # --- TLAČÍTKO VÝPOČTU ---
        if st.button("🚀 PROVÉST KOMPLETNÍ ANALÝZU ZISKU", type="primary"):
            with st.status("Provádím hloubkový výpočet...", expanded=True) as status:
                
                # A) EXTRAKCE DAT Z EDITORU (Ošetření změn)
                # Musíme vzít základ a ručně do něj vložit to, co uživatel změnil
                aktualni_ceny = editor_prep.copy()
                state = st.session_state["cenovy_editor_final"]
                
                if "edited_rows" in state:
                    for idx_str, changes in state["edited_rows"].items():
                        idx = int(idx_str)
                        for col, val in changes.items():
                            aktualni_ceny.at[idx, col] = val

                # Pojistka pro čísla
                aktualni_ceny['nakupni_cena'] = pd.to_numeric(aktualni_ceny['nakupni_cena']).fillna(0)
                aktualni_ceny['koeficient'] = pd.to_numeric(aktualni_ceny['koeficient']).fillna(1)
                
                # B) PŘÍPRAVA EXPORTU (Vyčištění od nulových NC, pokud tam už jsou)
                # Tohle je klíčové - zbavíme se starých NC sloupců z CSV
                df_calc = df_obj.drop(columns=[c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns], errors='ignore')
                
                # C) PÁROVÁNÍ 1:1 (Každý prodaný kus v exportu dostane svou NC)
                final_merged = pd.merge(df_calc, aktualni_ceny[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # D) VÝPOČET NÁKLADŮ NA ŘÁDEK
                final_merged['naklad_polozka'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # Celkové sumy
                t_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = final_merged['naklad_polozka'].sum()
                t_hruba_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_hruba_marze - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Analýza dokončena!", state="complete", expanded=False)

            # --- FINÁLNÍ VÝSLEDKY ---
            st.divider()
            st.header("📊 Finanční výsledky")
            
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("CELKOVÉ TRŽBY", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            
            # TADY UŽ TO MUSÍ UKAZOVAT REÁLNÉ ČÍSLO (ODEČTENÉ NC)
            res2.metric("NÁKLADY ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            
            res3.metric("HRUBÁ MARŽE", f"{t_hruba_marze:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=p_color)

            if t_zisk > 0:
                st.balloons()
                st.success(f"Výborně! Období končí v zisku {t_zisk:,.0f} Kč.")
            else:
                st.error(f"Pozor! Období končí ve ztrátě {t_zisk:,.0f} Kč.")

            # --- DETAILNÍ ROZPIS ---
            with st.expander("🔍 DETAILNÍ ROZPIS NÁKLADŮ (Kontrola výpočtu)"):
                st.write("V této tabulce vidíte, jakou nákupní cenu program přiřadil ke každému řádku objednávky.")
                st.dataframe(
                    final_merged[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'naklad_polozka']]
                    .rename(columns={'naklad_polozka': 'Náklad Celkem'}),
                    use_container_width=True
                )

            # --- ZÁPIS DO GOOGLE SHEET ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                # Spojíme původní paměť s aktuálními daty z obrazovky
                update_final = pd.concat([pamet_df, aktualni_ceny[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=update_final)
                st.toast("Databáze cen byla úspěšně aktualizována na Google Disku.", icon="💾")
            except:
                st.info("💡 Tip: Pro automatické ukládání cen je potřeba nastavit Service Account v Secrets.")
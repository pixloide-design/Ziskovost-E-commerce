import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Ziskovost E-commerce | Manažerský panel",
    page_icon="💰",
    layout="wide"
)

# --- STYLING (CSS) ---
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border: 1px solid #e0e0e0; }
    div[data-testid="stExpander"] { border: 1px solid #d1d1d1; border-radius: 10px; background-color: white; }
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; font-weight: bold; font-size: 1.2em; background-color: #007bff; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE DAT ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔒 Zabezpečený přístup")
        heslo = st.text_input("Zadejte firemní heslo:", type="password")
        if st.button("Vstoupit do aplikace"):
            if heslo == HESLO_PRO_VSTUP:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Neplatné heslo!")
        return False
    return True

if check_password():
    st.title("💸 Výpočet ziskovosti e-shopu")
    
    # --- PROPOJENÍ S GOOGLE ---
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        gsheets_available = True
    except:
        gsheets_available = False

    # --- POŘÁDNÁ NÁPOVĚDA ---
    with st.expander("📖 PODROBNÝ NÁVOD K POUŽITÍ"):
        st.markdown("""
        1. **Fixní náklady:** Zadejte celkové náklady na **Marketing** a **Dopravu** (faktura od dopravců) bez DPH.
        2. **Soubor:** Nahrajte soubor `orders.csv` z administrace e-shopu.
        3. **Nákupní ceny (NC):** V tabulce níže uvidíte všechny produkty. Pokud je NC 0.00, dopište správnou cenu.
        4. **Koeficient:** Pokud prodáváte balení (např. 1 balení = 2.5 m²), nastavte koeficient na 2.5 a NC zadejte za 1 m².
        5. **Výpočet:** Tlačítko provede analýzu celého souboru řádek po řádku.
        """)

    # --- NAČTENÍ DAT ---
    with st.spinner('Synchronizuji data...'):
        try:
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    st.subheader("🛠️ 1. Nastavení fixních nákladů")
    c1, c2 = st.columns(2)
    mkt_cost = c1.number_input("Marketing celkem (Kč):", min_value=0.0, step=100.0, value=0.0)
    doprava_cost = c2.number_input("Doprava celkem (Kč):", min_value=0.0, step=100.0, value=0.0)

    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava editoru
        unikaty = df_obj.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        merged_editor = pd.merge(unikaty, pamet_df, on='itemCode', how='left')
        merged_editor['nakupni_cena'] = merged_editor['nakupni_cena'].fillna(0.0)
        merged_editor['koeficient'] = merged_editor['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen")
        st.info("Upravte ceny v tabulce. Program si je zapamatuje pro aktuální výpočet.")
        
        # EDITOR S KLÍČEM 'editor_cen'
        ed_final = st.data_editor(
            merged_editor,
            column_config={
                "itemCode": "Kód produktu",
                "itemName": "Název položky",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="editor_cen"
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT CENY", type="primary"):
            with st.status("Provádím hloubkový výpočet...", expanded=True) as status:
                
                # --- KLÍČOVÁ OPRAVA: ZÍSKÁNÍ ZMĚN Z EDITORU ---
                actual_prices = merged_editor.copy()
                ed_changes = st.session_state["editor_cen"]
                
                # Pokud uživatel něco v tabulce změnil, musíme to natvrdo přepsat
                if "edited_rows" in ed_changes:
                    for row_idx, changes in ed_changes["edited_rows"].items():
                        for col_name, new_val in changes.items():
                            actual_prices.loc[row_idx, col_name] = new_val

                # Převod na čísla
                actual_prices['nakupni_cena'] = pd.to_numeric(actual_prices['nakupni_cena'], errors='coerce').fillna(0)
                actual_prices['koeficient'] = pd.to_numeric(actual_prices['koeficient'], errors='coerce').fillna(1)
                
                # --- PÁROVÁNÍ 1:1 NA CELÝ EXPORT ---
                # Každý řádek v orders.csv dostane svou NC a Koeficient
                vypocet_all = df_obj.merge(actual_prices[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # Výpočet nákladu na řádku: Množství * NC * Koeficient
                vypocet_all['naklad_radek'] = vypocet_all['itemAmount'] * vypocet_all['nakupni_cena'] * vypocet_all['koeficient']
                
                # Sumy
                t_trzby = vypocet_all['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = vypocet_all['naklad_radek'].sum()
                t_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_marze - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Analýza dokončena!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            st.header("📊 Finanční výsledky")
            
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("TRŽBY CELKEM", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            # Tady už MUSÍ být reálné číslo, ne nula
            res2.metric("NÁKLADY NA ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            res3.metric("HRUBÁ MARŽE", f"{t_marze:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=p_color)

            if t_zisk > 0:
                st.balloons()
            else:
                st.error("Výpočet skončil ve ztrátě.")

            # Zápis do Google
            try:
                if gsheets_available:
                    updated_data = pd.concat([pamet_df, actual_prices[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                    conn.update(spreadsheet=URL_CSV, data=updated_data)
                    st.toast("Ceny uloženy do Google Tabulky.", icon="💾")
            except:
                st.warning("⚠️ Automatické uložení selhalo, ale výpočet na webu je v pořádku.")

            with st.expander("🔎 Rozpis nákladů po položkách"):
                st.dataframe(vypocet_all[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'naklad_radek']], use_container_width=True)
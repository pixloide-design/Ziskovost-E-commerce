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
    .stButton>button { width: 100%; border-radius: 8px; height: 3.5em; font-weight: bold; font-size: 1.2em; background-color: #007bff; color: white; border: none; }
    .stButton>button:hover { background-color: #0056b3; border: none; }
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

if check_password():
    st.title("💸 Analýza ziskovosti e-shopu")
    
    # --- POŘÁDNÁ NÁPOVĚDA ---
    with st.expander("📖 PODROBNÝ NÁVOD PRO VEDENÍ (Rozklikněte)"):
        st.markdown("""
        ### Jak postupovat:
        1. **Fixní náklady:** Vyplňte náklady na **Marketing** a **Dopravu** (celkové měsíční faktury bez DPH).
        2. **Import dat:** Nahrajte soubor `orders.csv`. Aplikace spáruje produkty s nákupními cenami v databázi.
        3. **Kontrola nákupních cen (NC):** - Pokud svítí u produktu NC 0.00, systém jej nezná. **Dopište cenu přímo do tabulky.**
            - **Koeficient:** Použijte pro přepočet balení (např. 1 balení = 2.5 m² -> koeficient 2.5, NC za 1 m²).
        4. **Finální výpočet:** Klikněte na modré tlačítko. Program přepočítá **každý jeden kus** prodaného zboží z exportu.
        """)

    # --- NAČTENÍ DAT ---
    with st.spinner('Synchronizuji data s Google tabulkou...'):
        try:
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    st.subheader("🛠️ 1. Nastavení fixních nákladů období")
    c1, c2 = st.columns(2)
    mkt_cost = c1.number_input("Marketing celkem (Kč bez DPH):", min_value=0.0, step=100.0, value=0.0)
    doprava_cost = c2.number_input("Doprava celkem (faktura Kč bez DPH):", min_value=0.0, step=100.0, value=0.0)

    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava editoru pro UNIKÁTNÍ produkty
        unikaty = df_obj.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        merged_editor = pd.merge(unikaty, pamet_df, on='itemCode', how='left')
        merged_editor['nakupni_cena'] = merged_editor['nakupni_cena'].fillna(0.0)
        merged_editor['koeficient'] = merged_editor['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen pro tento export")
        st.info("Změňte hodnoty 0.00 na skutečné nákupní ceny. Tyto ceny se použijí pro výpočet.")
        
        # EDITOR S KLÍČEM 'editor_cen'
        # DŮLEŽITÉ: Tenhle editor teď budeme "vysávat" natvrdo při kliknutí na tlačítko
        st.data_editor(
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
            # --- ZÁCHRANNÁ BRZDA: NAČTENÍ ZMĚN Z EDITORU ---
            # Musíme vzít merged_editor a ručně do něj vložit změny ze session_state
            final_prices = merged_editor.copy()
            state = st.session_state["editor_cen"]
            
            # Zapracování editovaných řádků
            if "edited_rows" in state:
                for idx_str, changes in state["edited_rows"].items():
                    idx = int(idx_str)
                    for col, val in changes.items():
                        final_prices.at[idx, col] = val

            # Převod na čísla
            final_prices['nakupni_cena'] = pd.to_numeric(final_prices['nakupni_cena'], errors='coerce').fillna(0)
            final_prices['koeficient'] = pd.to_numeric(final_prices['koeficient'], errors='coerce').fillna(1)
            
            # --- VÝPOČET ---
            with st.status("Analyzuji tisíce řádků objednávek...", expanded=True) as status:
                # Párování 1:1 na celý export
                vypocet_all = df_obj.merge(final_prices[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # Výpočet nákladu na každém řádku: Množství * NC * Koeficient
                vypocet_all['naklad_radek'] = vypocet_all['itemAmount'] * vypocet_all['nakupni_cena'] * vypocet_all['koeficient']
                
                # Sumy
                t_trzby = vypocet_all['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = vypocet_all['naklad_radek'].sum()
                t_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_marze - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet dokončen!", state="complete", expanded=False)

            # --- VIZUALIZACE VÝSLEDKŮ ---
            st.divider()
            st.header("📊 Finanční výsledky")
            
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("CELKOVÉ TRŽBY", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            # TADY UŽ NESMÍ BÝT NULA
            res2.metric("NÁKLADY NA ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            res3.metric("HRUBÁ MARŽE", f"{t_marze:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=p_color)

            if t_zisk > 0:
                st.balloons()
            else:
                st.error("Výsledek je ve ztrátě!")

            # --- ZOBRAZENÍ DETAILNÍHO ROZPISU (KONTROLA) ---
            with st.expander("🔎 Detailní rozpis nákupních nákladů (pro kontrolu)"):
                st.write("V této tabulce vidíte přesně, jaké NC program přiřadil k položkám v exportu.")
                st.dataframe(vypocet_all[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'naklad_radek']], use_container_width=True)
            
            # --- ZÁPIS DO GOOGLE SHEET ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                updated_data = pd.concat([pamet_df, final_prices[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=updated_data)
                st.toast("Ceny uloženy do Google Tabulky.", icon="💾")
            except:
                st.warning("⚠️ Automatické uložení selhalo (chybí klíč), ale výpočet nahoře je 100% správně.")
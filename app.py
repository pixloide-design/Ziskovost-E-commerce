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
    .stButton>button { width: 100%; border-radius: 8px; height: 3em; font-weight: bold; font-size: 1.2em; }
    </style>
    """, unsafe_allow_html=True)

# --- HESLO ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔒 Zabezpečený přístup do systému")
        heslo = st.text_input("Zadejte firemní heslo:", type="password")
        if st.button("Vstoupit do aplikace"):
            if heslo == HESLO_PRO_VSTUP:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Neplatné heslo! Přístup odepřen.")
        return False
    return True

if check_password():
    st.title("💸 Manažerský nástroj: Analýza ziskovosti")
    
    # --- PROPOJENÍ ---
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        gsheets_available = True
    except:
        gsheets_available = False

    # --- POŘÁDNÁ NÁPOVĚDA ---
    with st.expander("📖 PODROBNÝ NÁVOD K POUŽITÍ (Čtěte pozorně)"):
        st.markdown("""
        ### 1️⃣ Zadání fixních nákladů
        Do polí níže zadejte náklady, které nejsou obsaženy v exportu objednávek. Jde především o **Marketing** (Sklik, Facebook, Google Ads) a **Dopravu** (měsíční vyúčtování od dopravců). Částky zadávejte bez DPH.
        
        ### 2️⃣ Nahrání dat (Export z administrace)
        Nahrajte soubor `orders.csv`. Program provede analýzu každého řádku a spáruje produkty s nákupními cenami v databázi.
        
        ### 3️⃣ Kontrola a oprava nákupních cen (NC)
        V tabulce "Kontrola nákupních cen" se zobrazí všechny unikátní produkty z exportu. 
        - **NC / Jednotku:** Pokud je u produktu 0.00, systém ho nezná. Dopište správnou cenu.
        - **Koeficient:** Důležité pro položky prodávané v balení (m2, kg). Pokud prodáváte balení, které má 2.5 m2, nastavte koeficient na **2.5**. Program pak spočítá: `množství * 2.5 * NC`.
        
        ### 4️⃣ Výpočet a uložení
        Po kliknutí na tlačítko se provede finální výpočet zisku. Pokud máte nastavené oprávnění, ceny se automaticky uloží do vaší Google Tabulky pro příští použití.
        """)

    # --- NAČTENÍ DAT ---
    with st.spinner('Synchronizuji data s Google Diskem...'):
        try:
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- SEKCE 1: NÁKLADY ---
    st.subheader("🛠️ 1. Fixní náklady období")
    col_nc1, col_nc2 = st.columns(2)
    mkt_cost = col_nc1.number_input("Marketingové náklady celkem (Kč):", min_value=0.0, step=100.0, value=0.0)
    doprava_cost = col_nc2.number_input("Doprava celkem - faktura od dopravců (Kč):", min_value=0.0, step=100.0, value=0.0)

    # --- SEKCE 2: OBJEDNÁVKY ---
    st.subheader("📂 2. Nahrání objednávek (orders.csv)")
    uploaded_file = st.file_uploader("Vyberte soubor pro analýzu", type=['csv'])

    if uploaded_file:
        df_orders = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění dat
        df_orders['itemTotalPriceWithoutVat'] = pd.to_numeric(df_orders['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_orders['itemAmount'] = pd.to_numeric(df_orders['itemAmount'], errors='coerce').fillna(1)
        df_orders['itemCode'] = df_orders['itemCode'].astype(str)

        # Příprava editoru
        unique_items = df_orders.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        merged_for_edit = pd.merge(unique_items, pamet_df, on='itemCode', how='left')
        merged_for_edit['nakupni_cena'] = merged_for_edit['nakupni_cena'].fillna(0.0)
        merged_for_edit['koeficient'] = merged_for_edit['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen")
        st.warning("Zkontrolujte řádky s nákupní cenou 0.00. Po kliknutí na výpočet se tyto hodnoty použijí.")
        
        # EDITOR S KLÍČEM PRO ODCHYT ZMĚN
        ed_state = st.data_editor(
            merged_for_edit,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="master_editor"
        )

        if st.button("🚀 SPOČÍTAT ZISK A AKTUALIZOVAT DATABÁZI", type="primary"):
            with st.status("Provádím finální výpočty...", expanded=True) as status:
                
                # --- KLÍČOVÁ OPRAVA: ZÍSKÁNÍ DAT Z EDITORU ---
                # Musíme vzít editor_prep a ručně na něj aplikovat změny ze session_state
                actual_prices = merged_for_edit.copy()
                editor_changes = st.session_state["master_editor"]
                
                if "edited_rows" in editor_changes:
                    for idx, changes in editor_changes["edited_rows"].items():
                        for col, val in changes.items():
                            actual_prices.loc[idx, col] = val

                # Převod na čísla
                actual_prices['nakupni_cena'] = pd.to_numeric(actual_prices['nakupni_cena'], errors='coerce').fillna(0)
                actual_prices['koeficient'] = pd.to_numeric(actual_prices['koeficient'], errors='coerce').fillna(1)
                
                # --- PÁROVÁNÍ 1:1 ---
                # Každý jeden řádek z CSV dostane svou cenu
                final_calc = df_orders.merge(actual_prices[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # Matika: Množství * NC * Koeficient
                final_calc['cost_total'] = final_calc['itemAmount'] * final_calc['nakupni_cena'] * final_calc['koeficient']
                
                # Součty
                total_rev = final_calc['itemTotalPriceWithoutVat'].sum()
                total_cost = final_calc['cost_total'].sum()
                total_margin = total_rev - total_cost
                total_profit = total_margin - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet dokončen!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            st.header("📊 Finanční přehled období")
            
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("TRŽBY CELKEM", f"{total_rev:,.0f} Kč".replace(',', ' '))
            r2.metric("NÁKLADY ZBOŽÍ", f"{total_cost:,.0f} Kč".replace(',', ' '), delta=f"-{total_cost:,.0f}", delta_color="inverse")
            r3.metric("HRUBÁ MARŽE", f"{total_margin:,.0f} Kč".replace(',', ' '))
            
            p_color = "normal" if total_profit > 0 else "inverse"
            r4.metric("ČISTÝ ZISK", f"{total_profit:,.0f} Kč".replace(',', ' '), delta=f"{total_profit:,.0f} Kč", delta_color=p_color)

            if total_profit > 0:
                st.balloons()
                st.success(f"Výborně! Období končí v zisku {total_profit:,.0f} Kč.")
            else:
                st.error(f"Pozor! Období končí ve ztrátě {total_profit:,.0f} Kč.")

            # --- ZÁPIS DO GOOGLE SHEET ---
            try:
                if gsheets_available:
                    updated_db = pd.concat([pamet_df, actual_prices[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                    conn.update(spreadsheet=URL_CSV, data=updated_db)
                    st.toast("Ceník byl úspěšně aktualizován na Google Disku.", icon="💾")
            except:
                st.warning("⚠️ Automatický zápis se nezdařil (chybí oprávnění), ale výpočet na obrazovce je správný.")

            with st.expander("🔎 Detailní rozpis nákupních nákladů po položkách"):
                st.dataframe(final_calc[['itemCode', 'itemName', 'itemAmount', 'nakupni_cena', 'cost_total']], use_container_width=True)
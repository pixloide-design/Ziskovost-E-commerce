import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Ziskovost E-shopu", layout="wide", initial_sidebar_state="collapsed")

# --- HESLO ---
HESLO_PRO_VSTUP = "mojeheslo123"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY/edit?usp=sharing"

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if not st.session_state.authenticated:
        st.title("🔒 Vstup do systému")
        heslo = st.text_input("Zadejte heslo:", type="password")
        if st.button("Přihlásit"):
            if heslo == HESLO_PRO_VSTUP:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Nesprávné heslo")
        return False
    return True

if check_password():
    # Propojení s Google Sheets
    conn = st.connection("gsheets", type=GSheetsConnection)

    st.title("💸 Výpočet ziskovosti e-shopu")

    # --- 1. NÁPOVĚDA ---
    with st.expander("ℹ️ NÁPOVĚDA A TAHÁK"):
        st.markdown("""
        ### Jak na to?
        1. **Fixní náklady:** Zadejte sumu za Marketing (Sklik/FB) a Dopravu (faktura od dopravce).
        2. **Soubor:** Nahrajte `orders.csv`. Program spáruje produkty s nákupními cenami v tabulce.
        3. **Doplnění cen:** Pokud vidíte u produktu NC 0.00, doplňte ji přímo v tabulce na webu.
        4. **Koeficient:** Použijte, pokud prodáváte balení (např. 1 balení = 5 m2, dejte koeficient 5).
        5. **Uložení:** Tlačítko 'Spočítat a uložit' přepíše ceny v Google Tabulce, aby tam příště už byly.
        """)

    # Načtení dat z tabulky
    try:
        pamet_df = conn.read(spreadsheet=SHEET_URL)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
        pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except Exception:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- 2. VSTUPY NÁKLADŮ ---
    st.subheader("1. Ostatní náklady (bez DPH)")
    col_a, col_b = st.columns(2)
    mkt = col_a.number_input("Marketing (Kč):", min_value=0.0, value=0.0, step=500.0)
    doprava_faktura = col_b.number_input("Doprava faktura (Kč):", min_value=0.0, value=0.0, step=500.0)

    # --- 3. NAHRÁNÍ SOUBORU ---
    st.subheader("2. Export z administrace")
    uploaded_file = st.file_uploader("Nahrajte orders.csv", type=['csv'])

    if uploaded_file:
        df_objednavky = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Očištění dat
        df_objednavky['itemTotalPriceWithoutVat'] = pd.to_numeric(df_objednavky['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_objednavky['itemAmount'] = pd.to_numeric(df_objednavky['itemAmount'], errors='coerce').fillna(1)
        df_objednavky['itemCode'] = df_objednavky['itemCode'].astype(str)

        # Příprava unikátních produktů pro editor
        produkty_v_exportu = df_objednavky.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        
        # Spojení se stávajícím ceníkem z Google
        editor_prep = pd.merge(produkty_v_exportu, pamet_df, on='itemCode', how='left')
        editor_prep['nakupni_cena'] = editor_prep['nakupni_cena'].fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)

        st.subheader("3. Kontrola a úprava nákupních cen")
        st.info("Upravte ceny (nuly). Pro výpočet se použijí ceny z tabulky níže pro VŠECHNY položky v objednávkách.")
        
        # DATA EDITOR
        aktualni_editor_df = st.data_editor(
            editor_prep,
            column_config={
                "itemCode": "Kód",
                "itemName": "Název produktu",
                "nakupni_cena": st.column_config.NumberColumn("NC za ks/jednotku", format="%.2f Kč"),
                "koeficient": st.column_config.NumberColumn("Koeficient (balení)", format="%.2f")
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT CENY", type="primary"):
            # 1. PŘÍPRAVA CENÍKU (To co je teď v editoru)
            master_cenik = aktualni_editor_df[['itemCode', 'nakupni_cena', 'koeficient']].copy()
            
            # 2. VÝPOČET - Spojíme ceny na každý jeden řádek objednávky
            df_final = pd.merge(df_objednavky, master_cenik, on='itemCode', how='left')
            
            # Ošetření NC
            df_final['nakupni_cena'] = df_final['nakupni_cena'].fillna(0)
            df_final['koeficient'] = df_final['koeficient'].fillna(1)
            
            # Matika: Množství * NC * Koeficient
            df_final['naklad_celkem_polozka'] = df_final['itemAmount'] * df_final['nakupni_cena'] * df_final['koeficient']
            
            # Celkové sumy
            suma_trzby = df_final['itemTotalPriceWithoutVat'].sum()
            suma_naklady_zbozi = df_final['naklad_celkem_polozka'].sum()
            suma_marze = suma_trzby - suma_naklady_zbozi
            suma_zisk = suma_marze - mkt - doprava_faktura

            # Zobrazení výsledků
            st.divider()
            st.header("📊 Finanční výsledky")
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Tržby celkem", f"{suma_trzby:,.0f} Kč")
            m2.metric("Nákupní ceny zboží", f"{suma_naklady_zbozi:,.0f} Kč")
            m3.metric("Hrubá marže", f"{suma_marze:,.0f} Kč")
            m4.metric("ČISTÝ ZISK", f"{suma_zisk:,.0f} Kč", delta=f"{suma_zisk:,.0f} Kč")

            # POKUS O ZÁPIS DO GOOGLE
            try:
                # Spojíme s celou pamětí, abychom o nic nepřišli
                update_df = pd.concat([pamet_df, master_cenik]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=SHEET_URL, data=update_df)
                st.success("✅ Ceny byly uloženy do Google Tabulky.")
            except Exception as e:
                st.warning("⚠️ Ceny se nepodařilo uložit do Google Tabulky (chybí Service Account v Secrets). Výpočet je ale správný.")

            # Detailní tabulka pod tím (volitelně)
            with st.expander("Zobrazit detailní rozpis po položkách"):
                st.dataframe(df_final[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'naklad_celkem_polozka']])
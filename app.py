import streamlit as st
import pandas as pd

# --- KONFIGURACE ---
HESLO_PRO_VSTUP = "mojeheslo123"  # <--- Tady si dej vlastní heslo
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

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
    st.set_page_config(page_title="Ziskovost E-shopu", layout="wide")
    st.title("💸 Výpočet ziskovosti e-shopu")

    # Načtení dat z Google Tabulky
    try:
        # Načteme ceník z Google tabulky
        pamet_df = pd.read_csv(URL_CSV)
        # Ujistíme se, že sloupce jsou správně, i kdyby byla tabulka prázdná
        if "itemCode" not in pamet_df.columns:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- 1. NÁPOVĚDA (TAHÁK) ---
    with st.expander("❓ NÁPOVĚDA: Jak s aplikací pracovat?"):
        st.markdown("""
        1. **Fixní náklady:** Zadejte částky za marketing a dopravu (faktury od dopravců).
        2. **Nahrání dat:** Nahrajte CSV export z e-shopu (soubor `orders.csv`).
        3. **Doplnění cen:** V tabulce se zobrazí jen produkty, které ještě nemají uloženou nákupní cenu, nebo u kterých je nastaven koeficient (balení).
        
        **Co znamená Koeficient?**
        * **1.0** = Prodáváte po kusech (1 ks na webu = 1 ks od dodavatele).
        * **Např. 2.5** = Prodáváte balení (1 balení na webu obsahuje 2.5 m² nebo 2.5 kg zboží). Do nákupní ceny pak pište cenu za 1 m² / 1 kg.
        """)

    # --- 2. VSTUPY ---
    st.subheader("1. Fixní náklady (bez DPH)")
    col1, col2 = st.columns(2)
    mkt = col1.number_input("Marketing (Kč):", min_value=0.0, value=0.0)
    doprava = col2.number_input("Doprava - faktura (Kč):", min_value=0.0, value=0.0)

    st.subheader("2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Vyberte soubor orders.csv", type=['csv'])

    if uploaded_file:
        # Načtení nahraného CSV
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Základní čištění dat
        df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
        df['itemCode'] = df['itemCode'].astype(str)
        
        # Spojení s pamětí cen
        unikaty = df.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
        spojeno = pd.merge(unikaty, pamet_df, on='itemCode', how='left')
        
        spojeno['nakupni_cena'] = spojeno['nakupni_cena'].fillna(0.0)
        spojeno['koeficient'] = spojeno['koeficient'].fillna(1.0)

        # Filtrace: Zobrazit jen to, co je potřeba řešit
        k_uprave = spojeno[(spojeno['nakupni_cena'] == 0.0) | (spojeno['koeficient'] != 1.0)].copy()

        st.write("### 📝 Položky k doplnění nákupních cen")
        if not k_uprave.empty:
            st.info("Zadejte ceny u položek níže. Tyto ceny se použijí pro aktuální výpočet.")
            opravena_data = st.data_editor(
                k_uprave[['itemCode', 'itemName', 'nakupni_cena', 'koeficient']],
                column_config={
                    "itemCode": "Kód",
                    "itemName": "Název",
                    "nakupni_cena": "NC bez DPH (Kč)",
                    "koeficient": "Koeficient"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success("Všechny položky mají nastavenou cenu.")
            opravena_data = pd.DataFrame(columns=['itemCode', 'nakupni_cena', 'koeficient'])

        if st.button("🚀 Spočítat ziskovost", type="primary"):
            # Sloučení opravených dat s původním ceníkem
            aktualni_cenik = pd.concat([pamet_df, opravena_data]).drop_duplicates(subset=['itemCode'], keep='last')
            
            # Finální výpočet
            df_final = pd.merge(df, aktualni_cenik, on='itemCode', how='left')
            df_final['nakupni_cena'] = df_final['nakupni_cena'].fillna(0)
            df_final['koeficient'] = df_final['koeficient'].fillna(1)
            
            df_final['naklad_polozka'] = df_final['itemAmount'] * df_final['nakupni_cena'] * df_final['koeficient']
            
            celkove_trzby = df_final['itemTotalPriceWithoutVat'].sum()
            celkove_nc = df_final['naklad_polozka'].sum()
            cisty_zisk = celkove_trzby - celkove_nc - mkt - doprava

            # Zobrazení výsledků
            st.divider()
            st.header("📊 Celkové výsledky")
            c1, c2, c3 = st.columns(3)
            c1.metric("Celkové tržby", f"{celkove_trzby:,.0f} Kč".replace(',', ' '))
            c2.metric("Náklady na zboží", f"{celkove_nc:,.0f} Kč".replace(',', ' '))
            c3.metric("Ostatní náklady", f"{(mkt + doprava):,.0f} Kč".replace(',', ' '))
            
            st.subheader(f"💰 Čistý zisk: {cisty_zisk:,.0f} Kč".replace(',', ' '))
            
            st.warning("⚠️ Poznámka: Ceny zadané v tabulce výše se použily pro výpočet. Pro jejich trvalé uložení je přepište přímo do Google Tabulky.")
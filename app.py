import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# Nastavení stránky
st.set_page_config(page_title="Ziskovost E-shopu", layout="wide")

# --- KONFIGURACE ---
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
    # POZOR: V Secrets musíš mít nastavený Service Account klíč!
    conn = st.connection("gsheets", type=GSheetsConnection)

    st.title("💸 Výpočet zisku a správa cen")

    with st.expander("❓ NÁPOVĚDA A TAHÁK"):
        st.markdown("""
        1. **Nahrajte orders.csv** - program načte všechny prodeje.
        2. **Doplňte NC** - u produktů, které svítí červeně (NC 0), doplňte nákupní cenu.
        3. **Uložte** - tlačítko uloží ceny do Google tabulky pro všechna budoucí použití.
        """)

    # Načtení dat z tabulky
    try:
        pamet_df = conn.read(spreadsheet=SHEET_URL)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
        pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # Vstupy nákladů
    st.subheader("1. Ostatní náklady")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketing (Kč bez DPH):", value=0.0)
    doprava_faktura = c2.number_input("Doprava faktura (Kč bez DPH):", value=0.0)

    # Nahrání souboru
    uploaded_file = st.file_uploader("2. Nahrajte export objednávek (CSV)", type=['csv'])

    if uploaded_file:
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění dat z e-shopu
        df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
        df['itemCode'] = df['itemCode'].astype(str)

        # Spárování s ceníkem
        vsechny_produkty = df.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        spojeno = pd.merge(vsechny_produkty, pamet_df, on='itemCode', how='left')
        spojeno['nakupni_cena'] = spojeno['nakupni_cena'].fillna(0.0)
        spojeno['koeficient'] = spojeno['koeficient'].fillna(1.0)

        st.subheader("3. Kontrola nákupních cen")
        # Zvýraznění chybějících cen
        def highlight_zeros(val):
            color = 'red' if val == 0 else 'black'
            return f'color: {color}'

        editor_data = st.data_editor(
            spojeno,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC bez DPH", format="%.2f Kč"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT CENY", type="primary"):
            # A) AKTUALIZACE GOOGLE TABULKY
            nove_ceny = editor_data[['itemCode', 'nakupni_cena', 'koeficient']].copy()
            final_pro_ulozeni = pd.concat([pamet_df, nove_ceny]).drop_duplicates(subset=['itemCode'], keep='last')
            
            try:
                conn.update(spreadsheet=SHEET_URL, data=final_pro_ulozeni)
                st.success("✅ Ceny uloženy do Google Tabulky!")
            except Exception as e:
                st.error(f"Chyba zápisu: {e}. Ujistěte se, že máte v Secrets správný Service Account klíč!")

            # B) KOMPLETNÍ VÝPOČET ZISKU
            # Každý řádek z objednávek musí dostat nákupní cenu
            vypocet_df = pd.merge(df, final_pro_ulozeni, on='itemCode', how='left')
            vypocet_df['nakupni_cena'] = vypocet_df['nakupni_cena'].fillna(0)
            vypocet_df['koeficient'] = vypocet_df['koeficient'].fillna(1)
            
            # Náklad na řádek = (množství * nákupka * koeficient)
            vypocet_df['naklad_radek'] = vypocet_df['itemAmount'] * vypocet_df['nakupni_cena'] * vypocet_df['koeficient']
            
            # Sumy
            celkove_trzby = vypocet_df['itemTotalPriceWithoutVat'].sum()
            celkove_naklady_zbozi = vypocet_df['naklad_radek'].sum()
            marze = celkove_trzby - celkove_naklady_zbozi
            zisk = marze - mkt - doprava_faktura

            # Zobrazení výsledků
            st.divider()
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("Tržby celkem", f"{celkove_trzby:,.0f} Kč")
            res2.metric("Náklady zboží", f"{celkove_naklady_zbozi:,.0f} Kč")
            res3.metric("Hrubá marže", f"{marze:,.0f} Kč")
            res4.metric("ČISTÝ ZISK", f"{zisk:,.0f} Kč", delta=f"{zisk:,.0f} Kč")

            if zisk > 0:
                st.balloons()
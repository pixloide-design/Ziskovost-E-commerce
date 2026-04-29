import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

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
    st.set_page_config(page_title="Ziskovost E-shopu", layout="wide")
    
    # Propojení s Google Sheets
    conn = st.connection("gsheets", type=GSheetsConnection)

    st.title("💸 Manažerský výpočet zisku")

    # 1. NÁPOVĚDA
    with st.expander("ℹ️ TAHÁK: Jak aplikaci používat?"):
        st.markdown("""
        * **Krok 1:** Zadejte fixní náklady na marketing a dopravu (faktury).
        * **Krok 2:** Nahrajte soubor `orders.csv` exportovaný z administrace.
        * **Krok 3:** V tabulce níže uvidíte seznam produktů. Pokud u nich svítí **nákupní cena 0.00**, doplňte ji.
        * **Koeficient:** Pokud prodáváte např. m2 (1 kus na webu = 2.5 m2 od dodavatele), nastavte koeficient 2.5. Program tím nákupní cenu automaticky vynásobí.
        * **Uložení:** Kliknutím na tlačítko se ceny **trvale uloží** do vaší Google Tabulky a už je příště nebudete muset vypisovat.
        """)

    # Načtení dat z Google Sheet
    try:
        pamet_df = conn.read(spreadsheet=SHEET_URL)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
        pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # 2. FIXNÍ NÁKLADY
    st.subheader("1. Fixní náklady (bez DPH)")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketingové náklady (Kč):", min_value=0.0, value=0.0, step=100.0)
    doprava_faktura = c2.number_input("Faktura od dopravců (Kč):", min_value=0.0, value=0.0, step=100.0)

    # 3. NAHRÁNÍ SOUBORU
    st.subheader("2. Export z e-shopu")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv", type=['csv'])

    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
            
            # Kontrola, zda jsou v CSV správné sloupce
            required_cols = ['itemCode', 'itemName', 'itemTotalPriceWithoutVat', 'itemAmount']
            if not all(col in df.columns for col in required_cols):
                st.error("⚠️ Soubor neobsahuje všechny potřebné sloupce! Zkontrolujte export.")
            else:
                df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
                df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
                df['itemCode'] = df['itemCode'].astype(str)

                # Unikátní produkty pro tabulku editoru
                produkty_v_objednavce = df.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
                spojeno = pd.merge(produkty_v_objednavce, pamet_df, on='itemCode', how='left')
                spojeno['nakupni_cena'] = spojeno['nakupni_cena'].fillna(0.0)
                spojeno['koeficient'] = spojeno['koeficient'].fillna(1.0)

                st.write("### 📝 Ceník produktů v objednávkách")
                st.info("Upravte ceny tam, kde chybí. Po kliknutí na tlačítko níže se změny uloží.")
                
                editor_data = st.data_editor(
                    spojeno,
                    column_config={
                        "itemCode": "Kód",
                        "itemName": "Název produktu",
                        "nakupni_cena": st.column_config.NumberColumn("NC za jednotku (Kč)", format="%.2f"),
                        "koeficient": st.column_config.NumberColumn("Koeficient (balení)", min_value=0.01)
                    },
                    hide_index=True,
                    use_container_width=True
                )

                if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT CENY", type="primary"):
                    # ULOŽENÍ DO GOOGLE SHEET
                    nove_ceny = editor_data[['itemCode', 'nakupni_cena', 'koeficient']].copy()
                    final_pro_ulozeni = pd.concat([pamet_df, nove_ceny]).drop_duplicates(subset=['itemCode'], keep='last')
                    
                    try:
                        conn.update(spreadsheet=SHEET_URL, data=final_pro_ulozeni)
                        st.toast("Ceny uloženy do Google Sheets!", icon="✅")
                    except Exception as e:
                        st.error(f"Chyba při ukládání: {e}")

                    # VÝPOČET
                    vypocet_df = pd.merge(df, final_pro_ulozeni, on='itemCode', how='left')
                    vypocet_df['naklad_celkem'] = vypocet_df['itemAmount'] * vypocet_df['nakupni_cena'].fillna(0) * vypocet_df['koeficient'].fillna(1)
                    
                    trzby = vypocet_df['itemTotalPriceWithoutVat'].sum()
                    naklady_zbozi = vypocet_df['naklad_celkem'].sum()
                    marze = trzby - naklady_zbozi
                    zisk = marze - mkt - doprava_faktura

                    # VIZUALIZACE VÝSLEDKŮ
                    st.divider()
                    st.header("📊 Finanční přehled")
                    
                    met1, met2, met3 = st.columns(3)
                    met1.metric("Celkové tržby (bez DPH)", f"{trzby:,.0f} Kč".replace(',', ' '))
                    met2.metric("Nákupní cena zboží", f"{naklady_zbozi:,.0f} Kč".replace(',', ' '))
                    met3.metric("Hrubá marže", f"{marze:,.0f} Kč".replace(',', ' '))

                    st.subheader(f"💰 Čistý zisk: {zisk:,.0f} Kč".replace(',', ' '))
                    
                    if zisk > 0:
                        st.balloons()
                    else:
                        st.warning("E-shop je v tomto období ve ztrátě.")

        except Exception as e:
            st.error(f"Chyba při zpracování souboru: {e}")
import streamlit as st
import pandas as pd

# --- KONFIGURACE ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
# Odkaz pro čtení (veřejný export)
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
    st.title("💸 Výpočet zisku (Verze bez API)")

    # 1. NAČTENÍ CENÍKU (Z Google Tabulky)
    try:
        pamet_df = pd.read_csv(URL_CSV)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
        pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    with st.expander("ℹ️ NÁPOVĚDA"):
        st.write("1. Zadejte náklady. 2. Nahrajte orders.csv. 3. Doplňte ceny u produktů, které je nemají (svítí tam 0).")

    # 2. VSTUPY
    st.subheader("1. Fixní náklady")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketing (Kč):", value=0.0)
    doprava = c2.number_input("Doprava faktura (Kč):", value=0.0)

    # 3. SOUBOR
    uploaded_file = st.file_uploader("2. Nahrajte orders.csv", type=['csv'])

    if uploaded_file:
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
        df['itemCode'] = df['itemCode'].astype(str)

        # Seznam všech unikátních věcí v objednávce
        vsechny_produkty = df.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        
        # Spojíme s tím, co už známe z Google tabulky
        pracovni_cenik = pd.merge(vsechny_produkty, pamet_df, on='itemCode', how='left')
        pracovni_cenik['nakupni_cena'] = pracovni_cenik['nakupni_cena'].fillna(0.0)
        pracovni_cenik['koeficient'] = pracovni_cenik['koeficient'].fillna(1.0)

        st.write("### 📝 Kontrola nákupních cen")
        st.info("Upravte ceny tam, kde je nula. Tyto ceny se použijí pro výpočet u VŠECH položek v objednávkách.")
        
        # Editor - TADY UŽIVATEL DOPLNÍ CENY
        final_cenik_z_webu = st.data_editor(
            pracovni_cenik,
            column_config={
                "itemCode": "Kód",
                "itemName": "Název",
                "nakupni_cena": "NC bez DPH (Kč)",
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("🚀 SPOČÍTAT KOMPLETNÍ ZISK", type="primary"):
            # KLÍČOVÝ MOMENT: Vezmeme ÚPLNĚ VŠECHNY objednávky z CSV
            # a ke každé jedné položce přiřadíme cenu z toho, co je v editoru
            
            ceny_pro_vypocet = final_cenik_z_webu[['itemCode', 'nakupni_cena', 'koeficient']]
            
            # Spojení 1:1 - každá položka v objednávce dostane svou cenu
            vypocet_vse = pd.merge(df, ceny_pro_vypocet, on='itemCode', how='left')
            
            # Výpočet nákladů pro každý řádek: (množství * NC * koeficient)
            vypocet_vse['naklad_radek'] = vypocet_vse['itemAmount'] * vypocet_vse['nakupni_cena'] * vypocet_vse['koeficient']
            
            # CELKOVÉ SUMY
            celkove_trzby = vypocet_vse['itemTotalPriceWithoutVat'].sum()
            celkove_naklady_zbozi = vypocet_vse['naklad_radek'].sum()
            zisk = celkove_trzby - celkove_naklady_zbozi - mkt - doprava

            # VÝSLEDKY
            st.divider()
            res1, res2, res3 = st.columns(3)
            res1.metric("Tržby celkem", f"{celkove_trzby:,.0f} Kč")
            res2.metric("Náklady na zboží", f"{celkove_naklady_zbozi:,.0f} Kč")
            res3.metric("Čistý zisk", f"{zisk:,.0f} Kč")

            # BONUSEK: Data pro Google Tabulku
            st.subheader("📂 Data pro uložení")
            st.write("Jelikož Google nepovolil automatický zápis, zkopírujte tyto řádky a vložte je do své Google tabulky pro příště:")
            st.dataframe(final_cenik_z_webu[['itemCode', 'nakupni_cena', 'koeficient']])
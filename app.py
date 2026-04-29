import streamlit as st
import pandas as pd

# --- KONFIGURACE ---
HESLO_PRO_VSTUP = "mojeheslo123" 
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
    st.title("💸 Výpočet zisku - FINÁLNÍ OPRAVA")

    # 1. NAČTENÍ CENÍKU Z GOOGLE TABULKY
    try:
        # Načteme to, co už v tabulce je
        stavejici_cenik = pd.read_csv(URL_CSV)
        stavejici_cenik['itemCode'] = stavejici_cenik['itemCode'].astype(str)
        # Odstraníme duplicity
        stavejici_cenik = stavejici_cenik.drop_duplicates(subset=['itemCode'], keep='last')
    except:
        stavejici_cenik = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # 2. VSTUPY NÁKLADŮ
    st.subheader("1. Fixní náklady")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketing (Kč):", value=0.0)
    doprava_faktura = c2.number_input("Doprava faktura (Kč):", value=0.0)

    # 3. NAHRÁNÍ OBJEDNÁVEK
    uploaded_file = st.file_uploader("2. Nahrajte orders.csv", type=['csv'])

    if uploaded_file:
        df_objednavky = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        df_objednavky['itemTotalPriceWithoutVat'] = pd.to_numeric(df_objednavky['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_objednavky['itemAmount'] = pd.to_numeric(df_objednavky['itemAmount'], errors='coerce').fillna(1)
        df_objednavky['itemCode'] = df_objednavky['itemCode'].astype(str)

        # Zjistíme, co všechno se v objednávkách prodalo
        produkty_v_objednavkach = df_objednavky.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        
        # Spojíme to se stávajícím ceníkem
        spojeny_cenik = pd.merge(produkty_v_objednavkach, stavejici_cenik, on='itemCode', how='left')
        spojeny_cenik['nakupni_cena'] = spojeny_cenik['nakupni_cena'].fillna(0.0)
        spojeny_cenik['koeficient'] = spojeny_cenik['koeficient'].fillna(1.0)

        st.write("### 📝 Kontrola a doplnění nákupních cen")
        st.info("Upravte ceny (nuly). Pro výpočet se použijí ceny z tabulky níže PRO VŠECHNY POLOŽKY.")
        
        # TABULKA PRO ÚPRAVU (Tady uživatel vidí všechno z objednávek)
        finalni_editor_df = st.data_editor(
            spojeny_cenik,
            column_config={
                "itemCode": "Kód",
                "itemName": "Název",
                "nakupni_cena": st.column_config.NumberColumn("NC bez DPH (Kč)", format="%.2f"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("🚀 SPOČÍTAT KOMPLETNÍ ZISK", type="primary"):
            # --- TADY JE TA OPRAVA ---
            # 1. Připravíme si "Master ceník" z toho, co je aktuálně v editoru na obrazovce
            master_cenik = finalni_editor_df[['itemCode', 'nakupni_cena', 'koeficient']].copy()
            
            # 2. PROPOJENÍ: Každý jeden řádek z orders.csv dostane svou NC z Master ceníku
            vypocet_df = pd.merge(df_objednavky, master_cenik, on='itemCode', how='left')
            
            # 3. Ošetření, kdyby se něco nepodařilo spárovat
            vypocet_df['nakupni_cena'] = vypocet_df['nakupni_cena'].fillna(0)
            vypocet_df['koeficient'] = vypocet_df['koeficient'].fillna(1)

            # 4. VÝPOČET NÁKLADŮ: Pro každý řádek (Množství * NC * Koeficient)
            vypocet_df['naklad_radek_celkem'] = vypocet_df['itemAmount'] * vypocet_df['nakupni_cena'] * vypocet_df['koeficient']

            # 5. SUMY
            total_trzby = vypocet_df['itemTotalPriceWithoutVat'].sum()
            total_naklady_zbozi = vypocet_df['naklad_radek_celkem'].sum()
            cisty_zisk = total_trzby - total_naklady_zbozi - mkt - doprava_faktura

            # Zobrazení výsledků
            st.divider()
            col1, col2, col3 = st.columns(3)
            col1.metric("Tržby celkem", f"{total_trzby:,.2f} Kč")
            col2.metric("Nákupní ceny celkem", f"{total_naklady_zbozi:,.2f} Kč")
            col3.metric("Čistý zisk", f"{cisty_zisk:,.2f} Kč")
            
            st.write("---")
            st.subheader("💡 Proč to teď sedí?")
            st.write(f"Výpočet proběhl u všech **{len(vypocet_df)}** řádků objednávek.")
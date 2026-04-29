import streamlit as st
import pandas as pd
import sqlite3

# --- KONFIGURACE HESLA ---
HESLO_PRO_VSTUP = "mojeheslo123" # <--- TADY SI ZMĚŇ HESLO

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

# --- 1. PŘÍPRAVA DATABÁZE ---
def init_db():
    conn = sqlite3.connect('pamet_cen.db')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cenik_v2 (
            itemCode TEXT PRIMARY KEY,
            nakupni_cena REAL,
            koeficient REAL
        )
    ''')
    conn.commit()
    return conn

# Spuštění aplikace
if check_password():
    st.set_page_config(page_title="Ziskovost E-shopu", layout="wide")
    st.title("💸 Výpočet ziskovosti e-shopu")

    # --- 2. VSTUPNÍ NÁKLADY ---
    st.subheader("1. Zadejte fixní náklady (bez DPH)")
    col1, col2 = st.columns(2)
    with col1:
        naklady_marketing = st.number_input("Náklady na marketing (Kč):", min_value=0.0, value=0.0)
    with col2:
        naklady_doprava = st.number_input("Faktura od dopravců za balíky (Kč):", min_value=0.0, value=0.0)

    # --- 3. NAHRÁNÍ DAT ---
    st.subheader("2. Nahrání objednávek")
    uploaded_file = st.file_uploader("Nahrajte export objednávek (orders.csv)", type=['csv'])

    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
        
        df['itemCode'] = df['itemCode'].astype(str)
        df.loc[df['itemCode'] == 'nan', 'itemCode'] = df['itemName'] 
        
        unikátní_produkty = df.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        
        # --- 4. PROPOJENÍ S PAMĚTÍ ---
        conn = init_db()
        pamet_df = pd.read_sql_query("SELECT * FROM cenik_v2", conn)
        
        spojeno = pd.merge(unikátní_produkty, pamet_df, on='itemCode', how='left')
        spojeno['nakupni_cena'] = spojeno['nakupni_cena'].fillna(0.0)
        spojeno['koeficient'] = spojeno['koeficient'].fillna(1.0)
        
        # NÁPOVĚDA (VRÁCENA ZPĚT)
        with st.expander("❓ TAHÁK: Jak funguje Nákupní cena a Koeficient?"):
            st.markdown("""
            **Většina produktů (1 ks na e-shopu = 1 ks od dodavatele):**
            Zadejte NC za 1 kus, koeficient nechte **1.0**.

            **Produkty na balení (např. 1 balení = 2.5 m²):**
            * Vaše NC od dodavatele je např. **300 Kč za 1 m²**. -> *(Do sloupce NC napíšete 300)*.
            * V jednom balení je **2.5 m²** podlahy. -> *(Do sloupce Koeficient napíšete 2.5)*.
            * Program spočítá náklad jako 300 × 2.5 = 750 Kč.
            """)

        # FILTRACE: Jen chybějící (NC=0) nebo balení (Koeficient != 1)
        k_uprave = spojeno[(spojeno['nakupni_cena'] == 0.0) | (spojeno['koeficient'] != 1.0)].copy()
        
        st.write("### 📝 Položky k doplnění nebo kontrole přepočtů")
        if not k_uprave.empty:
            opravena_data = st.data_editor(
                k_uprave[['itemCode', 'itemName', 'nakupni_cena', 'koeficient']],
                column_config={
                    "itemCode": "Kód",
                    "itemName": "Název položky",
                    "nakupni_cena": st.column_config.NumberColumn("NC (bez DPH)", min_value=0.0, format="%.2f"),
                    "koeficient": st.column_config.NumberColumn("Koeficient", min_value=0.0, format="%.2f")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.success("Všechny produkty jsou v pořádku (mají NC a jsou 1:1).")
            opravena_data = pd.DataFrame()

        st.divider()

        # --- 5. VÝPOČET ZISKU ---
        st.subheader("3. Výpočet")
        if st.button("Uložit změny a spočítat zisk", type="primary"):
            if not opravena_data.empty:
                for index, row in opravena_data.iterrows():
                    conn.execute('''
                        INSERT OR REPLACE INTO cenik_v2 (itemCode, nakupni_cena, koeficient)
                        VALUES (?, ?, ?)
                    ''', (row['itemCode'], row['nakupni_cena'], row['koeficient']))
                conn.commit()
            
            aktualni_pamet = pd.read_sql_query("SELECT * FROM cenik_v2", conn)
            df_konecne = pd.merge(df, aktualni_pamet, on='itemCode', how='left')
            df_konecne['nakupni_cena'] = df_konecne['nakupni_cena'].fillna(0.0)
            df_konecne['koeficient'] = df_konecne['koeficient'].fillna(1.0)
            
            df_konecne['naklad_celkem'] = df_konecne['itemAmount'] * df_konecne['nakupni_cena'] * df_konecne['koeficient']
            
            trzby = df_konecne['itemTotalPriceWithoutVat'].sum()
            naklady_zbozi = df_konecne['naklad_celkem'].sum()
            zisk = trzby - naklady_zbozi - naklady_marketing - naklady_doprava
            
            st.header("📊 Výsledky")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tržby", f"{trzby:,.0f} Kč".replace(',', ' '))
            c2.metric("Náklady zboží", f"{naklady_zbozi:,.0f} Kč".replace(',', ' '))
            c3.metric("Mkt + Doprava", f"{(naklady_marketing + naklady_doprava):,.0f} Kč".replace(',', ' '))
            st.success(f"### 💰 Čistý zisk: {zisk:,.0f} Kč".replace(',', ' '))
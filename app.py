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
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    div[data-testid="stExpander"] { border: 1px solid #e0e0e0; border-radius: 8px; background-color: white; }
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
    
    # --- PROPOJENÍ ---
    # Použijeme st.connection jen pokud máš nastavené Secrets, jinak jedeme přes CSV export (read-only)
    try:
        from streamlit_gsheets import GSheetsConnection
        conn = st.connection("gsheets", type=GSheetsConnection)
        gsheets_available = True
    except:
        gsheets_available = False

    # --- POŘÁDNÁ NÁPOVĚDA ---
    with st.expander("📖 INSTRUKCE PRO VEDENÍ (Přečtěte si před prvním použitím)"):
        st.markdown("""
        ### 1️⃣ Fixní náklady
        Zadejte náklady, které nejsou v exportu objednávek (typicky měsíční faktura za **Marketing** a celková faktura od **Dopravců** bez DPH).
        
        ### 2️⃣ Nahrání dat
        Nahrajte soubor `orders.csv`. Program automaticky projde tisíce řádků a přiřadí ke každému produktu nákupní cenu z paměti.
        
        ### 3️⃣ Kontrola a Koeficienty
        - **NC (Nákupní cena):** Pokud vidíte u produktu 0.00, znamená to, že ho systém nezná. Dopište cenu.
        - **Koeficient:** Slouží pro přepočet jednotek. 
            * *Příklad:* Prodáváte 1 balení dlažby (2.5 m²). Do NC napíšete cenu za 1 m² a koeficient dáte **2.5**. Program spočítá: `množství * 2.5 * NC`.
        
        ### 4️⃣ Výpočet a uložení
        Kliknutím na modré tlačítko se provede kompletní přepočet celého exportu. Pokud máte nastavené propojení, ceny se trvale uloží.
        """)

    # --- NAČTENÍ DAT ---
    with st.spinner('Načítám aktuální ceník z Google Disku...'):
        try:
            pamet_df = pd.read_csv(URL_CSV)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str)
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- SEKCE 1: NÁKLADY ---
    st.subheader("🛠️ 1. Nastavení fixních nákladů")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketingové náklady celkem (Kč bez DPH):", min_value=0.0, step=500.0, value=0.0)
    doprava_f = c2.number_input("Doprava celkem - faktura (Kč bez DPH):", min_value=0.0, step=500.0, value=0.0)

    # --- SEKCE 2: OBJEDNÁVKY ---
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte soubor orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění a konverze
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str)

        # Příprava tabulky unikátních produktů pro editor
        unikaty = df_obj.drop_duplicates(subset=['itemCode', 'itemName'])[['itemCode', 'itemName']].copy()
        merged_editor = pd.merge(unikaty, pamet_df, on='itemCode', how='left')
        merged_editor['nakupni_cena'] = merged_editor['nakupni_cena'].fillna(0.0)
        merged_editor['koeficient'] = merged_editor['koeficient'].fillna(1.0)

        st.subheader("📝 3. Kontrola nákupních cen pro tento export")
        st.info("Změny provedené v této tabulce se promítnou do celkového výpočtu.")
        
        # EDITOR S DATY
        ed_final = st.data_editor(
            merged_editor,
            column_config={
                "itemCode": "Kód produktu",
                "itemName": "Název položky",
                "nakupni_cena": st.column_config.NumberColumn("NC / Jednotku (Kč)", format="%.2f"),
                "koeficient": st.column_config.NumberColumn("Koeficient (přepočet)", format="%.2f")
            },
            hide_index=True,
            use_container_width=True,
            key="vstupni_editor"
        )

        if st.button("🚀 PROVÉST KOMPLETNÍ VÝPOČET", type="primary", use_container_width=True):
            with st.status("Provádím hloubkovou analýzu objednávek...", expanded=True) as status:
                
                # --- KLÍČOVÁ MATEMATIKA ---
                # 1. Připravíme si čistý ceník z editoru
                cisty_cenik = ed_final[['itemCode', 'nakupni_cena', 'koeficient']].copy()
                cisty_cenik['nakupni_cena'] = pd.to_numeric(cisty_cenik['nakupni_cena'], errors='coerce').fillna(0)
                cisty_cenik['koeficient'] = pd.to_numeric(cisty_cenik['koeficient'], errors='coerce').fillna(1)
                
                # 2. Spojíme se všemi řádky v objednávkách (X řádků v CSV = X NC výpočtů)
                # Tady probíhá to párování 1:1
                vypocet_all = df_obj.merge(cisty_cenik, on='itemCode', how='left')
                
                # 3. Výpočet nákladu na každou položku
                # Matika: Množství na řádku * Cena z ceníku * Koeficient
                vypocet_all['naklad_polozka'] = vypocet_all['itemAmount'] * vypocet_all['nakupni_cena'] * vypocet_all['koeficient']
                
                # 4. Agregace výsledků
                t_trzby = vypocet_all['itemTotalPriceWithoutVat'].sum()
                t_naklady_zbozi = vypocet_all['naklad_polozka'].sum()
                t_marze = t_trzby - t_naklady_zbozi
                t_zisk = t_marze - mkt - doprava_f

                time.sleep(1)
                status.update(label="Výpočet dokončen! Generuji přehled...", state="complete", expanded=False)

            # --- VIZUALIZACE VÝSLEDKŮ ---
            st.divider()
            st.header("📊 Finanční výsledky období")
            
            # Karty s výsledky
            res1, res2, res3, res4 = st.columns(4)
            res1.metric("CELKOVÉ TRŽBY", f"{t_trzby:,.0f} Kč".replace(',', ' '))
            res2.metric("NÁKLADY NA ZBOŽÍ", f"{t_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{t_naklady_zbozi:,.0f}", delta_color="inverse")
            res3.metric("HRUBÁ MARŽE", f"{t_marze:,.0f} Kč".replace(',', ' '))
            
            # Čistý zisk se zvýrazněním
            color = "normal" if t_zisk > 0 else "inverse"
            res4.metric("ČISTÝ ZISK", f"{t_zisk:,.0f} Kč".replace(',', ' '), delta=f"{t_zisk:,.0f} Kč", delta_color=color)

            # --- GRAFICKÉ UPOZORNĚNÍ ---
            if t_zisk > 0:
                st.balloons()
                st.success(f"Skvělá práce! E-shop je v zisku {t_zisk:,.0f} Kč.")
            else:
                st.error(f"Pozor! E-shop je v tomto období ve ztrátě {t_zisk:,.0f} Kč.")

            # --- ZÁPIS DO GOOGLE (POKUD JE SETUP) ---
            try:
                if gsheets_available:
                    # Sloučíme nová data s kompletní pamětí a uložíme
                    finalni_pamet_pro_disk = pd.concat([pamet_df, cisty_cenik]).drop_duplicates(subset=['itemCode'], keep='last')
                    conn.update(spreadsheet=URL_CSV, data=finalni_pamet_pro_disk)
                    st.toast("Ceny byly trvale uloženy do Google Tabulky.", icon="💾")
            except:
                st.warning("⚠️ Automatické uložení selhalo (chybí Service Account), ale výpočet je správný. Pro příště doporučujeme nahrát ceny přímo do Google Tabulky.")

            # --- DETAILNÍ ROZPIS ---
            with st.expander("🔍 Zobrazit detailní rozpis nákladů po položkách"):
                st.dataframe(
                    vypocet_all[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'naklad_polozka']]
                    .rename(columns={'itemTotalPriceWithoutVat': 'Tržba (ks)', 'naklad_polozka': 'Náklad celkem'}),
                    use_container_width=True
                )
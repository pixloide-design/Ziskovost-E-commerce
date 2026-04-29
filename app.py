import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Ziskovost E-shopu 2026", layout="wide")

# --- STYLING ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .stButton>button { width: 100%; height: 3.5em; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; }
    div[data-testid="stExpander"] { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený vstup")
    heslo = st.text_input("Zadejte heslo:", type="password")
    if st.button("PŘIHLÁSIT SE"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Chybné heslo!")
else:
    st.title("💰 Detailní analýza zisku")

    with st.expander("📖 PODROBNÝ MANUÁL (Přečíst!)"):
        st.markdown("""
        1. **Fixní náklady:** Zadejte sumu za Marketing a Dopravu (faktury od dopravců) bez DPH.
        2. **Import:** Nahrajte soubor `orders.csv`.
        3. **NC tabulka:** Zde uvidíte všechny produkty. Doprava a platba jsou automaticky vynechány.
        4. **Výpočet:** Program projde každý řádek v CSV. Pokud najde shodu kódu, odečte NC * množství * koeficient.
        """)

    # Načtení dat z Google
    try:
        pamet_df = pd.read_csv(URL_CSV)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    st.subheader("🛠️ 1. Fixní náklady")
    c1, c2 = st.columns(2)
    mkt = c1.number_input("Marketing celkem (Kč):", value=0.0, step=100.0)
    dopr_f = c2.number_input("Doprava faktura (Kč):", value=0.0, step=100.0)

    st.subheader("📂 2. Data z e-shopu")
    uploaded_file = st.file_uploader("Vyberte exportní soubor orders.csv", type=['csv'])

    if uploaded_file:
        # Načtení CSV (středník jako oddělovač dle tvého souboru)
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění sloupců
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str).str.strip()

        # Odstraníme řádky bez kódu (doprava, slevy atd. v exportu) pro ceník
        unikaty = df_obj[df_obj['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # Spojení s pamětí
        editor_df = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_df['nakupni_cena'] = editor_df['nakupni_cena'].fillna(0.0)
        editor_df['koeficient'] = editor_df['koeficient'].fillna(1.0)

        st.subheader("📝 3. Nastavení nákupních cen")
        st.info("Zde doplňte ceny. Ty se použijí pro VŠECHNY výskyty daného kódu v objednávkách.")
        
        # EDITOR
        final_editor = st.data_editor(
            editor_df,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC / ks (Kč)", format="%.2f"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True,
            key="hlavni_editor"
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT", type="primary"):
            with st.status("Analyzuji export a páruji ceny...", expanded=True):
                # 1. Získání cen z editoru (včetně změn)
                aktualni_ceny = editor_df.copy()
                state = st.session_state["hlavni_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_ceny.at[int(idx), col] = val

                # 2. Vyčištění exportu od starých nulových NC
                df_vypocet = df_obj.drop(columns=[c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns], errors='ignore')
                
                # 3. PÁROVÁNÍ 1:1 (Spojíme každou položku v CSV s ceníkem)
                final_merged = pd.merge(df_vypocet, aktualni_ceny[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # 4. VÝPOČET NÁKLADŮ (pouze tam, kde je kód)
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                final_merged['naklad_polozky'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # 5. SUMY
                total_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                total_nc = final_merged['naklad_polozky'].sum()
                total_zisk = total_trzby - total_nc - mkt - dopr_f

                time.sleep(1)

            # VÝSLEDKY
            st.divider()
            st.header("📊 Finanční výsledky")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("TRŽBY CELKEM", f"{total_trzby:,.0f} Kč")
            c2.metric("NÁKLADY ZBOŽÍ", f"{total_nc:,.0f} Kč", delta=f"-{total_nc:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_nc):,.0f} Kč")
            
            zisk_color = "normal" if total_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_zisk:,.0f} Kč", delta=f"{total_zisk:,.0f} Kč", delta_color=zisk_color)

            if total_zisk > 0: st.balloons()

            with st.expander("🔍 DETAILNÍ KONTROLA (Každý řádek z CSV)"):
                st.write("Zde vidíte, jakou NC program přiřadil ke každému řádku objednávky:")
                st.dataframe(final_merged[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'naklad_polozky']], use_container_width=True)

            # Uložení do Google
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                updated_db = pd.concat([pamet_df, aktualni_ceny[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=updated_db)
                st.toast("Ceny uloženy do Google Sheets!", icon="✅")
            except:
                st.info("💡 Automatické uložení vyžaduje Service Account.")
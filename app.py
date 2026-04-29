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
        3. **NC tabulka:** Zde doplňte **NÁKUPNÍ CENY**. Prodejní ceny si program bere sám z exportu.
        4. **Výpočet:** Program spočítá: `Tržba - (Množství * Nákupka * Koeficient) - Fixní náklady`.
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
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění sloupců z CSV
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str).str.strip()

        # Příprava editoru pro UNIKÁTNÍ produkty (vynecháme prázdné kódy jako doprava)
        unikaty = df_obj[df_obj['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # Spojení s pamětí NC
        editor_df = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_df['nakupni_cena'] = editor_df['nakupni_cena'].fillna(0.0)
        editor_df['koeficient'] = editor_df['koeficient'].fillna(1.0)

        st.subheader("📝 3. Zadání nákupních cen")
        st.info("Do sloupce 'nakupni_cena' zadejte vaše náklady na pořízení zboží.")
        
        # EDITOR
        final_editor = st.data_editor(
            editor_df,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NÁKUPNÍ CENA (NC) / ks", format="%.2f Kč"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True,
            key="hlavni_editor"
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT", type="primary"):
            with st.status("Počítám čistý zisk...", expanded=True):
                # 1. Získání NC z editoru
                aktualni_nc = editor_df.copy()
                state = st.session_state["hlavni_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_nc.at[int(idx), col] = val

                # 2. Příprava exportu (přejmenujeme původní NC sloupec z CSV, pokud tam je, aby nepřekážel)
                df_vypocet = df_obj.copy()
                if 'nakupni_cena' in df_vypocet.columns:
                    df_vypocet = df_vypocet.rename(columns={'nakupni_cena': 'puvodni_nc_export'})

                # 3. PÁROVÁNÍ NC K PRODEJŮM
                final_merged = pd.merge(df_vypocet, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # 4. VÝPOČET NÁKLADU NA ZBOŽÍ
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                
                # Celkový nákupní náklad = Množství * NC * Koeficient
                final_merged['total_nc_row'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # 5. SUMY
                total_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                total_naklady_zbozi = final_merged['total_nc_row'].sum()
                total_cisty_zisk = total_trzby - total_naklady_zbozi - mkt - dopr_f

                time.sleep(1)

            # VÝSLEDKY
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("TRŽBY CELKEM", f"{total_trzby:,.0f} Kč")
            c2.metric("NÁKLADY ZBOŽÍ (NC)", f"{total_naklady_zbozi:,.0f} Kč", delta=f"-{total_naklady_zbozi:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_naklady_zbozi):,.0f} Kč")
            
            zisk_color = "normal" if total_cisty_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_cisty_zisk:,.0f} Kč", delta=f"{total_cisty_zisk:,.0f} Kč", delta_color=zisk_color)

            if total_cisty_zisk > 0: st.balloons()

            with st.expander("🔍 DETAILNÍ KONTROLA (Prodejní cena vs Nákupní cena)"):
                # Přejmenování pro přehlednost vedení
                check_df = final_merged[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'total_nc_row']].copy()
                check_df.columns = ['Kód', 'Název', 'Množství', 'TRŽBA (Prodejní)', 'NC / ks', 'NÁKLAD CELKEM (NC)']
                st.dataframe(check_df, use_container_width=True)

            # Uložení NC do Google
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                updated_db = pd.concat([pamet_df, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=updated_db)
                st.toast("Nákupní ceny uloženy!", icon="✅")
            except:
                st.info("💡 Pro uložení nastavte Service Account.")
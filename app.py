import streamlit as st
import pandas as pd
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Ziskovost E-shopu | PRO verze", layout="wide")

# --- STYLING ---
st.markdown("""
    <style>
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton>button { width: 100%; height: 4em; font-weight: bold; background-color: #007bff; color: white; border-radius: 10px; font-size: 1.1em; }
    div[data-testid="stExpander"] { background-color: white; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- ZABEZPEČENÍ ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený manažerský panel")
    heslo = st.text_input("Vložte přístupové heslo:", type="password")
    if st.button("PŘIHLÁSIT SE"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Neplatné heslo!")
else:
    st.title("💰 Detailní analýza zisku a nákladů")

    # --- NÁPOVĚDA ---
    with st.expander("📖 NÁVOD: Jak zajistit, aby výpočet fungoval?"):
        st.markdown("""
        1. **Fixní náklady:** Vyplňte Marketing a Dopravu (celkové faktury bez DPH).
        2. **Nahrání:** Vložte soubor `orders.csv`.
        3. **Zadání NC (Zásadní krok):** - V tabulce níže uvidíte všechny unikátní položky.
           - **Musíte ručně přepsat ty nuly v sloupci NC / ks na vaše skutečné nákupní ceny.**
           - Jakmile tam napíšete číslo, program jej použije pro všechny prodané kusy daného kódu.
        4. **Výpočet:** Klikněte na tlačítko. Program odečte (NC * Množství) od Prodejní ceny.
        """)

    # Načtení paměti z Google
    try:
        pamet_df = pd.read_csv(URL_CSV)
        pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
    except:
        pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    st.subheader("🛠️ 1. Fixní náklady období")
    col_a, col_b = st.columns(2)
    mkt = col_a.number_input("Marketing celkem (Kč bez DPH):", min_value=0.0, step=100.0)
    dopr_f = col_b.number_input("Doprava faktura (Kč bez DPH):", min_value=0.0, step=100.0)

    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Čištění a příprava dat z exportu
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str).str.strip()

        # Příprava tabulky unikátních položek (bez dopravy/plateb bez kódu)
        unikaty = df_obj[df_obj['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # Spojení s databází NC
        editor_df = pd.merge(unikaty, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        editor_df['nakupni_cena'] = editor_df['nakupni_cena'].fillna(0.0)
        editor_df['koeficient'] = editor_df['koeficient'].fillna(1.0)

        st.subheader("📝 3. Zadání nákupních cen (NC)")
        st.info("⚠️ Pokud uvidíte NC 0.00, přepište ji na skutečnou nákupní cenu, jinak bude zisk chybný!")
        
        # EDITOR S KLÍČEM
        final_editor_df = st.data_editor(
            editor_df,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC / ks (Kč bez DPH)", format="%.2f", min_value=0.0),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True,
            key="vstup_editor"
        )

        if st.button("🚀 SPOČÍTAT ZISK A ULOŽIT CENY", type="primary"):
            with st.status("Analyzuji tisíce řádků a přiřazuji NC...", expanded=True):
                
                # --- EXTRAKCE CEN Z EDITORU ---
                # Tohle natvrdo vezme to, co jsi do tabulky napsal
                ceny_z_tabulky = final_editor_df.copy()
                state = st.session_state["vstup_editor"]
                if "edited_rows" in state:
                    for idx_str, changes in state["edited_rows"].items():
                        idx = int(idx_str)
                        for col, val in changes.items():
                            ceny_z_tabulky.at[idx, col] = val

                # --- PÁROVÁNÍ NA EXPORT ---
                # Vymažeme staré sloupce, pokud existují
                df_calc = df_obj.drop(columns=[c for c in ['nakupni_cena', 'koeficient'] if c in df_obj.columns], errors='ignore')
                
                # Propojíme prodejní řádky s tvými nákupními cenami
                vypocet_all = pd.merge(df_calc, ceny_z_tabulky[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # --- VÝPOČET ---
                vypocet_all['nakupni_cena'] = pd.to_numeric(vypocet_all['nakupni_cena']).fillna(0)
                vypocet_all['koeficient'] = pd.to_numeric(vypocet_all['koeficient']).fillna(1)
                
                # Náklad řádku = Množství * NC * Koeficient
                vypocet_all['naklad_radek'] = vypocet_all['itemAmount'] * vypocet_all['nakupni_cena'] * vypocet_all['koeficient']

                # Sumy
                total_trzby = vypocet_all['itemTotalPriceWithoutVat'].sum()
                total_nc = vypocet_all['naklad_radek'].sum()
                total_zisk = total_trzby - total_nc - mkt - dopr_f
                
                time.sleep(1)

            # --- VIZUALIZACE ---
            st.divider()
            st.header("📊 Výsledky analýzy")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("TRŽBY", f"{total_trzby:,.0f} Kč")
            # TADY UŽ NESMÍ BÝT NULA
            c2.metric("NÁKLADY ZBOŽÍ", f"{total_nc:,.0f} Kč", delta=f"-{total_nc:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_nc):,.0f} Kč")
            
            p_color = "normal" if total_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_zisk:,.0f} Kč", delta=f"{total_zisk:,.0f} Kč", delta_color=p_color)

            if total_zisk > 0: st.balloons()

            with st.expander("🔍 DETAILNÍ ROZPIS (Zkontrolujte si NC u každého řádku)"):
                st.dataframe(
                    vypocet_all[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']]
                    .rename(columns={'itemTotalPriceWithoutVat': 'Prodejní tržba', 'naklad_radek': 'Nákupní náklad'}),
                    use_container_width=True
                )

            # --- ULOŽENÍ ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                update_final = pd.concat([pamet_df, ceny_z_tabulky[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV, data=update_final)
                st.toast("Ceny uloženy do Google Sheets!", icon="✅")
            except:
                st.info("💡 Automatické uložení vyžaduje Service Account v Secrets.")
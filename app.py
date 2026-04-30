import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Ziskovost E-shopu | PRO", page_icon="📈", layout="wide")

# --- STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f4f6f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton>button { width: 100%; height: 3.5em; font-weight: bold; background-color: #0066cc; color: white; border-radius: 8px; font-size: 1.1em; transition: 0.3s; }
    .stButton>button:hover { background-color: #004c99; box-shadow: 0 4px 10px rgba(0,0,0,0.15); }
    div[data-testid="stExpander"] { background-color: white; border-radius: 10px; border: 1px solid #e0e0e0; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE DAT ---
HESLO_PRO_VSTUP = "mojeheslo123" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV_GSHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
XML_FEED_URL = "https://eshop.superpodlaha.cz/export/productsComplete.xml?patternId=-5&partnerId=6&hash=2f7d22f13d30329b53e8cfb4937eb14143c5e09ec1adaea045d098e7248dbfaa"

# --- CACHE PRO XML FEED (Nyní i s konverzí DPH) ---
@st.cache_data(ttl=3600)
def load_xml_feed(url, dph_sazba=21, ceny_s_dph=True):
    try:
        clean_url = str(url).strip()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(clean_url, headers=headers, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        xml_data = []
        dph_delitel = (1 + (dph_sazba / 100)) if ceny_s_dph else 1.0
        
        # Procházení XML
        for item in root.findall('.//SHOPITEM'):
            main_code = item.findtext('CODE')
            if not main_code:
                main_code = item.findtext('ITEM_ID')
                
            main_price = item.findtext('PURCHASE_PRICE')
            
            # Zpracování ceny hlavního produktu
            if main_code and main_price:
                try:
                    cista_nc = float(main_price) / dph_delitel
                    xml_data.append({'itemCode': str(main_code).strip(), 'nc_xml': cista_nc})
                except:
                    pass
                    
            # Zpracování VARIANT
            for variant in item.findall('.//VARIANT'):
                var_code = variant.findtext('CODE')
                var_price = variant.findtext('PURCHASE_PRICE')
                
                if not var_price:
                    var_price = main_price
                    
                if var_code and var_price:
                    try:
                        cista_nc_var = float(var_price) / dph_delitel
                        xml_data.append({'itemCode': str(var_code).strip(), 'nc_xml': cista_nc_var})
                    except:
                        pass
        
        df_xml = pd.DataFrame(xml_data)
        if not df_xml.empty:
            df_xml = df_xml.drop_duplicates(subset=['itemCode'], keep='last')
        return df_xml
    except Exception as e:
        st.error(f"⚠️ Chyba při stahování XML feedu: {e}")
        return pd.DataFrame(columns=['itemCode', 'nc_xml'])

# --- ZABEZPEČENÍ ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený přístup k financím")
    heslo = st.text_input("Zadejte heslo:", type="password")
    if st.button("VSTOUPIT"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Chybné heslo!")
else:
    st.title("💰 Inteligentní analýza zisku")

    with st.expander("📖 JAK SYSTÉM FUNGUJE (Rozklikni)"):
        st.markdown("""
        1. **DPH Korekce:** Tržby počítáme z CSV *bez DPH*. XML feed z e-shopu stahuje nákupní ceny *s DPH*. Program proto z XML cen DPH odečte.
        2. **Automatika:** Systém najde nákupní ceny i u variant (metráže atd.).
        3. **Doplnění:** V tabulce dole doplňte produkty s NC 0.00. **Zadávejte NC vždy BEZ DPH!**
        4. **Výpočet:** Program vezme Tržbu bez DPH a odečte (NC bez DPH x Množství).
        """)

    # Nastavení DPH pro XML
    st.sidebar.header("⚙️ Nastavení XML Feedu")
    xml_ceny_s_dph = st.sidebar.checkbox("Nákupní ceny ve feedu (v administraci) jsou vč. DPH", value=True)
    dph_sazba_xml = st.sidebar.number_input("Sazba DPH (%) pro nákupní ceny:", value=21.0, step=1.0)

    # 1. Načtení dat z Google a XML
    with st.spinner("Stahuji a přepočítávám data z e-shopu..."):
        df_xml = load_xml_feed(XML_FEED_URL, dph_sazba=dph_sazba_xml, ceny_s_dph=xml_ceny_s_dph)
        try:
            pamet_df = pd.read_csv(URL_CSV_GSHEETS)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # 2. Vstupy fixních nákladů
    st.subheader("🛠️ 1. Fixní náklady období")
    col1, col2 = st.columns(2)
    mkt_cost = col1.number_input("Marketing (Kč bez DPH):", min_value=0.0, step=100.0)
    doprava_cost = col2.number_input("Doprava - faktury (Kč bez DPH):", min_value=0.0, step=100.0)

    # 3. Import objednávek
    st.subheader("📂 2. Nahrání exportu objednávek")
    uploaded_file = st.file_uploader("Nahrajte orders.csv", type=['csv'])

    if uploaded_file:
        df_obj = pd.read_csv(uploaded_file, sep=';', decimal=',', encoding='cp1250')
        
        # Očištění exportu (Zásadní: tržba BEZ DPH)
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str).str.strip()

        # Unikátní produkty
        unikaty = df_obj[df_obj['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # PROPOJENÍ: Objednávky + XML (očistěné od DPH) + Google Tabulka
        editor_prep = pd.merge(unikaty, df_xml, on='itemCode', how='left')
        editor_prep = pd.merge(editor_prep, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        
        # Priorita cen: 1. Ručně zadaná v Google, 2. XML Feed (už bez DPH), 3. Nula
        editor_prep['finalni_nc'] = editor_prep['nakupni_cena'].fillna(editor_prep['nc_xml']).fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)
        
        # Finální tabulka
        tabulka_pro_editor = editor_prep[['itemCode', 'itemName', 'finalni_nc', 'koeficient']].copy()
        tabulka_pro_editor.rename(columns={'finalni_nc': 'nakupni_cena'}, inplace=True)

        st.subheader("📝 3. Kontrola nákupních cen (BEZ DPH)")
        st.info("💡 Všechny ceny v této tabulce jsou již přepočtené na hodnoty **BEZ DPH**. Pokud doplňujete nuly, zadávejte také cenu BEZ DPH.")
        
        # Nuly řadíme nahoře
        tabulka_pro_editor = tabulka_pro_editor.sort_values(by=['nakupni_cena', 'itemName'], ascending=[True, True]).reset_index(drop=True)

        # EDITOR
        final_editor = st.data_editor(
            tabulka_pro_editor,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NC / ks (BEZ DPH)", format="%.2f Kč"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True,
            key="cenovy_editor"
        )

        if st.button("🚀 SPOČÍTAT FINÁLNÍ ZISK A ULOŽIT", type="primary"):
            with st.status("Počítám zisk ze všech položek...", expanded=True) as status:
                
                # Získání dat z editoru
                aktualni_nc = tabulka_pro_editor.copy()
                state = st.session_state["cenovy_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_nc.at[int(idx), col] = val

                # Čištění CSV od případných starých NC
                df_vypocet = df_obj.copy()
                if 'nakupni_cena' in df_vypocet.columns:
                    df_vypocet = df_vypocet.rename(columns={'nakupni_cena': 'nc_stara_z_csv'})

                # SPÁROVÁNÍ
                final_merged = pd.merge(df_vypocet, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # MATEMATIKA NÁKLADŮ
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                
                # NÁKLAD BEZ DPH = Množství * NC (bez DPH) * Koeficient
                final_merged['naklad_radek'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # SOUČTY (Tržba bez DPH - Náklad bez DPH)
                total_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                total_naklady_zbozi = final_merged['naklad_radek'].sum()
                total_cisty_zisk = total_trzby - total_naklady_zbozi - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Analýza úspěšná!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("TRŽBY CELKEM (bez DPH)", f"{total_trzby:,.0f} Kč".replace(',', ' '))
            c2.metric("NÁKLADY ZBOŽÍ (bez DPH)", f"{total_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{total_naklady_zbozi:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_naklady_zbozi):,.0f} Kč".replace(',', ' '))
            
            barva = "normal" if total_cisty_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_cisty_zisk:,.0f} Kč".replace(',', ' '), delta=f"{total_cisty_zisk:,.0f} Kč", delta_color=barva)

            if total_cisty_zisk > 0:
                st.balloons()
            else:
                st.error("Pozor, období končí ve ztrátě!")

            # --- ROZPIS PO POLOŽKÁCH ---
            with st.expander("🔍 DETAILNÍ ROZPIS (Tržba bez DPH vs Náklad bez DPH)"):
                kontrola_df = final_merged[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']].copy()
                kontrola_df.columns = ['Kód', 'Produkt', 'Množství', 'TRŽBA (bez DPH)', 'NC / ks (bez DPH)', 'NÁKLAD (Celkem)']
                st.dataframe(kontrola_df, use_container_width=True)

            # --- ULOŽENÍ DO GOOGLE SHEETS ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                # Ukládáme očištěné ceny (bez DPH)
                k_ulozeni = aktualni_nc[aktualni_nc['nakupni_cena'] > 0]
                update_db = pd.concat([pamet_df, k_ulozeni[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV_GSHEETS, data=update_db)
                st.toast("Ceny uloženy do Google Tabulky!", icon="💾")
            except Exception as e:
                pass
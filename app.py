import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import time
from io import StringIO
import re

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(page_title="Ziskovost E-shopu | PRO", page_icon="📈", layout="wide")

# --- STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f4f6f9; }
    .stMetric { background-color: #ffffff; padding: 20px; border-radius: 12px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
    .stButton>button { width: 100%; height: 3.5em; font-weight: bold; background-color: #0066cc; color: white; border-radius: 8px; font-size: 1.1em; transition: 0.3s; }
    .stButton>button:hover { background-color: #004c99; box-shadow: 0 4px 10px rgba(0,0,0,0.15); }
    div[data-testid="stExpander"] { background-color: white; border-radius: 10px; border: 1px solid #e0e0e0; margin-bottom: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- KONFIGURACE DAT A URL ---
HESLO_PRO_VSTUP = "KoberceAdamSuperpodlaha2026MiraSedaXX22XX25" 
SHEET_ID = "1KQXP_5hkEBOXUDLMZR1CdSsdMf8BU72kPxEFaXdNjSY"
URL_CSV_GSHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
XML_FEED_URL = "https://eshop.superpodlaha.cz/export/productsComplete.xml?patternId=-5&partnerId=6&hash=2f7d22f13d30329b53e8cfb4937eb14143c5e09ec1adaea045d098e7248dbfaa"
ORDERS_CSV_URL = "https://eshop.superpodlaha.cz/export/orders.csv?patternId=-9&partnerId=6&hash=39a4ee9904e1b2fecd432faddac364a49291288ba4f616285a5d1c6ee147d716"

# --- POMOCNÉ FUNKCE (Čištění datumu a čísel) ---
def extract_month(d):
    m_iso = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', str(d))
    if m_iso: return float(m_iso.group(2))
    m_cz = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', str(d))
    if m_cz: return float(m_cz.group(2))
    return None
    
def extract_year(d):
    m_iso = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', str(d))
    if m_iso: return float(m_iso.group(1))
    m_cz = re.search(r'(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})', str(d))
    if m_cz: return float(m_cz.group(3))
    return None

def clean_money(column_data):
    # Vymaže prázdné mezery u tisíců (1 500,00 -> 1500.00) a převede na číslo
    cleaned = column_data.astype(str).str.replace(r'\s+', '', regex=True).str.replace(',', '.')
    return pd.to_numeric(cleaned, errors='coerce').fillna(0)

# --- CACHE: XML FEED ---
@st.cache_data(ttl=3600)
def load_xml_feed(url, dph_sazba=21, ceny_s_dph=True):
    try:
        clean_url = str(url).strip()
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(clean_url, headers=headers, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        xml_data = []
        dph_delitel = (1 + (dph_sazba / 100)) if ceny_s_dph else 1.0
        
        for item in root.findall('.//SHOPITEM'):
            main_code = item.findtext('CODE') or item.findtext('ITEM_ID')
            main_price = item.findtext('PURCHASE_PRICE')
            
            if main_code and main_price:
                try:
                    cista_nc = float(main_price) / dph_delitel
                    xml_data.append({'itemCode': str(main_code).strip(), 'nc_xml': cista_nc})
                except: pass
                    
            for variant in item.findall('.//VARIANT'):
                var_code = variant.findtext('CODE')
                var_price = variant.findtext('PURCHASE_PRICE') or main_price
                if var_code and var_price:
                    try:
                        cista_nc_var = float(var_price) / dph_delitel
                        xml_data.append({'itemCode': str(var_code).strip(), 'nc_xml': cista_nc_var})
                    except: pass
        
        df_xml = pd.DataFrame(xml_data)
        if not df_xml.empty:
            df_xml = df_xml.drop_duplicates(subset=['itemCode'], keep='last')
        return df_xml
    except Exception as e:
        st.error(f"⚠️ Chyba při stahování XML feedu: {e}")
        return pd.DataFrame(columns=['itemCode', 'nc_xml'])

# --- CACHE: EXPORT OBJEDNÁVEK (S OBLBNUTÍM SHOPTET CACHE) ---
@st.cache_data(ttl=60)
def load_orders(url):
    try:
        # Cache Buster: Přidáme aktuální čas do URL, aby Shoptet nemohl poslat stará data
        clean_url = f"{str(url).strip()}&timestamp={int(time.time())}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(clean_url, headers=headers, timeout=45)
        response.raise_for_status()
        response.encoding = 'cp1250' # Natvrdo vynutíme české Windows kódování
        
        df = pd.read_csv(StringIO(response.text), sep=';', decimal=',', quotechar='"', on_bad_lines='skip', low_memory=False)
        
        df['itemTotalPriceWithoutVat'] = clean_money(df['itemTotalPriceWithoutVat'])
        df['itemAmount'] = clean_money(df['itemAmount'])
        df['itemCode'] = df['itemCode'].astype(str).str.strip()
        
        if 'date' in df.columns:
            df['date_str'] = df['date'].astype(str).str.strip().str.replace('"', '')
            df['rok'] = df['date_str'].apply(extract_year)
            df['mesic'] = df['date_str'].apply(extract_month)
        return df
    except Exception as e:
        st.error(f"⚠️ Chyba při automatickém stahování objednávek: {e}")
        return pd.DataFrame()

# --- ZABEZPEČENÍ APLIKACE ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Zabezpečený přístup")
    heslo = st.text_input("Zadejte přístupový kód:", type="password")
    if st.button("VSTOUPIT DO SYSTÉMU"):
        if heslo == HESLO_PRO_VSTUP:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("❌ Chybné heslo! Zkuste to znovu.")
else:
    # --- HLAVNÍ APLIKACE ---
    st.title("💰 Plně automatizovaná analýza zisku")

    with st.expander("📖 JAK SYSTÉM FUNGUJE"):
        st.markdown("""
        1. **Zdroj dat:** Aplikace bere data tajným odkazem. Pokud odkaz stagnuje, nahrajte soubor ručně do políčka níže.
        2. **DPH Korekce:** Tržby se počítají z objednávek *bez DPH*. Nákupní ceny se očistí od DPH podle nastavení vlevo.
        3. **Filtry:** Vyberte si Rok, Měsíc a odfiltrujte storna (Stornováno se vyřadí automaticky).
        4. **Doplnění NC:** V tabulce doplňte chybějící ceny (NC 0.00). **Ceny zadávejte BEZ DPH.**
        """)

    # --- SIDEBAR ---
    st.sidebar.header("⚙️ Nastavení datového feedu")
    xml_ceny_s_dph = st.sidebar.checkbox("Ceny z administrace e-shopu jsou vč. DPH", value=True)
    dph_sazba_xml = st.sidebar.number_input("Sazba DPH (%):", value=21.0, step=1.0)
    
    if st.sidebar.button("🔄 VYNUTIT AKTUALIZACI DAT"):
        st.cache_data.clear()
        st.rerun()

    # --- 1. NAČTENÍ DAT ---
    with st.spinner("Stahuji a zpracovávám kompletní data (může chvíli trvat)..."):
        df_xml = load_xml_feed(XML_FEED_URL, dph_sazba=dph_sazba_xml, ceny_s_dph=xml_ceny_s_dph)
        try:
            pamet_df = pd.read_csv(URL_CSV_GSHEETS)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    st.subheader("📂 1. Zdroj dat (Objednávky)")
    uploaded_file = st.file_uploader("Volitelné: Nahrát CSV s objednávkami ručně (přepíše automatické API)", type=['csv'])

    if uploaded_file:
        df_vsechny_objednavky = pd.read_csv(uploaded_file, sep=';', decimal=',', quotechar='"', on_bad_lines='skip', low_memory=False, encoding='cp1250')
        df_vsechny_objednavky['itemTotalPriceWithoutVat'] = clean_money(df_vsechny_objednavky['itemTotalPriceWithoutVat'])
        df_vsechny_objednavky['itemAmount'] = clean_money(df_vsechny_objednavky['itemAmount'])
        df_vsechny_objednavky['itemCode'] = df_vsechny_objednavky['itemCode'].astype(str).str.strip()
        
        if 'date' in df_vsechny_objednavky.columns:
            df_vsechny_objednavky['date_str'] = df_vsechny_objednavky['date'].astype(str).str.strip().str.replace('"', '')
            df_vsechny_objednavky['rok'] = df_vsechny_objednavky['date_str'].apply(extract_year)
            df_vsechny_objednavky['mesic'] = df_vsechny_objednavky['date_str'].apply(extract_month)
        st.success("Data načtena ručně ze souboru!")
    else:
        df_vsechny_objednavky = load_orders(ORDERS_CSV_URL)

    # --- 2. VÝBĚR OBDOBÍ A NÁKLADŮ ---
    st.subheader("📅 2. Výběr období a fixních nákladů")
    
    if not df_vsechny_objednavky.empty and 'rok' in df_vsechny_objednavky.columns:
        roky = sorted(df_vsechny_objednavky['rok'].dropna().unique().astype(int).tolist(), reverse=True)
        mesice = sorted(df_vsechny_objednavky['mesic'].dropna().unique().astype(int).tolist())
        
        col_r, col_m, col_mkt, col_dop = st.columns(4)
        if not roky: roky = [pd.Timestamp.now().year]
        if not mesice: mesice = list(range(1, 13))
        
        vybrany_rok = col_r.selectbox("Rok:", roky)
        
        current_month = pd.Timestamp.now().month
        default_month_idx = mesice.index(current_month) if current_month in mesice else 0
        vybrany_mesic = col_m.selectbox("Měsíc:", mesice, index=default_month_idx)
        
        mkt_cost = col_mkt.number_input("Marketing (bez DPH):", min_value=0.0, step=100.0)
        doprava_cost = col_dop.number_input("Doprava faktury (bez DPH):", min_value=0.0, step=100.0)
        
        stavy = []
        if 'statusName' in df_vsechny_objednavky.columns:
            stavy = sorted(df_vsechny_objednavky['statusName'].dropna().unique().tolist())
            # Zajištění proti paznakům
            default_stavy = [s for s in stavy if "storno" not in str(s).lower() and "zru" not in str(s).lower()]
            vybrane_stavy = st.multiselect("Filtrovat stavy objednávek (vyřaďte storna atd.):", stavy, default=default_stavy)
        
        df_filtr = df_vsechny_objednavky[(df_vsechny_objednavky['rok'] == float(vybrany_rok)) & (df_vsechny_objednavky['mesic'] == float(vybrany_mesic))]
        
        if 'statusName' in df_vsechny_objednavky.columns and vybrane_stavy:
            df_filtr = df_filtr[df_filtr['statusName'].isin(vybrane_stavy)]

    else:
        st.error("Nepodařilo se načíst data o datumech z e-shopu. Použijte manuální nahrání.")
        st.stop()

    if df_filtr.empty:
        st.warning(f"V období {vybrany_mesic}/{vybrany_rok} nejsou evidovány žádné platné objednávky. Zkontrolujte stavy objednávek.")
    else:
        # --- 3. KONTROLA CEN ---
        unikaty = df_filtr[df_filtr['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        editor_prep = pd.merge(unikaty, df_xml, on='itemCode', how='left')
        editor_prep = pd.merge(editor_prep, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        
        editor_prep['finalni_nc'] = editor_prep['nakupni_cena'].fillna(editor_prep['nc_xml']).fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)
        
        tabulka_pro_editor = editor_prep[['itemCode', 'itemName', 'finalni_nc', 'koeficient']].copy()
        tabulka_pro_editor.rename(columns={'finalni_nc': 'nakupni_cena'}, inplace=True)

        st.subheader("📝 3. Kontrola nákupních cen (BEZ DPH)")
        st.info(f"Produkty prodané v {vybrany_mesic}/{vybrany_rok}. Pokud chybí NC (0.00), doplňte ji.")
        
        tabulka_pro_editor = tabulka_pro_editor.sort_values(by=['nakupni_cena', 'itemName'], ascending=[True, True]).reset_index(drop=True)

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

        # --- 4. FINÁLNÍ VÝPOČET ---
        if st.button("🚀 SPOČÍTAT ZISK ZA VYBRANÝ MĚSÍC A ULOŽIT", type="primary"):
            with st.status(f"Zpracovávám data pro {vybrany_mesic}/{vybrany_rok}...", expanded=True) as status:
                
                aktualni_nc = tabulka_pro_editor.copy()
                state = st.session_state["cenovy_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_nc.at[int(idx), col] = val

                df_vypocet = df_filtr.copy()
                if 'nakupni_cena' in df_vypocet.columns:
                    df_vypocet = df_vypocet.rename(columns={'nakupni_cena': 'nc_stara_z_csv'})

                final_merged = pd.merge(df_vypocet, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                final_merged['naklad_radek'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                total_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                total_naklady_zbozi = final_merged['naklad_radek'].sum()
                total_cisty_zisk = total_trzby - total_naklady_zbozi - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Kompletně spočítáno!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"TRŽBY ({vybrany_mesic}/{vybrany_rok})", f"{total_trzby:,.0f} Kč".replace(',', ' '))
            c2.metric("NÁKLADY ZBOŽÍ (bez DPH)", f"{total_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{total_naklady_zbozi:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_naklady_zbozi):,.0f} Kč".replace(',', ' '))
            
            barva = "normal" if total_cisty_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_cisty_zisk:,.0f} Kč".replace(',', ' '), delta=f"{total_cisty_zisk:,.0f} Kč", delta_color=barva)

            if total_cisty_zisk > 0:
                st.balloons()
            else:
                st.error("Vybraný měsíc končí ve ztrátě!")

            # --- ROZPIS PO POLOŽKÁCH ---
            with st.expander("🔍 DETAILNÍ ROZPIS (Tržba bez DPH vs Náklad bez DPH)"):
                kontrola_df = final_merged[['itemCode', 'itemName', 'statusName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']].copy()
                kontrola_df.columns = ['Kód', 'Produkt', 'Stav', 'Množství', 'TRŽBA (bez DPH)', 'NC / ks (bez DPH)', 'NÁKLAD (Celkem)']
                st.dataframe(kontrola_df, use_container_width=True)

            # --- ULOŽENÍ DO GOOGLE SHEETS ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                k_ulozeni = aktualni_nc[aktualni_nc['nakupni_cena'] > 0]
                update_db = pd.concat([pamet_df, k_ulozeni[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV_GSHEETS, data=update_db)
                st.toast("Změny cen byly uloženy do databáze!", icon="💾")
            except Exception as e:
                pass
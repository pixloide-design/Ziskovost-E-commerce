import streamlit as st
import pandas as pd
import numpy as np  # <-- PŘIDÁNO PRO BEZPEČNÉ VÝPOČTY (Dělení nulou u %)
import requests
import xml.etree.ElementTree as ET
import time
from io import StringIO, BytesIO
import re
from fpdf import FPDF
import unicodedata

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
try:
    HESLO_PRO_VSTUP = st.secrets["eshop"]["HESLO_PRO_VSTUP"]
    SHEET_ID = st.secrets["eshop"]["SHEET_ID"]
    URL_CSV_GSHEETS = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"
    XML_FEED_URL = st.secrets["eshop"]["XML_FEED_URL"]
    ORDERS_CSV_URL = st.secrets["eshop"]["ORDERS_CSV_URL"]
except KeyError as e:
    st.error(f"❌ Chybí bezpečnostní nastavení (Secrets) ve Streamlitu pro klíč: {e}")
    st.stop()

# --- POMOCNÉ FUNKCE ---
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
    cleaned = column_data.astype(str).str.replace('"', '').str.replace(r'[\s\xa0]+', '', regex=True).str.replace(',', '.')
    return pd.to_numeric(cleaned, errors='coerce').fillna(0.0)

# --- FUNKCE PRO PDF (Praha) ---
def remove_accents(input_str):
    """Odstraní diakritiku pro bezpečný export do základního PDF fontu."""
    if not isinstance(input_str, str): return str(input_str)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return u"".join([c for c in nfkd_form if not unicodedata.combining(c)])

def create_praha_dashboard_pdf(data_a, data_b, label_a, label_b, obdobi_text):
    """Vygeneruje PDF report porovnávající dvě konkrétní vybraná období."""
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    
    # Hlavička
    pdf.set_font("helvetica", "B", 18)
    pdf.cell(0, 10, remove_accents("SROVNAVACI REPORT PRODEJU: PRAHA"), ln=True, align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 7, remove_accents(f"Vygenerovano: {time.strftime('%d.%m.%Y')} | {obdobi_text}"), ln=True, align="C")
    pdf.ln(10)

    def vloz_sekci(titulek, d_a, d_b):
        pdf.set_font("helvetica", "B", 14)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(0, 10, remove_accents(titulek), ln=True, fill=True)
        pdf.ln(4)
        
        # Data pro Období A
        t_a = d_a['itemTotalPriceWithoutVat'].sum()
        p_a = d_a['code'].nunique()
        
        # Data pro Období B
        t_b = d_b['itemTotalPriceWithoutVat'].sum()
        p_b = d_b['code'].nunique()
        
        # Výpočet změny
        zmena = ((t_b - t_a) / t_a * 100) if t_a > 0 else 0
        znamenko = "+" if zmena > 0 else ""

        pdf.set_font("helvetica", "B", 11)
        pdf.cell(95, 8, remove_accents(f"OBDOBI A ({label_a})"))
        pdf.cell(95, 8, remove_accents(f"OBDOBI B ({label_b})"))
        pdf.ln()
        
        pdf.set_font("helvetica", "", 11)
        pdf.cell(95, 7, f"Trzby: {t_a:,.0f} CZK / {p_a} obj.")
        pdf.cell(95, 7, f"Trzby: {t_b:,.0f} CZK / {p_b} obj.")
        pdf.ln()
        
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(0, 100, 0) if zmena > 0 else pdf.set_text_color(150, 0, 0)
        pdf.cell(0, 8, remove_accents(f"CELKOVA ZMENA TRZEB: {znamenko}{zmena:.1f} %"), ln=True)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(8)

    # Celková Praha
    vloz_sekci("CELKOVA PRAHA (VSECHNY DOPRAVY)", data_a, data_b)
    
    # Rozdělení podle kategorií
    for kat in ['Osobní odběr', 'Vlastní doprava', 'Běžná doprava']:
        d_kat_a = data_a[data_a['Typ_dopravy'] == kat]
        d_kat_b = data_b[data_b['Typ_dopravy'] == kat]
        vloz_sekci(f"KATEGORIE: {kat}", d_kat_a, d_kat_b)
        
    return bytes(pdf.output())

# --- CACHE: XML FEED SHOPTET ---
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
        st.error(f"⚠️ Chyba při stahování XML feedu ze Shoptetu: {e}")
        return pd.DataFrame(columns=['itemCode', 'nc_xml'])

# --- CACHE: CÉZAR XML ---
@st.cache_data
def load_cezar_xml(file_bytes):
    def parse_cislo(hodnota):
        if not hodnota: return 0.0
        hodnota_str = str(hodnota).replace('\xa0', '').replace(' ', '').strip().replace(',', '.')
        try:
            return float(hodnota_str)
        except ValueError:
            return 0.0

    try:
        context = ET.iterparse(BytesIO(file_bytes), events=('end',))
        cezar_data = []
        
        for event, elem in context:
            kod = elem.get('Cislo')
            
            if not kod:
                kod_elem = elem.find('Cislo')
                if kod_elem is not None:
                    kod = kod_elem.text
                    
            if kod and elem.tag not in ['Field', 'FieldDefs']:
                nca = parse_cislo(elem.get('NCA') or elem.findtext('NCA'))
                ncp = parse_cislo(elem.get('NCP') or elem.findtext('NCP'))
                nc = parse_cislo(elem.get('NC') or elem.findtext('NC'))
                
                vybrana_nc = ncp if ncp > 0 else (nca if nca > 0 else nc)
                
                if vybrana_nc > 0:
                    jednotka = (elem.get('jednotka') or elem.findtext('jednotka') or '').strip().lower()
                    
                    if jednotka in ['bm', 'm']:
                        sirka = parse_cislo(elem.get('Sirka') or elem.findtext('Sirka'))
                        if sirka > 0:
                            vybrana_nc = vybrana_nc / (sirka / 100.0)
                            
                    elif jednotka in ['bal', 'bal.', 'karton']:
                        baleni_zakl = parse_cislo(elem.get('BaleniZakl') or elem.findtext('BaleniZakl'))
                        if baleni_zakl > 0:
                            vybrana_nc = vybrana_nc / baleni_zakl

                    cezar_data.append({
                        'itemCode': str(kod).strip(),
                        'nc_cezar': vybrana_nc
                    })
                
                elem.clear()
                
        df_cezar = pd.DataFrame(cezar_data)
        
        if df_cezar.empty:
            return pd.DataFrame(columns=['itemCode', 'nc_cezar'])
            
        df_cezar = df_cezar.drop_duplicates(subset=['itemCode'], keep='last')
        return df_cezar

    except Exception as e:
        st.error(f"⚠️ Chyba při zpracování Cézar XML: {e}")
        return pd.DataFrame(columns=['itemCode', 'nc_cezar'])

# --- CACHE: EXPORT OBJEDNÁVEK Z ODKAZU ---
@st.cache_data(ttl=3600)
def load_orders(url):
    try:
        clean_url = f"{str(url).strip()}&timestamp={int(time.time())}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(clean_url, headers=headers, timeout=45)
        response.raise_for_status()
        response.encoding = 'cp1250' 
        
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
        st.error(f"⚠️ Chyba při stahování objednávek: {e}")
        return pd.DataFrame()

# --- CACHE: ZPRACOVÁNÍ RUČNÍHO SOUBORU OBJEDNÁVEK ---
@st.cache_data
def process_uploaded_file(file_bytes):
    df = pd.read_csv(StringIO(file_bytes.decode('cp1250')), sep=';', decimal=',', quotechar='"', on_bad_lines='skip', low_memory=False)
    df['itemTotalPriceWithoutVat'] = clean_money(df['itemTotalPriceWithoutVat'])
    df['itemAmount'] = clean_money(df['itemAmount'])
    df['itemCode'] = df['itemCode'].astype(str).str.strip()
    
    if 'date' in df.columns:
        df['date_str'] = df['date'].astype(str).str.strip().str.replace('"', '')
        df['rok'] = df['date_str'].apply(extract_year)
        df['mesic'] = df['date_str'].apply(extract_month)
    return df

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
    # --- HLAVNÍ APLIKACE ROZDĚLENÁ NA ZÁLOŽKY ---
    tab_zisk, tab_praha = st.tabs(["💰 Analýza Zisku (Aktuální)", "🏙️ Report Praha (Komplexní)"])

    # ==========================================
    # ZÁLOŽKA 1: ANALÝZA ZISKU
    # ==========================================
    with tab_zisk:
        st.title("Analýza zisku")

        with st.expander("📖 JAK SYSTÉM FUNGUJE"):
            st.markdown("""
            1. **Plná automatizace:** Aplikace si sama stahuje seznam objednávek i databázi nákupních cen z e-shopu.
            2. **DPH Korekce:** Tržby se počítají z objednávek *bez DPH*. Nákupní ceny ze Shoptet XML se automaticky očistí od DPH podle nastavení vlevo. Cézar přenáší hodnoty již bez DPH.
            3. **Integrace Cézara:** Můžete nahrát XML z Cézara (až 125 MB). Systém automaticky upřednostní aktuální nákupní cenu z něj a chytře přepočítá balení/metráž podle měrné jednotky.
            4. **Výběr období:** Zvolte si Rok a Měsíc pro analýzu.
            5. **Doplnění NC:** V tabulce doplňte chybějící ceny. Ukládají se napořád do Google Tabulky (Tato tabulka má absolutní prioritu).
            """)

        # --- SIDEBAR ---
        st.sidebar.header("⚙️ Nastavení datového feedu")
        xml_ceny_s_dph = st.sidebar.checkbox("Ceny z administrace e-shopu jsou vč. DPH", value=True)
        dph_sazba_xml = st.sidebar.number_input("Sazba DPH (%):", value=21.0, step=1.0)
        
        if st.sidebar.button("🔄 Vynutit aktualizaci dat"):
            st.cache_data.clear()
            st.rerun()

        # --- 1. NAČTENÍ DAT ---
        with st.spinner("Stahuji a zpracovávám data ze Shoptetu a Google Sheets..."):
            df_xml = load_xml_feed(XML_FEED_URL, dph_sazba=dph_sazba_xml, ceny_s_dph=xml_ceny_s_dph)
            try:
                pamet_df = pd.read_csv(URL_CSV_GSHEETS)
                pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
                pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
            except:
                pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

        col_up1, col_up2 = st.columns(2)
        with col_up1:
            uploaded_file = st.file_uploader("Nahrát CSV s objednávkami ručně (volitelné)", type=['csv'])
        with col_up2:
            cezar_file = st.file_uploader("Nahrát XML export z Cézara (volitelné, např. 125 MB)", type=['xml'])

        if cezar_file:
            with st.spinner("Zpracovávám data z Cézara... (může to chvíli trvat)"):
                df_cezar = load_cezar_xml(cezar_file.getvalue())
                if not df_cezar.empty:
                    st.success(f"✅ Data z Cézara úspěšně načtena (nalezeno {len(df_cezar)} unikátních položek s cenou).")
        else:
            df_cezar = pd.DataFrame(columns=['itemCode', 'nc_cezar'])

        if uploaded_file:
            df_vsechny_objednavky = process_uploaded_file(uploaded_file.getvalue())
        else:
            df_vsechny_objednavky = load_orders(ORDERS_CSV_URL)

        # --- 2. VÝBĚR OBDOBÍ A NÁKLADŮ ---
        st.subheader("📅 1. Výběr období a fixních nákladů")
        
        if not df_vsechny_objednavky.empty and 'rok' in df_vsechny_objednavky.columns:
            roky = sorted(df_vsechny_objednavky['rok'].dropna().unique().astype(int).tolist(), reverse=True)
            mesice = sorted(df_vsechny_objednavky['mesic'].dropna().unique().astype(int).tolist())
            
            col_r, col_m, col_mkt, col_dop = st.columns(4)
            if not roky: roky = [pd.Timestamp.now().year]
            if not mesice: mesice = list(range(1, 13))
            
            vybrany_rok = col_r.selectbox("Rok:", ["CELÝ ROK"] + roky)
            vybrany_mesic = col_m.selectbox("Měsíc:", ["VŠECHNY MĚSÍCE"] + mesice)
            
            mkt_cost = col_mkt.number_input("Marketing (bez DPH):", min_value=0.0, step=100.0)
            doprava_cost = col_dop.number_input("Doprava faktury (bez DPH):", min_value=0.0, step=100.0)
            
            stavy = []
            if 'statusName' in df_vsechny_objednavky.columns:
                stavy = sorted(df_vsechny_objednavky['statusName'].dropna().unique().tolist())
                default_stavy = [s for s in stavy if "storno" not in str(s).lower() and "zrušen" not in str(s).lower()]
                vybrane_stavy = st.multiselect("Filtrovat stavy objednávek:", stavy, default=default_stavy)
            
            df_filtr = df_vsechny_objednavky.copy()
            
            if vybrany_rok != "CELÝ ROK":
                df_filtr = df_filtr[df_filtr['rok'] == float(vybrany_rok)]
            if vybrany_mesic != "VŠECHNY MĚSÍCE":
                df_filtr = df_filtr[df_filtr['mesic'] == float(vybrany_mesic)]
                
            if 'statusName' in df_vsechny_objednavky.columns and vybrane_stavy:
                df_filtr = df_filtr[df_filtr['statusName'].isin(vybrane_stavy)]

        else:
            st.error("Nepodařilo se načíst data o datumech z e-shopu.")
            st.stop()

        if df_filtr.empty:
            st.warning("V tomto období nezůstala k výpočtu žádná data.")
        else:
            # --- 3. KONTROLA CEN ---
            unikaty = df_filtr[df_filtr['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
            editor_prep = pd.merge(unikaty, df_xml, on='itemCode', how='left')
            editor_prep = pd.merge(editor_prep, df_cezar, on='itemCode', how='left')
            editor_prep = pd.merge(editor_prep, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
            
            editor_prep['finalni_nc'] = (
                editor_prep['nakupni_cena']
                .fillna(editor_prep['nc_cezar'])
                .fillna(editor_prep['nc_xml'])
                .fillna(0.0)
            )
            editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)
            
            tabulka_pro_editor = editor_prep[['itemCode', 'itemName', 'finalni_nc', 'koeficient']].copy()
            tabulka_pro_editor.rename(columns={'finalni_nc': 'nakupni_cena'}, inplace=True)

            st.subheader("📝 2. Kontrola nákupních cen (BEZ DPH)")
            st.info("Produkty prodané ve vybraném období. Zobrazují se předvyplněné hodnoty (Priorita: Vaše ruční oprava > Cézar > Shoptet). Pokud cena chybí (0.00), doplňte ji.")
            
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
            if st.button("🚀 SPOČÍTAT ZISK ZA VYBRANÉ OBDOBÍ A ULOŽIT", type="primary"):
                with st.status("Zpracovávám prodeje...", expanded=True) as status:
                    
                    aktualni_nc = tabulka_pro_editor.copy()
                    state = st.session_state.get("cenovy_editor", {})
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
                
                if total_cisty_zisk > 0:
                    st.balloons()
                    
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("TRŽBY (bez DPH)", f"{total_trzby:,.0f} Kč".replace(',', ' '))
                c2.metric("NÁKLADY ZBOŽÍ (bez DPH)", f"{total_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{total_naklady_zbozi:,.0f}", delta_color="inverse")
                c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_naklady_zbozi):,.0f} Kč".replace(',', ' '))
                
                barva = "normal" if total_cisty_zisk > 0 else "inverse"
                c4.metric("ČISTÝ ZISK", f"{total_cisty_zisk:,.0f} Kč".replace(',', ' '), delta=f"{total_cisty_zisk:,.0f} Kč", delta_color=barva)

                if total_cisty_zisk <= 0:
                    st.error("Vybrané období končí ve ztrátě!")

                with st.expander("🔍 DETAILNÍ ROZPIS (Tržba bez DPH vs Náklad bez DPH)"):
                    kontrola_df = final_merged[['itemCode', 'itemName', 'statusName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']].copy()
                    kontrola_df.columns = ['Kód', 'Produkt', 'Stav', 'Množství', 'TRŽBA (bez DPH)', 'NC / ks (bez DPH)', 'NÁKLAD (Celkem)']
                    st.dataframe(kontrola_df, use_container_width=True)

                try:
                    from streamlit_gsheets import GSheetsConnection
                    conn = st.connection("gsheets", type=GSheetsConnection)
                    k_ulozeni = aktualni_nc[aktualni_nc['nakupni_cena'] > 0]
                    update_db = pd.concat([pamet_df, k_ulozeni[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                    conn.update(spreadsheet=URL_CSV_GSHEETS, data=update_db)
                except Exception as e:
                    pass

    # ==========================================
    # ZÁLOŽKA 2: KOMPLEXNÍ REPORT PRAHA
    # ==========================================
    ("🏙️ Srovnávací analýza: Praha")
        
        if 'df_vsechny_objednavky' in locals() and not df_vsechny_objednavky.empty:
            # Příprava dat (kategorizace)
            df = df_vsechny_objednavky.copy()
            for col in ['billCity', 'deliveryCity']:
                df[col] = df[col].astype(str).fillna('')
            
            mask_praha = df['billCity'].str.contains('Praha|Prague', case=False) | df['deliveryCity'].str.contains('Praha|Prague', case=False)
            df_praha = df[mask_praha].copy()
            
            if 'statusName' in df_praha.columns:
                df_praha = df_praha[~df_praha['statusName'].str.contains('storno|zrušen', case=False, na=False)]

            def urci_kategorii(items_text):
                text = str(items_text).lower()
                if any(x in text for x in ['naše doprava', 'povezeme sami', 'vlastní doprava']): return 'Vlastní doprava'
                if re.search('osobní|odběr|vyzvednutí|prodejna|sklad', text): return 'Osobní odběr'
                return 'Běžná doprava'

            df_orders = df_praha.groupby(['code', 'rok', 'mesic']).agg({
                'itemTotalPriceWithoutVat': 'sum',
                'itemName': lambda x: ' '.join(x.astype(str))
            }).reset_index()
            df_orders['Typ_dopravy'] = df_orders['itemName'].apply(urci_kategorii)

            # --- FILTRY OBDOBÍ ---
            st.subheader("🔍 Nastavení srovnání")
            roky_list = sorted(df_orders['rok'].dropna().unique().astype(int), reverse=True)
            mesice_list = list(range(1, 13))

            c_f1, c_f2 = st.columns(2)
            with c_f1:
                st.markdown("**Období A (Základní)**")
                rok_a = st.selectbox("Rok A:", roky_list, index=min(1, len(roky_list)-1), key="rok_a")
                mesice_a = st.multiselect("Měsíce A (nechte prázdné pro celý rok):", mesice_list, key="mes_a")
            with c_f2:
                st.markdown("**Období B (Srovnávané)**")
                rok_b = st.selectbox("Rok B:", roky_list, index=0, key="rok_b")
                mesice_b = st.multiselect("Měsíce B (nechte prázdné pro celý rok):", mesice_list, key="mes_b")

            # Logika filtrování
            def filtruj_obdobi(df_in, rok, mesice):
                res = df_in[df_in['rok'] == rok]
                if mesice: res = res[res['mesic'].isin(mesice)]
                return res

            df_a = filtruj_obdobi(df_orders, rok_a, mesice_a)
            df_b = filtruj_obdobi(df_orders, rok_b, mesice_b)

            label_a = f"{rok_a} (měs: {mesice_a if mesice_a else 'vše'})"
            label_b = f"{rok_b} (měs: {mesice_b if mesice_b else 'vše'})"

            # --- 1. CELKOVÁ PRAHA ---
            st.divider()
            st.header("🌍 Celkový výsledek: Praha")
            
            t_a, p_a = df_a['itemTotalPriceWithoutVat'].sum(), df_a['code'].nunique()
            t_b, p_b = df_b['itemTotalPriceWithoutVat'].sum(), df_b['code'].nunique()
            
            m1, m2 = st.columns(2)
            m1.metric(f"Celkové tržby (Období B)", f"{t_b:,.0f} Kč".replace(',',' '), 
                      delta=f"{((t_b-t_a)/t_a*100):.1f} %" if t_a > 0 else None)
            m2.metric(f"Počet objednávek (Období B)", f"{p_b}", 
                      delta=f"{((p_b-p_a)/p_a*100):.1f} %" if p_a > 0 else None)

            # --- 2. GRAF MĚSÍČNÍHO ROZPADU ---
            st.subheader("📅 Měsíční srovnání tržeb (A vs B)")
            chart_a = df_a.groupby('mesic')['itemTotalPriceWithoutVat'].sum().reset_index()
            chart_b = df_b.groupby('mesic')['itemTotalPriceWithoutVat'].sum().reset_index()
            chart_data = pd.merge(chart_a, chart_b, on='mesic', how='outer', suffixes=('_A', '_B')).fillna(0).set_index('mesic')
            chart_data.columns = [f"Tržby {rok_a}", f"Tržby {rok_b}"]
            st.bar_chart(chart_data)

            # --- 3. ROZPAD PODLE DOPRAV ---
            st.subheader("🚛 Rozdělení podle typu logistiky")
            kategorie = ['Osobní odběr', 'Vlastní doprava', 'Běžná doprava']
            
            for kat in kategorie:
                with st.expander(f"Detail: {kat}", expanded=True):
                    d_kat_a = df_a[df_a['Typ_dopravy'] == kat]
                    d_kat_b = df_b[df_b['Typ_dopravy'] == kat]
                    
                    t_ka, p_ka = d_kat_a['itemTotalPriceWithoutVat'].sum(), d_kat_a['code'].nunique()
                    t_kb, p_kb = d_kat_b['itemTotalPriceWithoutVat'].sum(), d_kat_b['code'].nunique()
                    
                    c1, c2, c3, c4 = st.columns(4)
                    c1.write(f"**{rok_a}**")
                    c1.write(f"{t_ka:,.0f} Kč".replace(',',' '))
                    c2.write(f"**{rok_b}**")
                    c2.write(f"{t_kb:,.0f} Kč".replace(',',' '))
                    
                    # Procentuální změna
                    zmena_t = ((t_kb - t_ka) / t_ka * 100) if t_ka > 0 else 0
                    color = "green" if zmena_t > 0 else "red"
                    c3.write("**Změna tržeb**")
                    c3.markdown(f":{color}[{zmena_t:+.1f} %]")
                    
                    c4.write("**Změna obj.**")
                    zmena_p = ((p_kb - p_ka) / p_ka * 100) if p_ka > 0 else 0
                    c4.write(f"{zmena_p:+.1f} %")

            # --- EXPORT ---
            st.divider()
            pdf_bytes = create_praha_dashboard_pdf(df_a, df_b, label_a, label_b, f"Srovnání {label_a} vs {label_b}")
            st.download_button("⬇️ Stáhnout srovnávací report (PDF)", data=pdf_bytes, 
                               file_name=f"srovnani_praha_{rok_a}_{rok_b}.pdf", mime="application/pdf", type="primary")
        else:
            st.warning("Nahrajte data v první záložce.")
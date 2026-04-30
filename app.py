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

# --- CACHE: XML FEED (Stahuje se jen občas) ---
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

# --- CACHE: EXPORT OBJEDNÁVEK (Opravené extrahování data) ---
@st.cache_data(ttl=600) # Aktualizuje se každých 10 minut
def load_orders(url):
    try:
        clean_url = str(url).strip()
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(clean_url, headers=headers, timeout=30)
        response.raise_for_status()
        # Shoptet exportuje v CP1250
        response.encoding = 'cp1250' 
        
        df = pd.read_csv(StringIO(response.text), sep=';', decimal=',')
        
        # Očištění sloupců rovnou při načtení
        df['itemTotalPriceWithoutVat'] = pd.to_numeric(df['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df['itemAmount'] = pd.to_numeric(df['itemAmount'], errors='coerce').fillna(1)
        df['itemCode'] = df['itemCode'].astype(str).str.strip()
        
        # --- NEPRŮSTŘELNÁ EXTRACE DATUMU ---
        if 'date' in df.columns:
            # Převedeme vše na string a odstraníme zbytečné mezery
            df['date_str'] = df['date'].astype(str).str.strip()
            
            # Vytvoříme pomocnou funkci pro bezpečné parsování roku a měsíce
            def get_month_year(date_string):
                try:
                    # Hledáme vzor jako "DD.MM.YYYY" (nebo cokoliv s tečkami)
                    parts = date_string.split(' ')[0].split('.')
                    if len(parts) >= 3:
                        return float(parts[1]), float(parts[2])
                except:
                    pass
                return None, None

            # Aplikujeme funkci na každý řádek
            df[['mesic', 'rok']] = df['date_str'].apply(lambda x: pd.Series(get_month_year(x)))
        
        return df
    except Exception as e:
        st.error(f"⚠️ Chyba při stahování objednávek: {e}")
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
    st.title("Analýza zisku")

    with st.expander("📖 JAK SYSTÉM FUNGUJE"):
        st.markdown("""
        1. **Plná automatizace:** Aplikace si sama stahuje seznam objednávek i databázi nákupních cen (NC) z e-shopu.
        2. **DPH Korekce:** Tržby se počítají z objednávek *bez DPH*. Nákupní ceny z XML se automaticky očistí od DPH podle nastavení vlevo.
        3. **Výběr období:** Zvolte si Rok a Měsíc pro analýzu.
        4. **Doplnění NC:** V tabulce doplňte chybějící ceny (NC 0.00). Ukládají se napořád do Google Tabulky. **Ceny zadávejte BEZ DPH.** / V PROCESU ! Zatím není napojeno! (Míra)
        """)

    # --- SIDEBAR (NASTAVENÍ DPH) ---
    st.sidebar.header("⚙️ Nastavení datového feedu")
    xml_ceny_s_dph = st.sidebar.checkbox("Ceny z administrace e-shopu jsou vč. DPH", value=True)
    dph_sazba_xml = st.sidebar.number_input("Sazba DPH (%):", value=21.0, step=1.0)
    
    if st.sidebar.button("🔄 Vynutit aktualizaci dat"):
        st.cache_data.clear()
        st.rerun()

    # --- 1. NAČTENÍ VŠECH DAT (API + GOOGLE) ---
    with st.spinner("Stahuji a zpracovávám data přes API e-shopu..."):
        df_xml = load_xml_feed(XML_FEED_URL, dph_sazba=dph_sazba_xml, ceny_s_dph=xml_ceny_s_dph)
        df_vsechny_objednavky = load_orders(ORDERS_CSV_URL)
        try:
            pamet_df = pd.read_csv(URL_CSV_GSHEETS)
            pamet_df['itemCode'] = pamet_df['itemCode'].astype(str).str.strip()
            pamet_df = pamet_df.drop_duplicates(subset=['itemCode'], keep='last')
        except:
            pamet_df = pd.DataFrame(columns=["itemCode", "nakupni_cena", "koeficient"])

    # --- 2. VÝBĚR OBDOBÍ A NÁKLADŮ ---
    st.subheader("📅 1. Výběr období a fixních nákladů")
    
    # Filtrovací roletky pro datum
    if not df_vsechny_objednavky.empty and 'rok' in df_vsechny_objednavky.columns:
        # Převedeme na int, ignorujeme NaN
        roky = sorted(df_vsechny_objednavky['rok'].dropna().unique().astype(int).tolist(), reverse=True)
        mesice = sorted(df_vsechny_objednavky['mesic'].dropna().unique().astype(int).tolist())
        
        col_r, col_m, col_mkt, col_dop = st.columns(4)
        if not roky: roky = [pd.Timestamp.now().year]
        if not mesice: mesice = list(range(1, 13))
        
        vybrany_rok = col_r.selectbox("Rok:", roky)
        
        # Pokusíme se předvybrat aktuální měsíc, pokud je v seznamu, jinak první dostupný
        current_month = pd.Timestamp.now().month
        default_month_idx = mesice.index(current_month) if current_month in mesice else 0
        vybrany_mesic = col_m.selectbox("Měsíc:", mesice, index=default_month_idx)
        
        mkt_cost = col_mkt.number_input("Marketing (bez DPH):", min_value=0.0, step=100.0)
        doprava_cost = col_dop.number_input("Doprava faktury (bez DPH):", min_value=0.0, step=100.0)
        
        # Vyfiltrování objednávek na vybrané období
        df_filtr = df_vsechny_objednavky[(df_vsechny_objednavky['rok'] == float(vybrany_rok)) & (df_vsechny_objednavky['mesic'] == float(vybrany_mesic))]
    else:
        st.error("Nepodařilo se načíst data o datumech z e-shopu.")
        st.stop()

    if df_filtr.empty:
        st.warning(f"V období {vybrany_mesic}/{vybrany_rok} nejsou evidovány žádné objednávky.")
    else:
        # --- 3. PŘÍPRAVA DAT PRO VYBRANÝ MĚSÍC ---
        unikaty = df_filtr[df_filtr['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # PROPOJENÍ
        editor_prep = pd.merge(unikaty, df_xml, on='itemCode', how='left')
        editor_prep = pd.merge(editor_prep, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        
        # Priorita: Google -> XML -> Nula
        editor_prep['finalni_nc'] = editor_prep['nakupni_cena'].fillna(editor_prep['nc_xml']).fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)
        
        tabulka_pro_editor = editor_prep[['itemCode', 'itemName', 'finalni_nc', 'koeficient']].copy()
        tabulka_pro_editor.rename(columns={'finalni_nc': 'nakupni_cena'}, inplace=True)

        st.subheader("📝 2. Kontrola nákupních cen (BEZ DPH)")
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
                
                # Získání dat z editoru
                aktualni_nc = tabulka_pro_editor.copy()
                state = st.session_state["cenovy_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_nc.at[int(idx), col] = val

                # Spárování a matematika
                df_vypocet = df_filtr.copy()
                if 'nakupni_cena' in df_vypocet.columns:
                    df_vypocet = df_vypocet.rename(columns={'nakupni_cena': 'nc_stara_z_csv'})

                final_merged = pd.merge(df_vypocet, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                final_merged['naklad_radek'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # Součty
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
                kontrola_df = final_merged[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']].copy()
                kontrola_df.columns = ['Kód', 'Produkt', 'Množství', 'TRŽBA (bez DPH)', 'NC / ks (bez DPH)', 'NÁKLAD (Celkem)']
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
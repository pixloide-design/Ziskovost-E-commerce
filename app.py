
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
URL_CSV_GSHEETS = f"[https://docs.google.com/spreadsheets/d/](https://docs.google.com/spreadsheets/d/){SHEET_ID}/gviz/tq?tqx=out:csv"
XML_FEED_URL = "[https://eshop.superpodlaha.cz/export/productsComplete.xml?patternId=-5&partnerId=6&hash=2f7d22f13d30329b53e8cfb4937eb14143c5e09ec1adaea045d098e7248dbfaa](https://eshop.superpodlaha.cz/export/productsComplete.xml?patternId=-5&partnerId=6&hash=2f7d22f13d30329b53e8cfb4937eb14143c5e09ec1adaea045d098e7248dbfaa)"

# --- CACHE PRO XML FEED (aby se nestahoval při každém kliknutí) ---
@st.cache_data(ttl=3600) # Pamatuje si data 1 hodinu
def load_xml_feed(url):
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        
        xml_data = []
        # Procházení XML - předpokládáme standardní Shoptet/Heureka tagy
        for item in root.findall('.//SHOPITEM'):
            code = item.findtext('CODE')
            if not code:
                code = item.findtext('ITEM_ID') # Záchrana, kdyby to byl jiný feed
                
            purchase_price = item.findtext('PURCHASE_PRICE')
            
            if code and purchase_price:
                try:
                    xml_data.append({'itemCode': str(code).strip(), 'nc_xml': float(purchase_price)})
                except:
                    pass
        
        df_xml = pd.DataFrame(xml_data)
        # Odstranění případných duplicit v XML
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
        1. **Automatické NC:** Systém sám stáhne váš XML feed a najde nákupní ceny.
        2. **Google Tabulka:** Pokud jste uložili jinou cenu do Google Tabulky, má přednost před XML.
        3. **Doplnění:** V tabulce dole se vám ukáží produkty z vašich objednávek. **Ty s NC 0.00 dopište.**
        4. **Výpočet:** Program odečte nákupní cenu u každého prodaného kusu a odečte fixní náklady.
        """)

    # 1. Načtení dat z Google a XML
    with st.spinner("Stahuji data z XML feedu a Google Tabulky..."):
        df_xml = load_xml_feed(XML_FEED_URL)
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
        
        # Očištění exportu
        df_obj['itemTotalPriceWithoutVat'] = pd.to_numeric(df_obj['itemTotalPriceWithoutVat'], errors='coerce').fillna(0)
        df_obj['itemAmount'] = pd.to_numeric(df_obj['itemAmount'], errors='coerce').fillna(1)
        df_obj['itemCode'] = df_obj['itemCode'].astype(str).str.strip()

        # Vytáhneme unikátní produkty (bez dopravy/plateb, ty nemají kód)
        unikaty = df_obj[df_obj['itemCode'] != 'nan'].drop_duplicates(subset=['itemCode'])[['itemCode', 'itemName']].copy()
        
        # MAGIE SPOJOVÁNÍ DAT: Objednávky + XML + Google Tabulka
        editor_prep = pd.merge(unikaty, df_xml, on='itemCode', how='left')
        editor_prep = pd.merge(editor_prep, pamet_df[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
        
        # Logika priority cen: 1. Google Tabulka, 2. XML Feed, 3. Nula
        editor_prep['finalni_nc'] = editor_prep['nakupni_cena'].fillna(editor_prep['nc_xml']).fillna(0.0)
        editor_prep['koeficient'] = editor_prep['koeficient'].fillna(1.0)
        
        # Připravíme finální tabulku pro zobrazení
        tabulka_pro_editor = editor_prep[['itemCode', 'itemName', 'finalni_nc', 'koeficient']].copy()
        tabulka_pro_editor.rename(columns={'finalni_nc': 'nakupni_cena'}, inplace=True)

        st.subheader("📝 3. Kontrola nákupních cen")
        st.info("💡 Produkty jsou seřazeny tak, že ty s NULOVOU nákupní cenou jsou úplně nahoře! Doplňte je.")
        
        # Seřazení tak, aby nuly byly nahoře k doplnění
        tabulka_pro_editor = tabulka_pro_editor.sort_values(by=['nakupni_cena', 'itemName'], ascending=[True, True]).reset_index(drop=True)

        # EDITOR
        final_editor = st.data_editor(
            tabulka_pro_editor,
            column_config={
                "itemCode": "Kód",
                "itemName": "Produkt",
                "nakupni_cena": st.column_config.NumberColumn("NÁKUPNÍ CENA (NC) / ks", format="%.2f Kč"),
                "koeficient": "Koeficient"
            },
            hide_index=True,
            use_container_width=True,
            key="cenovy_editor"
        )

        if st.button("🚀 SPOČÍTAT FINÁLNÍ ZISK A ULOŽIT", type="primary"):
            with st.status("Provádím datovou analýzu...", expanded=True) as status:
                
                # 1. Načtení dat z editoru (včetně změn)
                aktualni_nc = tabulka_pro_editor.copy()
                state = st.session_state["cenovy_editor"]
                if "edited_rows" in state:
                    for idx, changes in state["edited_rows"].items():
                        for col, val in changes.items():
                            aktualni_nc.at[int(idx), col] = val

                # 2. Příprava exportu (Přejmenování starých NC z CSV, kdyby tam náhodou byly)
                df_vypocet = df_obj.copy()
                if 'nakupni_cena' in df_vypocet.columns:
                    df_vypocet = df_vypocet.rename(columns={'nakupni_cena': 'nc_stara_z_csv'})

                # 3. PÁROVÁNÍ 1:1 NA EXPORT
                final_merged = pd.merge(df_vypocet, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']], on='itemCode', how='left')
                
                # 4. MATEMATIKA NÁKLADŮ
                final_merged['nakupni_cena'] = pd.to_numeric(final_merged['nakupni_cena']).fillna(0)
                final_merged['koeficient'] = pd.to_numeric(final_merged['koeficient']).fillna(1)
                
                # Výpočet nákladu za každý řádek (Množství * NC * Koeficient)
                final_merged['naklad_radek'] = final_merged['itemAmount'] * final_merged['nakupni_cena'] * final_merged['koeficient']

                # 5. CELKOVÉ SOUČTY
                total_trzby = final_merged['itemTotalPriceWithoutVat'].sum()
                total_naklady_zbozi = final_merged['naklad_radek'].sum()
                total_cisty_zisk = total_trzby - total_naklady_zbozi - mkt_cost - doprava_cost

                time.sleep(1)
                status.update(label="Výpočet dokončen!", state="complete", expanded=False)

            # --- VÝSLEDKY ---
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("TRŽBY CELKEM", f"{total_trzby:,.0f} Kč".replace(',', ' '))
            c2.metric("NÁKLADY NA ZBOŽÍ (NC)", f"{total_naklady_zbozi:,.0f} Kč".replace(',', ' '), delta=f"-{total_naklady_zbozi:,.0f}", delta_color="inverse")
            c3.metric("HRUBÁ MARŽE", f"{(total_trzby - total_naklady_zbozi):,.0f} Kč".replace(',', ' '))
            
            barva = "normal" if total_cisty_zisk > 0 else "inverse"
            c4.metric("ČISTÝ ZISK", f"{total_cisty_zisk:,.0f} Kč".replace(',', ' '), delta=f"{total_cisty_zisk:,.0f} Kč", delta_color=barva)

            if total_cisty_zisk > 0:
                st.balloons()
                st.success("Skvělá práce! E-shop je v zisku.")
            else:
                st.error("Pozor, období končí ve ztrátě!")

            # --- KONTROLNÍ ROZPIS ---
            with st.expander("🔍 DETAILNÍ ROZPIS (Tržba vs Náklad po řádcích)"):
                kontrola_df = final_merged[['itemCode', 'itemName', 'itemAmount', 'itemTotalPriceWithoutVat', 'nakupni_cena', 'naklad_radek']].copy()
                kontrola_df.columns = ['Kód', 'Produkt', 'Množství', 'TRŽBA (Prodejní)', 'NC / ks', 'NÁKLAD (Celkem)']
                st.dataframe(kontrola_df, use_container_width=True)

            # --- ULOŽENÍ DO GOOGLE SHEETS ---
            try:
                from streamlit_gsheets import GSheetsConnection
                conn = st.connection("gsheets", type=GSheetsConnection)
                # Spojíme nově zadaná data s pamětí
                update_db = pd.concat([pamet_df, aktualni_nc[['itemCode', 'nakupni_cena', 'koeficient']]]).drop_duplicates(subset=['itemCode'], keep='last')
                conn.update(spreadsheet=URL_CSV_GSHEETS, data=update_db)
                st.toast("Ceny uloženy do Google Tabulky!", icon="💾")
            except Exception as e:
                st.info("💡 Automatické uložení funguje po propojení Google Service Accountu dle návodu.")
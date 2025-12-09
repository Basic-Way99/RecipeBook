import streamlit as st
import pandas as pd
import json
import os
import io
import zipfile

try:
    from recipe_scrapers import scrape_me

    HAS_SCRAPER = True
except ImportError:
    HAS_SCRAPER = False

# ==========================================
# 1. הגדרות וקבועים
# ==========================================

RECIPES_FILE = "recipes.json"
INGREDIENTS_FILE = "ingredients.json"
CATEGORIES_FILE = "categories.json"
TRASH_FILE = "trash.json"

FOOD_EMOJIS = [
    "🥘", "🥗", "🍲", "🥣", "🍝", "🍜", "🥩", "🍗", "🍖", "🍔", "🍕", "🥪", "🌮", "🌯",
    "🥙", "🥚", "🍳", "🍞", "🥯", "🥞", "🧇", "🧀", "🍟", "🌭", "🧂", "🥫", "🍱", "🍘",
    "🍙", "🍚", "🍛", "🥡", "🍢", "🍣", "🍤", "🍥", "🥮", "🍡", "🥟", "🥠", "🥦", "🥑",
    "🍆", "🥔", "🥕", "🌽", "🌶️", "🥒", "🥬", "🍅", "🍄", "🥜", "🌰", "🍰", "🎂", "🧁",
    "🥧", "🍫", "🍬", "🍭", "🍮", "🍯", "🍪", "🍩", "🍿", "🍦", "🍨", "🍧", "☕", "🍵",
    "🥤", "🧃", "🍺", "🍷", "🍹", "🥂", "🥃"
]

WEIGHT_CONVERTER = {
    "גרם": 1, "מ''ל": 1, "כף": 15, "כפית": 5
}

# תוקן: "כפפית" הוחלף ב- "כפית"
ALLOWED_UNITS = ["גרם", "מ''ל", "כף", "כפית", "יחידה"]

DEFAULT_CATEGORIES = ["בוקר", "צהריים", "ערב", "נשנוש"]

DEFAULT_INGREDIENTS = {
    "חזה עוף (חי)": {"vals": [110, 23, 0, 2], "measure_type": "100g"},
    "אורז בסמטי (לפני בישול)": {"vals": [356, 7, 80, 0.6], "measure_type": "100g"},
    "שמן זית": {"vals": [882, 0, 0, 98], "measure_type": "100g"},
    "ביצה (L)": {"vals": [86, 7.5, 0.6, 6], "measure_type": "unit"},
    "לחם מלא (פרוסה)": {"vals": [87, 3, 15, 1], "measure_type": "unit"},
    "מלפפון": {"vals": [15, 0.7, 3.6, 0.1], "measure_type": "100g"},
    "עגבניה": {"vals": [18, 0.9, 3.9, 0.2], "measure_type": "100g"},
    "טונה במים (מסונן)": {"vals": [116, 26, 0, 1], "measure_type": "100g"},
    "שיבולת שועל": {"vals": [389, 16.9, 66, 6.9], "measure_type": "100g"},
    "קוטג' 5% (גביע)": {"vals": [240, 27.5, 3.75, 12.5], "measure_type": "unit"},
}


# ==========================================
# 2. פונקציות עזר
# ==========================================

def load_json(filename, default_data):
    if not os.path.exists(filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=4)
        return default_data
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if filename == INGREDIENTS_FILE:
                for key, val in data.items():
                    if len(val["vals"]) == 2: val["vals"].extend([0, 0])
                    if "measure_type" not in val: val["measure_type"] = "100g"
            return data
    except:
        return default_data


def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def parse_ingredients_list(ingredients_text_list):
    parsed_data = []
    for ing_str in ingredients_text_list:
        try:
            parts = ing_str.split(' ', 2)
            if len(parts) >= 3:
                parsed_data.append({
                    "שם המצרך": parts[2],
                    "כמות": float(parts[0]),
                    "יחידה": parts[1]
                })
            else:
                parsed_data.append({"שם המצרך": ing_str, "כמות": 1.0, "יחידה": "יחידה"})
        except:
            pass
    return pd.DataFrame(parsed_data)


def calculate_nutrition(df_ingredients, ingredients_db):
    total = {"pro": 0, "carb": 0, "fat": 0}
    if df_ingredients.empty: return {"cal": 0, "pro": 0, "carb": 0, "fat": 0}

    for _, row in df_ingredients.iterrows():
        name = row["שם המצרך"]
        amount = row["כמות"]
        unit = row["יחידה"]

        if name in ingredients_db and amount > 0:
            db_item = ingredients_db[name]
            measure_type = db_item.get("measure_type", "100g")
            vals = db_item["vals"]
            ratio = 0

            if measure_type == "unit":
                if unit == "יחידה":
                    ratio = amount
                else:
                    ratio = 0
            else:
                # משתמש ב- WEIGHT_CONVERTER
                weight_in_grams = amount * WEIGHT_CONVERTER.get(unit, 1)
                ratio = weight_in_grams / 100

            if ratio > 0:
                total["pro"] += vals[1] * ratio
                total["carb"] += vals[2] * ratio
                total["fat"] += vals[3] * ratio

    total_cal = (total["pro"] * 4) + (total["carb"] * 4) + (total["fat"] * 9)
    return {
        "cal": int(total_cal),
        "pro": int(total["pro"]),
        "carb": int(total["carb"]),
        "fat": int(total["fat"])
    }


def recalc_all_recipes(recipes_list, ingredients_db):
    count = 0
    for recipe in recipes_list:
        df_ing = parse_ingredients_list(recipe['ingredients'])
        new_vals = calculate_nutrition(df_ing, ingredients_db)
        recipe['calories'] = new_vals['cal']
        recipe['protein'] = new_vals['pro']
        recipe['carbs'] = new_vals['carb']
        recipe['fats'] = new_vals['fat']
        count += 1
    return count

# פונקציות Callback לטיפול בכפתורי + / - (תיקון שגיאת StreamlitAPIException)
def increment_serving(serving_key):
    # מעלה את הערך ב-session_state, תוך שמירה על גבול עליון של 100
    if serving_key in st.session_state:
        st.session_state[serving_key] = min(100, st.session_state[serving_key] + 1)

def decrement_serving(serving_key):
    # מוריד את הערך ב-session_state, תוך שמירה על גבול תחתון של 1
    if serving_key in st.session_state:
        st.session_state[serving_key] = max(1, st.session_state[serving_key] - 1)

def set_selected_emoji(new_emoji):
    # פונקציית הקאלבק לעדכון האייקון
    st.session_state['selected_emoji'] = new_emoji
    st.rerun() 

def create_backup_zip():
    """דוחס את כל קבצי ה-JSON ל-ZIP ושומר ב-BytesIO."""
    file_list = [RECIPES_FILE, INGREDIENTS_FILE, CATEGORIES_FILE, TRASH_FILE]
    
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename in file_list:
            if os.path.exists(filename):
                try:
                    with open(filename, 'rb') as f:
                        zipf.writestr(filename, f.read())
                except Exception:
                    pass

    buffer.seek(0)
    return buffer.getvalue()


# ==========================================
# 3. הגדרות תצוגה ו-CSS
# ==========================================

st.set_page_config(page_title="השף האוטומטי", page_icon="🤖", layout="centered")

st.markdown("""
<style>
    /* כיוון כללי לימין */
    body {direction: rtl; text-align: right;}

    .stSelectbox, .stMultiSelect, .stMarkdown, p, h1, h2, h3, input, textarea, .stNumberInput {
        direction: rtl; 
        text-align: right;
    }

    .stDataFrame, .stDataEditor {direction: rtl;}

    div[data-testid="stForm"] {direction: rtl; text-align: right;}
    /* מרכוז כותרות במטריק של סטרימליט */
    div[data-testid="stMetric"] {direction: rtl; text-align: right;}
    div[data-testid="stMetricValue"] {
        text-align: right;
        font-size: 1.5rem;
    }
    div[data-testid="stMetricLabel"] {
        text-align: right;
        font-size: 0.9rem;
    }

    /* התאמת כפתורי ה +/- */
    div[data-testid^="stButton"] > button {
        height: 38px;
        line-height: 1; 
        font-size: 1.2rem;
        font-weight: bold;
        padding: 5px 12px;
    }
    
    /* מוחק את כפתורי הברירת מחדל של st.number_input */
    div[data-testid="stNumberInput"] button {
        display: none !important;
    }
    div[data-testid="stNumberInput"] > div:nth-child(2) {
        padding-right: 0.5rem; 
    }
    
    /* סגנון כפתורי האמוג'י ב-PopOver */
    .stPopover div[data-testid^="stButton"] > button {
        height: 40px !important;
        width: 40px !important;
        font-size: 1.5rem !important;
        padding: 0 !important;
        margin: 1px !important;
        background-color: #f0f2f6; 
        border-radius: 8px;
        transition: background-color 0.1s;
    }
    
    /* *** תיקון קריטי לריווח האנכי בטאב 2 (נשאר לצורך יציבות) *** */
    div[data-testid="stTextInput"] {
        margin-bottom: 0px !important;
    }
    div[data-testid="stForm"] > div:first-child {
        padding-top: 0px !important;
    }
    div[data-testid="stRadio"] {
        margin-bottom: 0.5rem !important;
    }


    /* מימין לשמאל בטבלאות */
    th {text-align: right !important;}
    td {text-align: right !important;}

    .stDataEditor iframe {width: 100% !important;}

    /* === Sticky Tabs Hack === */
    div[data-testid="stTabs"] > div:first-child {
        position: sticky;
        top: 0; 
        z-index: 1000;
        background-color: white; 
        padding-top: 1rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #f0f0f0;
    }
</style>
""", unsafe_allow_html=True)

if 'recipes' not in st.session_state:
    st.session_state['recipes'] = load_json(RECIPES_FILE, [])
if 'ingredients_db' not in st.session_state:
    st.session_state['ingredients_db'] = load_json(INGREDIENTS_FILE, DEFAULT_INGREDIENTS)
if 'categories' not in st.session_state:
    st.session_state['categories'] = load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES)
if 'trash' not in st.session_state:
    st.session_state['trash'] = load_json(TRASH_FILE, [])

st.title("🤖 השף האוטומטי")

tab1, tab2, tab3, tab4 = st.tabs(["🔎 ספר המתכונים", "📝 הוספה ועריכה", "⚙️ ניהול מאגרים", "🗑️ פח אשפה"])

# ------------------------------------------
# TAB 1: ספר המתכונים
# ------------------------------------------
with tab1:
    df = pd.DataFrame(st.session_state['recipes'])

    if not df.empty:
        with st.expander("🔍 אפשרויות סינון וחיפוש", expanded=True):

            search_query = st.text_input("🔎 חיפוש חופשי (שם מתכון, הוראות או מצרך):")
            st.divider()

            col_fil1, col_fil2 = st.columns([1, 2])
            with col_fil1:
                all_cats = st.session_state['categories']
                sel_cats = st.multiselect("קטגוריות:", all_cats, placeholder="בחר קטגוריות (ריק = הכל)")

            with col_fil2:
                all_possible_ingredients = list(st.session_state['ingredients_db'].keys())
                sel_ingredients = st.multiselect("מצרכים (הצג מתכונים שמכילים את כולם):", all_possible_ingredients)

        filtered = df.copy()

        # 1. סינון חיפוש חופשי
        if search_query:
            query = search_query.lower()


            def filter_text(row):
                all_text = str(row['name']) + " " + str(row['instructions']) + " " + " ".join(row['ingredients'])
                return query in all_text.lower()


            filtered = filtered[filtered.apply(filter_text, axis=1)]

        # 2. סינון קטגוריות
        if sel_cats:
            filtered = filtered[filtered['category'].isin(sel_cats)]

        # 3. סינון מצרכים
        if sel_ingredients:
            def check_ingredients(recipe_ings_list):
                recipe_text = " ".join(recipe_ings_list)
                return all(sel_ing in recipe_text for sel_ing in sel_ingredients)


            filtered = filtered[filtered['ingredients'].apply(check_ingredients)]

        if filtered.empty:
            st.warning("לא נמצאו מתכונים תואמים.")
        else:
            st.write(f"נמצאו {len(filtered)} מתכונים:")

            categories_to_show = sel_cats if sel_cats else st.session_state['categories']
            other_recipes = filtered[~filtered['category'].isin(st.session_state['categories'])]

            for category in categories_to_show:
                df_cat = filtered[filtered['category'] == category]

                if not df_cat.empty:
                    st.header(f"{category}")
                    for idx, row in df_cat.iterrows():
                        original_idx = df[df['name'] == row['name']].index[0]
                        total_cals = int(row.get('calories', 0))
                        total_pro = int(row.get('protein', 0))
                        total_carb = int(row.get('carbs', 0))
                        total_fat = int(row.get('fats', 0))
                        
                        # === המתכון הראשי - כותרת מלאה ===
                        header_text = (
                            f"{row['image']} **{row['name']}** | "
                            f"🔥 {total_cals} קל' | "
                            f"🥩 {total_pro} חל' | "
                            f"🍞 {total_carb} פח' | "
                            f"🥑 {total_fat} שומ'"
                        )
                        
                        # פתיחת ה-Expander
                        with st.expander(header_text): 

                            # 1. הצגת הערכים הכוללים (תמיד גלויים כאשר המתכון פתוח)
                            st.markdown("##### **ערכים כוללים (לכל המתכון):**")
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("🔥 קלוריות", total_cals)
                            c2.metric("🥩 חלבון", f"{total_pro} גר'")
                            c3.metric("🍞 פחמימה", f"{total_carb} גר'")
                            c4.metric("🥑 שומן", f"{total_fat} גר'")

                            # ==============================================================
                            # === EXPANDER פנימי למחשבון הקלורי (אופציונלי) ===
                            # ==============================================================
                            with st.expander("⚙️ **מחשבון חלוקה למנות (הרחב)**", expanded=False):

                                # 2. פקד החלוקה למנות
                                st.markdown("##### **מספר מנות:**")
                                
                                # מפתח ייחודי לכל מתכון
                                serving_key = f"serving_calc_{original_idx}"
                                
                                # וודא שקיים ערך התחלתי ב-session_state
                                if serving_key not in st.session_state:
                                    st.session_state[serving_key] = 1

                                # פריסה: מינוס, קלט, פלוס
                                col_minus, col_servings_input, col_plus = st.columns([0.8, 1.5, 0.8])
                                
                                # כפתור מינוס
                                with col_minus:
                                    st.button(
                                        "➖", 
                                        key=f"minus_{original_idx}", 
                                        use_container_width=True,
                                        on_click=decrement_serving,
                                        args=(serving_key,)
                                    )
                                
                                # פקד קלט (כפתורי הברירת מחדל שלו מוסתרים ע"י CSS)
                                with col_servings_input:
                                    num_servings = st.number_input(
                                        "מספר מנות לחלוקה",
                                        min_value=1,
                                        max_value=100,
                                        value=st.session_state[serving_key],
                                        step=1,
                                        label_visibility="collapsed",
                                        key=serving_key
                                    )

                                # כפתור פלוס
                                with col_plus:
                                    st.button(
                                        "➕", 
                                        key=f"plus_{original_idx}", 
                                        use_container_width=True,
                                        on_click=increment_serving,
                                        args=(serving_key,)
                                    )
                                    

                                # 3. חישוב הערכים למנה
                                if num_servings > 0:
                                    cal_per_serving = total_cals / num_servings
                                    pro_per_serving = total_pro / num_servings
                                    carb_per_serving = total_carb / num_servings
                                    fat_per_serving = total_fat / num_servings
                                else:
                                    cal_per_serving = pro_per_serving = carb_per_serving = fat_per_serving = 0

                                # 4. שורה שנייה: ערכים למנה
                                st.markdown(f"##### **ערכים למנה (1/{num_servings}):**")
                                d1, d2, d3, d4 = st.columns(4)
                                d1.metric("🔥 קלוריות", int(cal_per_serving))
                                d2.metric("🥩 חלבון", f"{round(pro_per_serving, 1)} גר'")
                                d3.metric("🍞 פחמימה", f"{round(carb_per_serving, 1)} גר'")
                                d4.metric("🥑 שומן", f"{round(fat_per_serving, 1)} גר'")

                            st.divider()
                            # ==============================================================
                            # === סוף קטע המחשבון המתכווץ ===
                            # ==============================================================

                            col_cont1, col_cont2 = st.columns(2)
                            with col_cont1:
                                st.markdown("**🛒 מצרכים:**")
                                for ing in row['ingredients']:
                                    st.text(f"• {ing}")
                            with col_cont2:
                                st.markdown("**👨‍🍳 הוראות הכנה:**")
                                # שינוי: הוראות כרשימת צ'קבוקסים
                                if row['instructions']:
                                    lines = row['instructions'].split('\n')
                                    st.markdown("<style>.stCheckbox label {direction: rtl; text-align: right;}</style>", unsafe_allow_html=True)
                                    for i, line in enumerate(lines):
                                        step = line.strip()
                                        if step:
                                            # מפתח ייחודי לכל צ'קבוקס עבור המתכון הספציפי
                                            key = f"recipe_{original_idx}_step_{i}"
                                            st.checkbox(step, key=key)
                                else:
                                    st.write("-")

                            if st.button("🗑️ מחק", key=f"del_cat_{category}_{original_idx}"):
                                recipe_to_trash = st.session_state['recipes'].pop(original_idx)
                                st.session_state['trash'].append(recipe_to_trash)
                                save_json(RECIPES_FILE, st.session_state['recipes'])
                                save_json(TRASH_FILE, st.session_state['trash'])
                                st.rerun()
                    st.divider()

            if not other_recipes.empty and not sel_cats:
                st.header("📂 ללא קטגוריה / אחר")
                for idx, row in other_recipes.iterrows():
                    original_idx = df[df['name'] == row['name']].index[0]
                    
                    total_cals = int(row.get('calories', 0))
                    total_pro = int(row.get('protein', 0))
                    total_carb = int(row.get('carbs', 0))
                    total_fat = int(row.get('fats', 0))

                    # === כותרת מלאה עבור מתכונים ללא קטגוריה ===
                    header_text = (
                        f"{row['image']} **{row['name']}** | "
                        f"🔥 {total_cals} קל' | "
                        f"🥩 {total_pro} חל' | "
                        f"🍞 {total_carb} פח' | "
                        f"🥑 {total_fat} שומ'"
                    )
                    
                    with st.expander(header_text):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("🔥 קלוריות", total_cals)
                        c2.metric("🥩 חלבון", f"{total_pro} גר'")
                        c3.metric("🍞 פחמימה", f"{total_carb} גר'")
                        c4.metric("🥑 שומן", f"{total_fat} גר'")

                        st.write("ללא קטגוריה")
                        st.write(row['instructions']) # כאן נשאר טקסט רגיל כיוון שאין הוראות של ממש
                        if st.button("🗑️ מחק", key=f"del_other_{original_idx}"):
                            recipe_to_trash = st.session_state['recipes'].pop(original_idx)
                            st.session_state['trash'].append(recipe_to_trash)
                            save_json(RECIPES_FILE, st.session_state['recipes'])
                            save_json(TRASH_FILE, st.session_state['trash'])
                            st.rerun()
    else:
        st.info("המאגר ריק.")

# ------------------------------------------
# TAB 2: הוספה ועריכה
# ------------------------------------------
with tab2:
    
    # === טאב 2: פקדי ייבוא ו Mode ===
    with st.expander("🌐 ייבוא מתכון מקישור (YouTube / אתרים)", expanded=False):
        import_url = st.text_input("הדבק כאן קישור למתכון:")
        import_text = st.text_area("או הדבק כאן טקסט חופשי (תיאור מיוטיוב/פייסבוק):")

        imported_data = None

        if st.button("נסה לייבא"):
            if import_url and HAS_SCRAPER:
                try:
                    scraper = scrape_me(import_url)
                    imported_data = {
                        "name": scraper.title(),
                        "instructions": scraper.instructions(),
                        "raw_ingredients": scraper.ingredients()
                    }
                    st.success("המתכון נשאב בהצלחה! אנא בדוק את המצרכים בטבלה למטה.")
                except Exception as e:
                    st.warning(f"לא הצלחנו לשאוב אוטומטית. נסה להעתיק ידנית.")
            elif import_url and not HAS_SCRAPER:
                st.error("חסרה ספריית recipe-scrapers. התקן אותה בטרמינל.")

            elif import_text:
                lines = import_text.split('\n')
                ing_lines = [l for l in lines if len(l) > 3]
                imported_data = {
                    "name": "מתכון מיובא",
                    "instructions": "הוראות יובאו מהטקסט...",
                    "raw_ingredients": ing_lines
                }
                st.success("הטקסט נקלט!")

    st.divider()

    mode = st.radio("בחר פעולה:", ["➕ מתכון חדש", "✏️ ערוך קיים"], horizontal=True)

    default_name = ""
    default_emoji = "🥘"
    default_cat = st.session_state['categories'][0] if st.session_state['categories'] else ""
    default_inst = ""
    default_ing_df = pd.DataFrame([{"כמות": 1, "יחידה": "גרם", "שם המצרך": ""}])
    edit_index = -1

    if imported_data:
        default_name = imported_data.get("name", "")
        default_inst = imported_data.get("instructions", "")
        raw_rows = []
        for line in imported_data.get("raw_ingredients", []):
            raw_rows.append({"כמות": 1, "יחידה": "יחידה", "שם המצרך": line})
        if raw_rows:
            default_ing_df = pd.DataFrame(raw_rows)

    elif mode == "✏️ ערוך קיים":
        if st.session_state['recipes']:
            recipe_names = [r['name'] for r in st.session_state['recipes']]
            selected_recipe_name = st.selectbox("בחר מתכון לעריכה:", recipe_names)
            
            for i, r in enumerate(st.session_state['recipes']):
                if r['name'] == selected_recipe_name:
                    edit_index = i
                    default_name = r['name']
                    default_emoji = r['image']
                    default_cat = r['category']
                    default_inst = r['instructions']
                    temp_df = parse_ingredients_list(r['ingredients'])
                    if not temp_df.empty:
                        default_ing_df = pd.DataFrame(temp_df[["כמות", "יחידה", "שם המצרך"]])
        else:
            st.warning("אין מתכונים לעריכה.")


    with st.form("recipe_form"):
        c1, c2 = st.columns([4, 1])
        with c1:
            name = st.text_input("שם המתכון", value=default_name)
        with c2:
            e_idx = FOOD_EMOJIS.index(default_emoji) if default_emoji in FOOD_EMOJIS else 0
            emoji = st.selectbox("אייקון", FOOD_EMOJIS, index=e_idx)

        cat_idx = 0
        if default_cat in st.session_state['categories']:
            cat_idx = st.session_state['categories'].index(default_cat)
        category = st.selectbox("קטגוריה", st.session_state['categories'], index=cat_idx)

        st.divider()
        st.subheader("🛒 הרכבת המנה")

        # === התיקון הסופי לטבלה ===
        col_order_add = ["כמות", "יחידה", "שם המצרך"]

        edited_df = st.data_editor(
            default_ing_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "שם המצרך": st.column_config.SelectboxColumn("שם המצרך",
                                                             options=list(st.session_state['ingredients_db'].keys()),
                                                             required=False, width="medium"),
                "יחידה": st.column_config.SelectboxColumn("יחידה", options=ALLOWED_UNITS, required=True, width="small"),
                "כמות": st.column_config.NumberColumn("כמות", min_value=0, step=0.5, width="small")
            },
            column_order=col_order_add
        )

        st.markdown("**הוראות הכנה:**")
        instructions = st.text_area("כתוב כאן...", value=default_inst, height=150)

        if st.form_submit_button("💾 שמור מתכון"):
            if name and not edited_df.empty:
                nutri = calculate_nutrition(edited_df, st.session_state['ingredients_db'])
                final_ing_list = []
                for _, row in edited_df.iterrows():
                    ing_name = row["שם המצרך"]
                    if ing_name:
                        final_ing_list.append(f"{row['כמות']} {row['יחידה']} {ing_name}")

                new_recipe_obj = {
                    "name": name,
                    "image": emoji,
                    "category": category,
                    "ingredients": final_ing_list,
                    "calories": nutri["cal"],
                    "protein": nutri["pro"],
                    "carbs": nutri["carb"],
                    "fats": nutri["fat"],
                    "instructions": instructions
                }

                if mode == "➕ מתכון חדש" or imported_data:
                    st.session_state['recipes'].append(new_recipe_obj)
                    msg = "המתכון נוסף בהצלחה!"
                else:
                    st.session_state['recipes'][edit_index] = new_recipe_obj
                    msg = "המתכון עודכן בהצלחה!"

                save_json(RECIPES_FILE, st.session_state['recipes'])
                st.success(msg)
                st.rerun()
            else:
                st.error("חסר שם או מצרכים.")

# ------------------------------------------
# TAB 3: ניהול מאגרים
# ------------------------------------------
with tab3:
    st.header("⚙️ הגדרות מערכת")
    
    # ===================================================
    # === פקדי בחירת אייקון מחוץ לטופס (PopOver) ===
    # ===================================================
    st.subheader("🖼️ אייקון ברירת מחדל לרישום חדש")
    
    current_default_emoji = "🥘"
    if 'selected_emoji' not in st.session_state:
        st.session_state['selected_emoji'] = current_default_emoji
    
    c1, c2 = st.columns([1, 4])
    with c1:
        # Popover: מכיל את רשת הבחירה
        popover_button_text = f"🖼️ {st.session_state.get('selected_emoji', current_default_emoji)}"
        with st.popover(popover_button_text):
            st.markdown("### בחר אייקון למתכון (ישמר לשימוש חוזר):")
            
            # הצגת הרשת
            cols_per_row = 8
            emoji_rows = [FOOD_EMOJIS[i:i + cols_per_row] for i in range(0, len(FOOD_EMOJIS), cols_per_row)]
            
            for row_emojis in emoji_rows:
                cols = st.columns(cols_per_row)
                for i, emoji in enumerate(row_emojis):
                    with cols[i]:
                        # הכפתור עצמו (משתמש ב-st.button עם callback)
                        st.button(
                            emoji, 
                            key=f"tab3_popover_emoji_{emoji}", 
                            on_click=set_selected_emoji, 
                            args=(emoji,),
                            use_container_width=True
                        )
    with c2:
        st.markdown(f"**האייקון הנבחר כרגע:** {st.session_state.get('selected_emoji', current_default_emoji)}")
    
    st.divider()

    st.subheader("🥦 מצרכים")
    st.info("הזן חלבון/פחמימה/שומן. הקלוריות יחושבו לבד בשמירה.")

    flattened_data = []
    for name, data in st.session_state['ingredients_db'].items():
        vals = data['vals']
        m_type = data.get("measure_type", "100g")
        display_type = "100 גרם" if m_type == "100g" else "יחידה"

        flattened_data.append({
            "שם המצרך": name,
            "סוג חישוב": display_type,
            "שומן": vals[3],
            "פחמימה": vals[2],
            "חלבון": vals[1],
            "קלוריות (מחושב)": vals[0]
        })

    ingredients_df = pd.DataFrame(flattened_data)

    # סדר ל-RTL: שם אחרון (ימין)
    col_order_manage = ["שומן", "פחמימה", "חלבון", "קלוריות (מחושב)", "סוג חישוב", "שם המצרך"]
    ingredients_df = ingredients_df[col_order_manage]

    edited_ingredients = st.data_editor(
        ingredients_df,
        num_rows="dynamic",
        use_container_width=True,
        key="ing_editor",
        column_config={
            "קלוריות (מחושב)": st.column_config.NumberColumn(disabled=True),
            "סוג חישוב": st.column_config.SelectboxColumn("לפי מה לחשב?", options=["100 גרם", "יחידה"], required=True),
            "שם המצרך": st.column_config.TextColumn("שם המצרך")
        }
    )

    if st.button("💾 שמור שינויים ועדכן הכל 🔄"):
        new_db = {}
        for _, row in edited_ingredients.iterrows():
            if row["שם המצרך"]:
                p = row["חלבון"]
                c = row["פחמימה"]
                f = row["שומן"]
                auto_cals = (p * 4) + (c * 4) + (f * 9)
                internal_type = "100g" if row["סוג חישוב"] == "100 גרם" else "unit"
                new_db[row["שם המצרך"]] = {
                    "vals": [auto_cals, p, c, f],
                    "measure_type": internal_type
                }

        st.session_state['ingredients_db'] = new_db
        save_json(INGREDIENTS_FILE, new_db)
        count = recalc_all_recipes(st.session_state['recipes'], new_db)
        save_json(RECIPES_FILE, st.session_state['recipes'])
        st.success(f"עודכן! {count} מתכונים חושבו מחדש.")
        st.rerun()

    st.divider()

    st.subheader("🏷️ קטגוריות")
    cat_df = pd.DataFrame([{"קטגוריה": c} for c in st.session_state['categories']])
    edited_cats = st.data_editor(
        cat_df,
        num_rows="dynamic",
        use_container_width=True,
        key="cat_editor"
    )

    if st.button("שמור קטגוריות"):
        new_cat_list = [row["קטגוריה"] for _, row in edited_cats.iterrows() if row["קטגוריה"]]
        st.session_state['categories'] = new_cat_list
        save_json(CATEGORIES_FILE, new_cat_list)
        st.success("עודכן!")
        st.rerun()
    
    st.divider()
    
    st.subheader("📦 גיבוי ושחזור")
    
    # כפתור הורדת הגיבוי
    backup_data = create_backup_zip()
    st.download_button(
        label="⬇️ הורד גיבוי מאגרים (ZIP)",
        data=backup_data,
        file_name="recipe_backup.zip",
        mime="application/zip",
        help="מוריד את כל קבצי ה-JSON (מתכונים, מצרכים, קטגוריות ופח אשפה)"
    )

# ------------------------------------------
# TAB 4: פח אשפה
# ------------------------------------------
with tab4:
    st.header("🗑️ פח אשפה")
    
    if st.session_state['trash']:
        st.write(f"יש {len(st.session_state['trash'])} מתכונים בפח.")
        for idx, row in enumerate(st.session_state['trash']):
            col_info, col_actions = st.columns([3, 1])
            with col_info:
                st.write(f"{row['image']} **{row['name']}** ({int(row['calories'])} קל')")
            with col_actions:
                if st.button("♻️ שחזר", key=f"restore_{idx}"):
                    recipe_to_restore = st.session_state['trash'].pop(idx)
                    st.session_state['recipes'].append(recipe_to_restore)
                    save_json(RECIPES_FILE, st.session_state['recipes'])
                    save_json(TRASH_FILE, st.session_state['trash'])
                    st.success("שוחזר!")
                    st.rerun()
                if st.button("❌ מחק סופית", key=f"perm_del_{idx}"):
                    st.session_state['trash'].pop(idx)
                    save_json(TRASH_FILE, st.session_state['trash'])
                    st.rerun()
            st.divider()
    else:
        st.info("הפח ריק.")

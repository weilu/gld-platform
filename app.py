import yaml
import pandas as pd
import streamlit as st
from pathlib import Path
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, ColumnsAutoSizeMode
from queries import QueryService
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="GLD Survey Finder",
    page_icon="📊",
    layout="wide"
)

st.markdown("""
<style>
    .gld-header {
        background: #003366;
        color: white;
        padding: 14px 24px;
        border-radius: 4px;
        margin-bottom: 16px;
    }
    .gld-header h1 { font-size: 22px; font-weight: bold; margin: 0; }
    .gld-header p  { font-size: 13px; opacity: 0.85; margin: 4px 0 0 0; }

    .stTabs [data-baseweb="tab-list"] {
        background-color: #dce3ed;
        border-bottom: 3px solid #003366;
        gap: 0px;
    }
    .stTabs [data-baseweb="tab"] { color: #444; font-size: 13px; padding: 10px 20px; }
    .stTabs [aria-selected="true"] {
        background-color: white;
        color: #003366;
        font-weight: bold;
        border-bottom: 3px solid white;
    }

    .ag-header-cell       { background-color: #003366 !important; color: white !important; }
    .ag-header-group-cell { background-color: #1a4d80 !important; color: white !important; font-weight: bold; }
    .ag-pinned-left-header { background-color: #001f44 !important; }
    .ag-row-even  { background-color: #f8f9fb !important; }
    .ag-row-hover { background-color: #eef4ff !important; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="gld-header">
    <h1>GLD Survey Finder</h1>
    <p>Variable coverage across countries and survey years</p>
</div>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300, show_spinner=False)
def load_data():
    qs = QueryService.get_instance()
    df = qs.get_gld_variable_coverage()
    return df

@st.cache_data
def load_tabs():
    return yaml.safe_load((Path(__file__).parent / "tabs.yaml").read_text(encoding="utf-8"))

# Loading message while data is fetched
with st.spinner("Loading survey data - this may take a few minutes..."):
    df = load_data()

TABS = load_tabs()

def preprocess(df):
    df = df.copy()
    for col in df.columns:
        if col not in ["country", "survey_year"]:
            df[col] = df[col].apply(
                lambda v: "✓" if v == "X" else (
                    "·" if (v is None or (isinstance(v, float) and pd.isna(v)) or v == "")
                    else str(v)
                )
            )
    return df

df_display = preprocess(df)
countries = sorted(df["country"].dropna().unique().tolist())

tab_objects = st.tabs([t["label"] for t in TABS])

for tab_ui, tab_data in zip(tab_objects, TABS):
    with tab_ui:

        if tab_data.get("note"):
            st.info(tab_data["note"])

        col1, col2 = st.columns([2, 1])
        with col1:
            search = st.text_input(
                "Search",
                placeholder="Filter by country or year...",
                key=f"search_{tab_data['id']}"
            )
        with col2:
            country_filter = st.selectbox(
                "Country",
                ["All countries"] + countries,
                key=f"country_{tab_data['id']}"
            )

        filtered = df_display.copy()
        if search:
            mask = (
                filtered["country"].str.contains(search, case=False, na=False) |
                filtered["survey_year"].astype(str).str.contains(search, na=False)
            )
            filtered = filtered[mask]
        if country_filter != "All countries":
            filtered = filtered[filtered["country"] == country_filter]

        n = len(filtered)
        st.caption(f"{n} survey{'s' if n != 1 else ''}")

        tab_vars = ["country", "survey_year"] + [
            c["var"] for g in tab_data["groups"] for c in g["cols"]
        ]
        tab_vars = [v for v in tab_vars if v in filtered.columns]
        tab_df = filtered[tab_vars].reset_index(drop=True)

        if len(tab_vars) <= 2:
            st.warning("No data columns found for this tab in the current dataset.")
            continue

        # Count how many data columns exist (excluding country + year)
        n_data_cols = len(tab_vars) - 2

        # For tabs with few columns, make them wider to fill space
        # For tabs with many columns, use a fixed comfortable width
        if n_data_cols <= 8:
            data_col_flex = 1          # stretch to fill available width
            data_col_width = None
        else:
            data_col_flex = None
            data_col_width = 140       # fixed width for dense tabs

        col_defs = [
            {
                "field": "country",
                "headerName": "Country",
                "pinned": "left",
                "width": 150,
                "suppressMovable": True,
                "cellStyle": {"fontWeight": "bold", "color": "#003366"}
            },
            {
                "field": "survey_year",
                "headerName": "Year",
                "pinned": "left",
                "width": 90,
                "suppressMovable": True,
                "cellStyle": {"color": "#555"}
            },
        ]

        for group in tab_data["groups"]:
            children = []
            for c in group["cols"]:
                if c["var"] not in tab_df.columns:
                    continue
                child = {
                    "field": c["var"],
                    "headerName": c["def"],
                    "wrapHeaderText": True,
                    "autoHeaderHeight": True,
                    "cellStyle": {"textAlign": "center"},
                }
                if data_col_flex:
                    child["flex"] = data_col_flex
                else:
                    child["width"] = data_col_width
                children.append(child)

            if children:
                col_defs.append({
                    "headerName": group["label"],
                    "children": children,
                    "marryChildren": True
                })

        gb = GridOptionsBuilder.from_dataframe(tab_df)
        gb.configure_default_column(
            resizable=True,
            sortable=True,
            filter=False,
            wrapHeaderText=True,
            autoHeaderHeight=True,
            minWidth=160,
        )
        gb.configure_grid_options(
            suppressColumnVirtualisation=True,
            groupHeaderHeight=50,
            headerHeight=120,
            rowHeight=35,
        )
        grid_options = gb.build()
        grid_options["columnDefs"] = col_defs

        AgGrid(
            tab_df,
            gridOptions=grid_options,
            height=600,
            fit_columns_on_grid_load=False,
            update_mode=GridUpdateMode.NO_UPDATE,
            allow_unsafe_jscode=False,
            columns_auto_size_mode=ColumnsAutoSizeMode.NO_AUTOSIZE,
        )


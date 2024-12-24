"""Dashboard for local permits.

See https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::all-building-permits/about
"""

from datetime import datetime, timedelta, UTC
import math

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st


@st.cache_data(ttl=3600)
def query(
    date_range: tuple[datetime, datetime],
    max_per_page: int = 2000,
    max_pages: int = 100,
) -> pd.DataFrame:
    """Fetches GeoJSON pages of permit data from Durham's ArcGIS server."""
    all_rows = []
    for i in range(max_pages):
        params = {
            "outFields": "ISSUE_DATE,DESCRIPTION,COMMENTS,TYPE,BLDB_ACTIVITY_1,BLD_Type,Occupancy,PmtStatus",
            "outSR": 4326,
            "resultOffset": i * max_per_page,
            "resultRecordCount": max_per_page,
            # https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/#date-time-queries
            "where": f"ISSUE_DATE >= TIMESTAMP '{date_range[0]:%Y-%m-%d} 00:00:00' AND ISSUE_DATE <= TIMESTAMP '{date_range[1]:%Y-%m-%d} 23:59:59'",
            "f": "json",
        }
        resp = requests.get(
            "https://webgis2.durhamnc.gov/server/rest/services/PublicServices/Inspections/MapServer/12/query",
            params=params,
        )
        resp.raise_for_status()

        rows = [
            {**row["attributes"], **row.get("geometry", {})}
            for row in resp.json()["features"]
        ]
        all_rows.extend(rows)

        if len(rows) < max_per_page:
            break
    else:
        raise RuntimeError("max_pages exceeded")

    df = pd.DataFrame(all_rows)
    return (
        df.assign(ISSUE_DATE=pd.to_datetime(df.ISSUE_DATE, unit="ms"))
        .rename(columns={"x": "lon", "y": "lat"})
        .sort_values("ISSUE_DATE", ascending=False)
    )


def reset_table():
    """Clears a table selection by generating a new table ID.

    There's no other way at present to clear a table selection in Streamlit."""
    st.session_state.table_idx = st.session_state.get("table_idx", 0) + 1


def on_table_select():
    """Updates the selected dataframe row in state when a table row is selected."""
    df = st.session_state.df
    key = f"table_{st.session_state.get('table_idx', 0)}"
    table = st.session_state[key]
    if table.selection.rows:
        st.session_state.selected_df = df.iloc[table.selection.rows]
    elif "selected_df" in st.session_state:
        del st.session_state.selected_df


def on_map_select():
    """Clears the table selection and updates the selected dataframe row in state when a map point
    is selected."""
    reset_table()
    df = st.session_state.df
    if "scatterplot" in st.session_state.map.selection.indices:
        st.session_state.selected_df = df.iloc[
            st.session_state.map.selection.indices["scatterplot"]
        ]
    elif "selected_df" in st.session_state:
        del st.session_state.selected_df


def on_filter_change():
    """Clears all table and map selections when any of the initial filters change."""
    reset_table()
    if "df" in st.session_state:
        del st.session_state.df
    if "selected_df" in st.session_state:
        del st.session_state.selected_df


def main():
    st.set_page_config(layout="wide")
    st.title("Durham, NC Permits")

    a, b, c, d = st.columns(4)

    # Filter the ArcGIS query by a date range
    utcnow = datetime.now(UTC)
    date_range = a.date_input(
        label="Date Issued",
        min_value=datetime(2007, 1, 1),
        value=(utcnow.date() - timedelta(days=90), utcnow.date()),
        on_change=on_filter_change,
        help="Defaults to the last 90 days",
    )

    # Use today's date for the upper bound if one is not selected
    if len(date_range) < 2:
        date_range = (date_range[0], utcnow.date())

    df = query(date_range)

    # Show additional filters for permit type, activity, and comment/description text
    with b:
        bld_type = st.multiselect(
            "Type",
            placeholder="Filter by building type",
            options=df.TYPE.drop_duplicates().sort_values(),
            on_change=on_filter_change,
        )
    with c:
        activity = st.multiselect(
            "Activity",
            placeholder="Filter by activity",
            options=df.BLDB_ACTIVITY_1.drop_duplicates().sort_values(),
            on_change=on_filter_change,
        )
    with d:
        text = st.text_input(
            "Text",
            placeholder="Filter by description or comment text",
            on_change=on_filter_change,
        )

    # Perform all other filtering locally
    st.session_state.df = df = df[
        (df.TYPE.isin(bld_type) if bld_type else True)
        & (df.BLDB_ACTIVITY_1.isin(activity) if activity else True)
        & (
            df.DESCRIPTION.str.contains(text, case=False)
            | df.COMMENTS.str.contains(text, case=False)
        )
    ]

    # Show the matches in a map and table after initial filtering
    st.caption(f"{len(df)} matching permits")

    a, b = st.columns(2)
    with a:
        # Show whole data frame in a table for selection
        st.dataframe(
            key=f"table_{st.session_state.get('table_idx', 0)}",
            data=df,
            use_container_width=True,
            hide_index=True,
            height=500,
            selection_mode="single-row",
            on_select=on_table_select,
        )

    # Calculate bounds-based zoom for the table selected subset only
    map_focus_df = (
        st.session_state.selected_df if "selected_df" in st.session_state else df
    )
    longitude_range = map_focus_df.lon.max() - map_focus_df.lon.min()
    latitude_range = map_focus_df.lat.max() - map_focus_df.lat.min()
    angle = max(longitude_range, latitude_range)
    zoom = min(max(math.log2(360 / angle), 8), 15) if angle else 15

    # Render a map of all the locations with lat, lon
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=map_focus_df.lat.mean(),
            longitude=map_focus_df.lon.mean(),
            zoom=zoom,
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=df,
                id="scatterplot",
                get_position="[lon, lat]",
                get_color="[255, 90, 255, 160]",
                pickable=True,
                auto_highlight=True,
                get_radius=600 / zoom,
            ),
        ],
    )

    with b:
        st.pydeck_chart(
            key="map",
            pydeck_obj=deck,
            selection_mode="single-object",
            on_select=on_map_select,
            use_container_width=True,
        )

    # Show the details of the selected table row or map point
    if "selected_df" in st.session_state:
        st.table(st.session_state.selected_df.T.astype(str))
    else:
        st.markdown("_No row or point selected_")


if __name__ == "__main__":
    main()

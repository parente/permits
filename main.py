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
    """Fetch GeoJSON pages of permit data from Durham's ArcGIS server."""
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


def main():
    st.set_page_config(layout="wide")
    st.title("Durham Permits")

    a, b, c, d = st.columns(4)

    # Filter the ArcGIS query by a date range
    utcnow = datetime.now(UTC)
    date_range = a.date_input(
        label="Dates",
        min_value=datetime(2007, 1, 1),
        value=(utcnow.date() - timedelta(days=90), utcnow.date()),
    )

    # Use today's date for the upper bound if one is not selected
    if len(date_range) < 2:
        date_range = (date_range[0], utcnow.date())

    df = query(date_range)

    # Show additional filters for permit type, activity, and commnent/description text
    with b:
        bld_type = st.multiselect(
            "Type", options=df.TYPE.drop_duplicates().sort_values()
        )
    with c:
        activity = st.multiselect(
            "Activity", options=df.BLDB_ACTIVITY_1.drop_duplicates().sort_values()
        )
    with d:
        text = st.text_input("Text")

    # Perform all other filtering locally
    df = df[
        (df.TYPE.isin(bld_type) if bld_type else True)
        & (df.BLDB_ACTIVITY_1.isin(activity) if activity else True)
        & (
            df.DESCRIPTION.str.contains(text, case=False)
            | df.COMMENTS.str.contains(text, case=False)
        )
    ]

    # Calculate bounds-based zoom
    longitude_range = df.lon.max() - df.lon.min()
    latitude_range = df.lat.max() - df.lat.min()
    angle = max(longitude_range, latitude_range) * 1.0  # Padding
    zoom = min(max(math.log2(360 / angle), 8), 15)  # Clamp between zoom 8 and 15

    # Show the matches after filtering
    st.caption(f"{len(df)} matching permits")

    # Render a map of all the locations with lat, lon
    deck = pdk.Deck(
        map_style=None,
        initial_view_state=pdk.ViewState(
            latitude=df.lat.mean(),
            longitude=df.lon.mean(),
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
                get_radius=50,
            ),
        ],
    )

    a, b = st.columns(2)
    with a:
        event = st.pydeck_chart(
            deck,
            selection_mode="single-object",
            on_select="rerun",
            use_container_width=True,
        )

    # Show filtered and/or map selected data points
    with b:
        st.dataframe(
            data=(
                df.iloc[event.selection.indices["scatterplot"]]
                if event.selection.indices
                else df
            ),
            use_container_width=True,
            hide_index=True,
            height=500,
        )


if __name__ == "__main__":
    main()

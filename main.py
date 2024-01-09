"""Dashboard for local permits.

See https://live-durhamnc.opendata.arcgis.com/datasets/DurhamNC::all-building-permits/about
"""
import datetime

import pandas as pd
import streamlit as st


@st.cache_data(ttl=3600)
def get_df():
    # URL might be tied to a point in time ...
    df = pd.read_csv(
        "https://opendata.arcgis.com/api/v3/datasets/84d10c7d0a324a39987edaef9910847f_2/downloads/data?format=csv&spatialRefId=4326&where=1%3D1"
        low_memory=False,
    )
    df = (
        df.assign(ISSUE_DATE=pd.to_datetime(df.ISSUE_DATE))
        .filter(
            items=[
                "ISSUE_DATE",
                "DESCRIPTION",
                "COMMENTS",
                "TYPE",
                "BLDB_ACTIVITY_1",
                "BLD_Type",
                "Occupancy",
                "PmtStatus",
                "X",
                "Y",
            ],
        )
        .rename(columns={"X": "lon", "Y": "lat"})
        .sort_values("ISSUE_DATE", ascending=False)
    )
    return df


def main():
    st.set_page_config(layout="wide")
    st.title("Durham Permits")

    df = get_df()
    utcnow = datetime.datetime.utcnow()

    a, b, c, d = st.columns(4)
    with a:
        date_range = st.date_input(
            label="Dates",
            min_value=df.ISSUE_DATE.min(),
            value=(utcnow - datetime.timedelta(days=365 * 4), utcnow),
        )
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

    df = df[
        (df.ISSUE_DATE >= pd.to_datetime(date_range[0], utc=True))
        & (df.ISSUE_DATE <= pd.to_datetime(date_range[1], utc=True))
        & (df.TYPE.isin(bld_type) if bld_type else True)
        & (df.BLDB_ACTIVITY_1.isin(activity) if activity else True)
        & (
            df.DESCRIPTION.str.contains(text, case=False)
            | df.COMMENTS.str.contains(text, case=False)
        )
    ]
    df.insert(0, "MAP?", False)

    st.caption(f"{len(df)} matching permits")
    a, b = st.columns(2)
    with a:
        map_df = st.experimental_data_editor(df, use_container_width=True)
    with b:
        st.map(map_df[map_df["MAP?"]][["lat", "lon"]])


if __name__ == "__main__":
    main()

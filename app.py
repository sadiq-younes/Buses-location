import time
import folium
from folium.plugins import LocateControl
from google.transit import gtfs_realtime_pb2
import pandas as pd
import requests
import streamlit as st
from streamlit_folium import st_folium

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Wellington Live Bus Tracker",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- CUSTOM CSS FOR COMPACT TABLE TEXT & LAYOUT ---
st.markdown(
    """
    <style>
    /* Reduce font size and padding in Streamlit DataFrames */
    [data-testid="stTable"] td, [data-testid="stTable"] th,
    div[data-testid="stDataFrame"] div[role="gridcell"],
    div[data-testid="stDataFrame"] div[role="columnheader"] {
        font-size: 12px !important;
        padding: 2px 4px !important;
    }
    </style>
""",
    unsafe_allow_html=True,
)

st.title("🚌 Wellington Real-Time Bus Tracker")

# --- SECURE API KEY LOAD ---
metlink_api_key = st.secrets.get("METLINK_API_KEY", "")

# --- SESSION STATE FOR MAP VIEWPORT ---
if "map_center" not in st.session_state:
  st.session_state["map_center"] = [-41.2865, 174.7762]
if "map_zoom" not in st.session_state:
  st.session_state["map_zoom"] = 13


# --- DATA FETCHING & PARSING ---
@st.cache_data(ttl=10)
def fetch_gtfs_rt_positions(api_key: str) -> pd.DataFrame:
  if not api_key:
    return pd.DataFrame()

  url = "https://api.opendata.metlink.org.nz/v1/gtfs-rt/vehiclepositions"
  headers = {"x-api-key": api_key, "Accept": "application/x-protobuf"}

  try:
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    records = []
    for entity in feed.entity:
      if entity.HasField("vehicle"):
        veh = entity.vehicle
        pos = veh.position
        trip = veh.trip

        speed_mps = pos.speed if pos.HasField("speed") else 0.0

        records.append({
            "vehicle_id": (
                str(veh.vehicle.id) if veh.HasField("vehicle") else "N/A"
            ),
            "route_id": (
                str(trip.route_id) if trip.HasField("route_id") else "N/A"
            ),
            "trip_id": (
                str(trip.trip_id) if trip.HasField("trip_id") else "N/A"
            ),
            "latitude": pos.latitude,
            "longitude": pos.longitude,
            "bearing": pos.bearing if pos.HasField("bearing") else 0,
            "speed_kmh": round(float(speed_mps) * 3.6, 1),
            "timestamp": (
                pd.to_datetime(veh.timestamp, unit="s", utc=True).tz_convert(
                    "Pacific/Auckland"
                )
                if veh.timestamp
                else None
            ),
        })

    return pd.DataFrame(records)

  except Exception as e:
    st.error(f"Error fetching/parsing feed: {e}")
    return pd.DataFrame()


if not metlink_api_key:
  st.error("⚠️ `METLINK_API_KEY` missing from Streamlit secrets.")
  st.stop()

df_vehicles = fetch_gtfs_rt_positions(metlink_api_key)

# --- MAP & TABLE LAYOUT (7:3 ratio for maximum map area) ---
col_map, col_table = st.columns([7, 3], gap="small")

with col_map:
  # Floating controls popover positioned directly above/over map area
  with st.popover("⚙️ Map Controls & Vehicle Tracking"):
    st.markdown("### Settings & Filters")
    refresh_rate = st.slider(
        "Refresh Interval (s)", min_value=5, max_value=60, value=20, step=5
    )
    route_filter = st.text_input("Filter Route ID:", value="")

    # Route Filter logic
    if not df_vehicles.empty and route_filter.strip():
      df_filtered = df_vehicles[
          df_vehicles["route_id"].str.lower() == route_filter.strip().lower()
      ]
    else:
      df_filtered = df_vehicles

    # Vehicle Tracking Selectbox
    bus_options = ["None (Free View)"]
    if not df_filtered.empty:
      bus_options += [
          f"Route {row['route_id']} (#{row['vehicle_id']})"
          for _, row in df_filtered.iterrows()
      ]

    selected_tracking_bus = st.selectbox(
        "🎯 Follow Vehicle:", options=bus_options
    )

  # Calculate map focus based on popover tracking selection
  if selected_tracking_bus != "None (Free View)":
    tracked_veh_id = (
        selected_tracking_bus.split("(#")[1].replace(")", "").strip()
    )
    tracked_bus_data = df_filtered[df_filtered["vehicle_id"] == tracked_veh_id]

    if not tracked_bus_data.empty:
      current_map_center = [
          tracked_bus_data.iloc[0]["latitude"],
          tracked_bus_data.iloc[0]["longitude"],
      ]
      current_zoom = 16
    else:
      current_map_center = st.session_state["map_center"]
      current_zoom = st.session_state["map_zoom"]
  else:
    current_map_center = st.session_state["map_center"]
    current_zoom = st.session_state["map_zoom"]

  # Render Folium Map with CartoDB Dark Matter
  m = folium.Map(
      location=current_map_center,
      zoom_start=current_zoom,
      tiles="CartoDB dark_matter",
  )

  LocateControl(position="topleft").add_to(m)

  for _, row in df_filtered.iterrows():
    popup_content = f"""
        <div style="font-family: sans-serif; min-width: 130px; color: #111;">
            <b>Route {row['route_id']}</b> (Bus #{row['vehicle_id']})<br>
            <b>Speed:</b> {row['speed_kmh']} km/h<br>
            <b>Bearing:</b> {row['bearing']}°
        </div>
        """

    is_tracked = (
        selected_tracking_bus != "None (Free View)"
        and row["vehicle_id"]
        == selected_tracking_bus.split("(#")[1].replace(")", "").strip()
    )

    folium.CircleMarker(
        location=[row["latitude"], row["longitude"]],
        radius=10 if is_tracked else 6,
        color="#ffffff" if is_tracked else "#00b0ff",
        weight=2 if is_tracked else 1,
        fill=True,
        fill_color="#ffd700" if is_tracked else "#00e5ff",
        fill_opacity=0.95 if is_tracked else 0.85,
        tooltip=(
            f"🎯 Route {row['route_id']} (#{row['vehicle_id']})"
            if is_tracked
            else f"Route {row['route_id']} (#{row['vehicle_id']})"
        ),
        popup=folium.Popup(popup_content, max_width=200),
    ).add_to(m)

  map_data = st_folium(
      m,
      width="100%",
      height=550,
      key=f"bus_map_{selected_tracking_bus}",
      returned_objects=["center", "zoom"],
  )

  if (
      selected_tracking_bus == "None (Free View)"
      and map_data
      and map_data.get("center")
      and map_data.get("zoom")
  ):
    st.session_state["map_center"] = [
        map_data["center"]["lat"],
        map_data["center"]["lng"],
    ]
    st.session_state["map_zoom"] = map_data["zoom"]

with col_table:
  st.subheader("📋 Active Fleet")
  if not df_vehicles.empty:
    m_col1, m_col2 = st.columns(2)
    m_col1.metric("Total Active", len(df_vehicles))
    m_col2.metric("Filtered", len(df_filtered))

    df_display = df_filtered.sort_values(by="speed_kmh", ascending=False)

    st.dataframe(
        df_display[
            ["route_id", "vehicle_id", "speed_kmh", "latitude", "longitude"]
        ],
        column_config={
            "route_id": st.column_config.TextColumn("Route", width="small"),
            "vehicle_id": st.column_config.TextColumn("Bus ID", width="small"),
            "speed_kmh": st.column_config.NumberColumn(
                "Speed", format="%.1f km/h", width="small"
            ),
            "latitude": st.column_config.NumberColumn(
                "Lat", format="%.4f", width="small"
            ),
            "longitude": st.column_config.NumberColumn(
                "Lon", format="%.4f", width="small"
            ),
        },
        use_container_width=True,
        hide_index=True,
        height=430,
    )

# --- AUTO-REFRESH RERUN ---
time.sleep(refresh_rate)
st.rerun()

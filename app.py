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
    initial_sidebar_state="expanded",
)

st.title("🚌 Wellington Real-Time Bus Tracker")
st.caption(
    "Live GTFS-Realtime vehicle location tracking powered by Metlink Open Data"
)

# --- SESSION STATE FOR MAP VIEWPORT ---
if "map_center" not in st.session_state:
  st.session_state["map_center"] = [-41.2865, 174.7762]  # Wellington City Centre
if "map_zoom" not in st.session_state:
  st.session_state["map_zoom"] = 13

# --- API KEY MANAGEMENT ---
metlink_api_key = st.sidebar.text_input(
    "Metlink API Key",
    value=st.secrets.get("METLINK_API_KEY", ""),
    type="password",
    help="Get a free key from the Metlink Open Data Portal (opendata.metlink.org.nz)",
)

# Sidebar Options
refresh_rate = st.sidebar.slider(
    "Auto-Refresh Rate (seconds)", min_value=10, max_value=60, value=20, step=5
)
route_filter = st.sidebar.text_input(
    "Filter by Route ID (e.g., 1, 2, 7):", value=""
)


# --- DATA FETCHING & PARSING ---
@st.cache_data(ttl=10)
def fetch_gtfs_rt_positions(api_key: str) -> pd.DataFrame:
  """Fetches and parses GTFS-Realtime Vehicle Positions from Metlink API."""
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
            "speed_kmh": (
                round(pos.speed * 3.6, 1) if pos.HasField("speed") else 0
            ),
            "timestamp": (
                pd.to_datetime(veh.timestamp, unit="s", utc=True).tz_convert(
                    "Pacific/Auckland"
                )
                if veh.timestamp
                else None
            ),
        })

    return pd.DataFrame(records)

  except requests.exceptions.RequestException as e:
    st.error(f"API Connection Error: {e}")
    return pd.DataFrame()
  except Exception as e:
    st.error(f"Error parsing feed: {e}")
    return pd.DataFrame()


# --- MAIN APP LOGIC ---
if not metlink_api_key:
  st.warning(
      "⚠️ Please enter a Metlink API Key in the sidebar or configure"
      " `.streamlit/secrets.toml` to load vehicle positions."
  )
  st.info(
      "You can request a free API key at:"
      " [opendata.metlink.org.nz](https://opendata.metlink.org.nz)"
  )
else:
  df_vehicles = fetch_gtfs_rt_positions(metlink_api_key)

  if df_vehicles.empty:
    st.info(
        "No active vehicle data received. Please check your API key or try"
        " again in a few moments."
    )
  else:
    # Filter by route if user specified one
    if route_filter.strip():
      df_filtered = df_vehicles[
          df_vehicles["route_id"].str.lower() == route_filter.strip().lower()
      ]
    else:
      df_filtered = df_vehicles

    # --- TRACKING SELECTBOX IN SIDEBAR ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎯 Follow Vehicle Mode")

    # Options list for tracking specific buses
    bus_options = ["None (Free Pan/Zoom)"] + [
        f"Route {row['route_id']} (Vehicle #{row['vehicle_id']})"
        for _, row in df_filtered.iterrows()
    ]

    selected_tracking_bus = st.sidebar.selectbox(
        "Select Bus to Follow:",
        options=bus_options,
        help="Locks map focus onto the selected bus position each refresh cycle.",
    )

    # Calculate center coordinates based on selection
    if selected_tracking_bus != "None (Free Pan/Zoom)":
      # Extract vehicle_id from selection string
      tracked_veh_id = (
          selected_tracking_bus.split("Vehicle #")[1].replace(")", "").strip()
      )
      tracked_bus_data = df_filtered[
          df_filtered["vehicle_id"] == tracked_veh_id
      ]

      if not tracked_bus_data.empty:
        tracked_lat = tracked_bus_data.iloc[0]["latitude"]
        tracked_lng = tracked_bus_data.iloc[0]["longitude"]
        current_map_center = [tracked_lat, tracked_lng]
        current_zoom = 16  # Closer zoom level for tracking
      else:
        current_map_center = st.session_state["map_center"]
        current_zoom = st.session_state["map_zoom"]
    else:
      current_map_center = st.session_state["map_center"]
      current_zoom = st.session_state["map_zoom"]

    # --- METRICS DASHBOARD ---
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Total Active Buses", len(df_vehicles))
    col_m2.metric("Filtered Buses On Map", len(df_filtered))
    latest_time = df_vehicles["timestamp"].max()
    col_m3.metric(
        "Last Feed Update",
        latest_time.strftime("%H:%M:%S NZST")
        if pd.notnull(latest_time)
        else "N/A",
    )

    # --- MAP & TABLE LAYOUT ---
    col_map, col_table = st.columns([7, 5])

    with col_map:
      st.subheader("📍 Live Map View")

      m = folium.Map(
          location=current_map_center,
          zoom_start=current_zoom,
          tiles="OpenStreetMap",
      )

      LocateControl(position="topleft").add_to(m)

      for _, row in df_filtered.iterrows():
        popup_content = f"""
                <div style="font-family: sans-serif; min-width: 140px;">
                    <h4 style="margin:0 0 5px 0;">Bus Route {row['route_id']}</h4>
                    <b>Vehicle ID:</b> {row['vehicle_id']}<br>
                    <b>Speed:</b> {row['speed_kmh']} km/h<br>
                    <b>Bearing:</b> {row['bearing']}°<br>
                    <small>Updated: {row['timestamp'].strftime('%H:%M:%S') if pd.notnull(row['timestamp']) else 'N/A'}</small>
                </div>
                """

        # Highlight tracked vehicle with a distinct color/radius
        is_tracked = (
            selected_tracking_bus != "None (Free Pan/Zoom)"
            and row["vehicle_id"]
            == selected_tracking_bus.split("Vehicle #")[1]
            .replace(")", "")
            .strip()
        )

        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=11 if is_tracked else 7,
            color="#f39c12" if is_tracked else "#2c3e50",
            fill=True,
            fill_color="#f1c40f" if is_tracked else "#e74c3c",
            fill_opacity=0.95 if is_tracked else 0.85,
            tooltip=(
                f"🎯 FOLLOWED: Route {row['route_id']} (#{row['vehicle_id']})"
                if is_tracked
                else f"Route {row['route_id']} (#{row['vehicle_id']})"
            ),
            popup=folium.Popup(popup_content, max_width=220),
        ).add_to(m)

      # Store interaction data using returned dict
      map_data = st_folium(
          m,
          width="100%",
          height=500,
          key=f"bus_map_{selected_tracking_bus}",  # Re-keying avoids state conflict
          returned_objects=["center", "zoom"],
      )

      # Update state only when free pan/zoom mode is active
      if (
          selected_tracking_bus == "None (Free Pan/Zoom)"
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
      st.subheader("📋 Active Vehicles Data")
      st.dataframe(
          df_filtered[[
              "route_id",
              "vehicle_id",
              "speed_kmh",
              "latitude",
              "longitude",
          ]],
          use_container_width=True,
          height=450,
      )

    # Auto-refresh cycle
    time.sleep(refresh_rate)
    st.rerun()

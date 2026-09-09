import time
import requests
import pandas as pd
import folium
from folium.plugins import LocateControl
import streamlit as st
from streamlit_folium import st_folium
from google.transit import gtfs_realtime_pb2

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Wellington Live Bus Tracker",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚌 Wellington Real-Time Bus Tracker")
st.caption("Live GTFS-Realtime vehicle location tracking powered by Metlink Open Data")

# --- API KEY MANAGEMENT ---
# Retrieves key from Streamlit Secrets or sidebar input
metlink_api_key = st.sidebar.text_input(
    "Metlink API Key",
    value=st.secrets.get("METLINK_API_KEY", ""),
    type="password",
    help="Get a free key from the Metlink Open Data Portal (opendata.metlink.org.nz)"
)

# Sidebar Options
refresh_rate = st.sidebar.slider("Auto-Refresh Rate (seconds)", min_value=10, max_value=60, value=20, step=5)
route_filter = st.sidebar.text_input("Filter by Route ID (e.g., 1, 2, 7):", value="")

# --- DATA FETCHING & PARSING ---
@st.cache_data(ttl=10)
def fetch_gtfs_rt_positions(api_key: str) -> pd.DataFrame:
    """Fetches and parses GTFS-Realtime Vehicle Positions from Metlink API."""
    if not api_key:
        return pd.DataFrame()

    url = "https://api.opendata.metlink.org.nz/v1/gtfs-rt/vehiclepositions"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/x-protobuf"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        # Parse Protobuf GTFS-RT message
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)

        records = []
        for entity in feed.entity:
            if entity.HasField("vehicle"):
                veh = entity.vehicle
                pos = veh.position
                trip = veh.trip
                
                records.append({
                    "vehicle_id": veh.vehicle.id if veh.HasField("vehicle") else "N/A",
                    "route_id": trip.route_id if trip.HasField("route_id") else "N/A",
                    "trip_id": trip.trip_id if trip.HasField("trip_id") else "N/A",
                    "latitude": pos.latitude,
                    "longitude": pos.longitude,
                    "bearing": pos.bearing if pos.HasField("bearing") else 0,
                    "speed_kmh": round(pos.speed * 3.6, 1) if pos.HasField("speed") else 0,
                    "timestamp": pd.to_datetime(veh.timestamp, unit="s", utc=True).tz_convert("Pacific/Auckland") if veh.timestamp else None
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
    st.warning("⚠️ Please enter a Metlink API Key in the sidebar or configure `.streamlit/secrets.toml` to load vehicle positions.")
    st.info("You can request a free API key at: [opendata.metlink.org.nz](https://opendata.metlink.org.nz)")
else:
    df_vehicles = fetch_gtfs_rt_positions(metlink_api_key)

    if df_vehicles.empty:
        st.info("No active vehicle data received. Please check your API key or try again in a few moments.")
    else:
        # Filter by route if user specified one
        if route_filter.strip():
            df_filtered = df_vehicles[df_vehicles["route_id"].str.lower() == route_filter.strip().lower()]
        else:
            df_filtered = df_vehicles

        # --- METRICS DASHBOARD ---
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Active Buses", len(df_vehicles))
        col_m2.metric("Filtered Buses On Map", len(df_filtered))
        latest_time = df_vehicles["timestamp"].max()
        col_m3.metric("Last Feed Update", latest_time.strftime("%H:%M:%S NZST") if pd.notnull(latest_time) else "N/A")

        # --- MAP & TABLE LAYOUT ---
        col_map, col_table = st.columns([7, 5])

        with col_map:
            st.subheader("📍 Live Map View")
            
            # Center map on Wellington City Centre
            wellington_coords = [-41.2865, 174.7762]
            m = folium.Map(location=wellington_coords, zoom_start=13, tiles="OpenStreetMap")

            # Add GPS Locate Control
            LocateControl(position="topleft").add_to(m)

            # Render vehicle markers
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
                
                folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=7,
                    color="#2c3e50",
                    fill=True,
                    fill_color="#e74c3c" if row['route_id'] != 'N/A' else "#3498db",
                    fill_opacity=0.85,
                    tooltip=f"Route {row['route_id']} (Bus #{row['vehicle_id']})",
                    popup=folium.Popup(popup_content, max_width=220)
                ).add_to(m)

            st_folium(m, width="100%", height=500, key="bus_map")

        with col_table:
            st.subheader("📋 Active Vehicles Data")
            st.dataframe(
                df_filtered[["route_id", "vehicle_id", "speed_kmh", "latitude", "longitude"]],
                use_container_width=True,
                height=450
            )

        # Trigger auto-refresh
        time.sleep(refresh_rate)
        st.rerun()
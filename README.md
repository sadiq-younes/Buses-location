# 🚌 Wellington Real-Time Bus Tracker

A web-based spatial application built with Python and Streamlit that fetches, parses, and visualizes live public transit data across Wellington, New Zealand.

The application connects to the **Metlink Open Data API** to process GTFS Realtime (`GTFS-RT`) Protocol Buffer feeds, displaying active bus positions, movement metrics, and route details on an interactive map.

---

## 🌟 Key Features

* **Live Vehicle Tracking:** Parses GTFS-RT Protobuf feeds to display real-time bus locations updated every 10–60 seconds.
* **Interactive Spatial Visualization:** Interactive map powered by Folium with custom popups showing vehicle IDs, speed, heading, and route information.
* **Route Filtering & Search:** Filter active vehicles dynamically by route ID.
* **Live Analytics Dashboard:** Real-time metrics for total active buses and feed update timestamps.

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Framework:** [Streamlit](https://streamlit.io/)
* **Mapping & GIS:** [Folium](https://python-visualization.github.io/folium/) & `streamlit-folium`
* **Data Processing:** Pandas, Requests, `gtfs-realtime-bindings`
* **Data Source:** [Metlink Open Data Portal API](https://opendata.metlink.org.nz/)

---

## ⚙️ Deployment & Secrets Configuration

This application is deployed on **Streamlit Community Cloud**.

To configure API access:
1. Obtain an API key from the [Metlink Open Data Portal](https://opendata.metlink.org.nz/).
2. In Streamlit Cloud **App Settings → Secrets**, store the key as follows:
   ```toml
   METLINK_API_KEY = "your_actual_metlink_api_key"
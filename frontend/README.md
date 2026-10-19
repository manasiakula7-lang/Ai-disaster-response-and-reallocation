# Step 8: dashboard (React + Leaflet + Recharts)

A decision-support dashboard for the Kerala 2018 flood scenario. It reads everything from the Step 7 backend.

![Overview](../docs/screenshots/1-overview.png)

## Run it

You need Node.js 18+ and the backend running (see `backend/README.md`).

```
cd frontend
npm install
npm run dev          # http://localhost:5173
```

The backend address defaults to `http://localhost:8000`. To change it, copy `.env.example` to `.env` and edit `VITE_API_URL`.

## What's on it

**Map (Leaflet):**
- Districts from the official boundary shapefile, coloured by **GAT severity** (Step 2) or by **share of need met**.
- Relief centres, sized by number of vehicles.
- Roads, with that day's status (open / slowed / blocked; colour plus line style).
- The 25 biggest shipments of the day (centre → district, width = truckloads).
- Hover over anything for details. The day buttons switch the whole dashboard between 18 and 24 Aug 2018.

**Side panel tabs:**

| Tab | Shows |
|---|---|
| Overview | People displaced, districts at high severity and alerts for the day; severity by district; share of each resource covered by the day's plan |
| Alerts & events | The Step 6 event log for the day: real tweets, road changes, the 4 dispatch waves and alerts, filterable |
| Results | Strategy comparison (Steps 3-4), value of replanning (Step 6), federated vs centralised (Step 5); switch between demand met, worst-off district and Gini |
| Simulate | Play the week day by day with any strategy, close a road mid-week, and watch demand met and the worst-off district change (map follows the simulation) |
| What-if | Change stock, demand or close roads, replay the week and compare with the normal week |

Works in light and dark mode and on phones (map on top, panel below).

## Screenshots

`docs/screenshots/`: overview, alerts, results, simulation, what-if, dark mode, mobile. The screenshots were taken without the OpenStreetMap base map, which isn't reachable from the build machine; on a normal internet connection the base map shows under the districts.

## Files

```
src/api.js            backend calls
src/constants.js      days, resources, colour ramps, road styles
src/theme.js          colour tokens for charts, light/dark
src/App.jsx           layout, data loading, day + layer controls
src/components/       MapView, OverviewPanel, AlertsPanel, ComparePanel, SimulatePanel, WhatIfPanel
```

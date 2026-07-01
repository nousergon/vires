import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { RoutePoint } from '../lib/api'

// Tap-to-draw a route on a topo map. Keyless OpenTopoMap raster tiles + OSM/SRTM
// attribution — no API key, terms-clean (public geodata). The parent owns the
// waypoint list and sends it to /routes/measure; this component only renders the
// map + polyline and reports taps. Browser-only WebGL/DOM glue (mocked in tests).

const OPENTOPO_URL = 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)'
const DEFAULT_CENTER: [number, number] = [47.6, -121.7] // Cascades; recentred to the user if geolocation allows

export default function RouteDrawMap({
  points,
  onAddPoint,
}: {
  points: RoutePoint[]
  onAddPoint: (lat: number, lon: number) => void
}) {
  const elRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)
  // Latest callback in a ref so the (once-bound) click handler never goes stale.
  const addRef = useRef(onAddPoint)
  addRef.current = onAddPoint

  useEffect(() => {
    if (!elRef.current || mapRef.current) return
    const map = L.map(elRef.current, { center: DEFAULT_CENTER, zoom: 11 })
    L.tileLayer(OPENTOPO_URL, { attribution: ATTRIBUTION, maxZoom: 17 }).addTo(map)
    map.on('click', (e: L.LeafletMouseEvent) => addRef.current(e.latlng.lat, e.latlng.lng))
    layerRef.current = L.layerGroup().addTo(map)
    mapRef.current = map

    // Best-effort recenter on the user; ignore denial/errors.
    navigator.geolocation?.getCurrentPosition(
      (pos) => map.setView([pos.coords.latitude, pos.coords.longitude], 13),
      () => {},
      { timeout: 5000 },
    )
    return () => {
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [])

  // Redraw the polyline + waypoint dots whenever the points change.
  useEffect(() => {
    const group = layerRef.current
    if (!group) return
    group.clearLayers()
    const latlngs = points.map((p) => [p.lat, p.lon] as [number, number])
    if (latlngs.length >= 2) {
      L.polyline(latlngs, { color: '#f59e0b', weight: 4 }).addTo(group)
    }
    latlngs.forEach((ll) =>
      L.circleMarker(ll, { radius: 5, color: '#f59e0b', fillColor: '#f59e0b', fillOpacity: 1 }).addTo(group),
    )
  }, [points])

  return <div ref={elRef} className="h-64 w-full rounded-xl" aria-label="route map" />
}

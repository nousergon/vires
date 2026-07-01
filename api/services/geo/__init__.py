"""Geospatial helpers for deriving ruck route stats.

The shared measurement engine (:mod:`api.services.geo.measure`) turns any route
geometry — a drawn polyline, a searched trail, or a parsed GPX track — into the
same ``distance_m`` + ``elevation_gain_m`` the ruck log wants. Every flexible
input mode reduces to "geometry → stats", so they all funnel through here and
then through the one editable-fields → ``POST /api/workouts/ruck`` seam.

All outbound calls use stdlib ``urllib`` against **keyless** open providers
(Open-Meteo elevation DEM, Overpass/OSM trail search) — no API key, no secret to
provision, and proxy-tolerant. Every provider call is **fail-soft**: a provider
outage degrades to manual entry, it never blocks logging a ruck.
"""

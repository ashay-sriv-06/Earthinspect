import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Geometry } from './api'

maplibregl.setWorkerUrl(workerUrl)
const GIBS_BASE = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best'

export interface Layers { footprint: boolean; grid: boolean; event: boolean; imagery: boolean; imagery_opacity: number; basemap: boolean }
interface Props {
  geometry: Geometry | null
  support: { footprint: Geometry; cell_size_deg: { lat: number; lon: number }; cell_count: number; kind: string } | null
  cellCenters: [number, number][]
  eventPoint: { lon: number; lat: number; label: string } | null
  layers: Layers
  imageryDate: string | null
  imageryDateB?: string | null
  imageryMix?: number // 0 = show date A, 1 = show date B (real tiles only; no interpolated frames)
  flyKey: string // changes only on explicit user navigation
  highlight: boolean
  center: [number, number]
  zoom: number
  onView: (center: [number, number], zoom: number) => void
  extraPoints?: { lon: number; lat: number; label: string }[]
}

const GIBS = (d: string) => `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`

function bboxPoly(g: Geometry) {
  if (g.type !== 'bbox') return null
  return { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [[[g.west, g.south], [g.east, g.south], [g.east, g.north], [g.west, g.north], [g.west, g.south]]] } }
}
function cellsFC(centers: [number, number][], dlat: number, dlon: number) {
  return { type: 'FeatureCollection' as const, features: centers.map(([x, y]) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [[[x - dlon / 2, y - dlat / 2], [x + dlon / 2, y - dlat / 2], [x + dlon / 2, y + dlat / 2], [x - dlon / 2, y + dlat / 2], [x - dlon / 2, y - dlat / 2]]] } })) }
}
const empty = { type: 'FeatureCollection' as const, features: [] as any[] }

export default function MapView(p: Props) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [tileErr, setTileErr] = useState<string | null>(null)
  const onViewRef = useRef(p.onView)
  onViewRef.current = p.onView

  useEffect(() => {
    if (!el.current) return
    let m: maplibregl.Map
    try {
      m = new maplibregl.Map({
        container: el.current,
        center: p.center, zoom: p.zoom, attributionControl: { compact: true },
        style: {
          version: 8,
          sources: {
            basemap: { type: 'raster', tiles: [`${GIBS_BASE}/BlueMarble_ShadedRelief_Bathymetry/default/2004-08-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`], tileSize: 256, maxzoom: 8, attribution: 'Basemap: NASA Blue Marble shaded relief, coastlines & labels via NASA GIBS' },
            coast: { type: 'raster', tiles: [`${GIBS_BASE}/Coastlines_15m/default/2020-01-01/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`], tileSize: 256, maxzoom: 9 },
            labels: { type: 'raster', tiles: [`${GIBS_BASE}/Reference_Labels_15m/default/2020-01-01/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png`], tileSize: 256, maxzoom: 9 },
          },
          layers: [
            { id: 'bg', type: 'background', paint: { 'background-color': '#0c1218' } },
            { id: 'basemap', type: 'raster', source: 'basemap', paint: { 'raster-brightness-max': 0.42, 'raster-saturation': -0.55, 'raster-contrast': 0.1 } },
            { id: 'coast', type: 'raster', source: 'coast', paint: { 'raster-opacity': 0.55 } },
            { id: 'labels', type: 'raster', source: 'labels', paint: { 'raster-opacity': 0.8 } },
          ],
        },
      })
    } catch (e) {
      setErr('The map could not start (WebGL unavailable). Charts, tables and evidence remain fully usable.')
      return
    }
    map.current = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right')
    m.on('load', () => {
      m.addSource('footprint', { type: 'geojson', data: empty })
      m.addSource('grid', { type: 'geojson', data: empty })
      m.addSource('event', { type: 'geojson', data: empty })
      m.addLayer({ id: 'grid-fill', type: 'fill', source: 'grid', paint: { 'fill-color': '#58c7b1', 'fill-opacity': 0.05 } })
      m.addLayer({ id: 'grid-line', type: 'line', source: 'grid', paint: { 'line-color': '#58c7b1', 'line-opacity': 0.45, 'line-width': 0.8, 'line-dasharray': [2, 2] } })
      m.addLayer({ id: 'footprint-line', type: 'line', source: 'footprint', paint: { 'line-color': '#d5a555', 'line-width': 2 } })
      m.addLayer({ id: 'event-halo', type: 'circle', source: 'event', paint: { 'circle-radius': 10, 'circle-color': '#d57a6c', 'circle-opacity': 0.25 } })
      m.addLayer({ id: 'event-pt', type: 'circle', source: 'event', paint: { 'circle-radius': 4.5, 'circle-color': '#d57a6c', 'circle-stroke-color': '#111820', 'circle-stroke-width': 1.5 } })
      const pop = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'ei-pop' })
      m.on('mouseenter', 'event-pt', (e: any) => { m.getCanvas().style.cursor = 'default'; const f = e.features?.[0]; if (f) pop.setLngLat(f.geometry.coordinates).setText(f.properties.label).addTo(m) })
      m.on('mouseleave', 'event-pt', () => pop.remove())
      setReady(true)
    })
    m.on('error', (e: any) => {
      const src = e?.sourceId
      if (src === 'gibs') setTileErr('NASA GIBS imagery tiles failed to load for this date.')
      else if (src === 'basemap') setTileErr('Some basemap tiles failed to load; analysis overlays still render.')
    })
    m.on('moveend', () => { const c = m.getCenter(); onViewRef.current([+c.lng.toFixed(4), +c.lat.toFixed(4)], +m.getZoom().toFixed(2)) })
    return () => { m.remove(); map.current = null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // data layers
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const fp = p.geometry ? bboxPoly(p.geometry) : null
    ;(m.getSource('footprint') as maplibregl.GeoJSONSource).setData(fp ? { type: 'FeatureCollection', features: [fp] } : empty)
    ;(m.getSource('grid') as maplibregl.GeoJSONSource).setData(p.support ? cellsFC(p.cellCenters, p.support.cell_size_deg.lat, p.support.cell_size_deg.lon) : empty)
    const pts = [...(p.eventPoint ? [p.eventPoint] : []), ...(p.extraPoints || [])]
    ;(m.getSource('event') as maplibregl.GeoJSONSource).setData({ type: 'FeatureCollection', features: pts.map(e => ({ type: 'Feature', properties: { label: e.label }, geometry: { type: 'Point', coordinates: [e.lon, e.lat] } })) })
  }, [ready, p.geometry, p.support, p.cellCenters, p.eventPoint, p.extraPoints])

  // visibility
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const vis = (ids: string[], on: boolean) => ids.forEach(id => m.getLayer(id) && m.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'))
    vis(['footprint-line'], p.layers.footprint)
    vis(['grid-fill', 'grid-line'], p.layers.grid)
    vis(['event-halo', 'event-pt'], p.layers.event)
    vis(['basemap', 'coast', 'labels'], p.layers.basemap)
  }, [ready, p.layers])

  // imagery layer (date-specific; never silently swapped)
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    for (const id of ['gibsB', 'gibs']) { if (m.getLayer(id)) m.removeLayer(id); if (m.getSource(id)) m.removeSource(id) }
    setTileErr(null)
    if (p.layers.imagery && p.imageryDate) {
      m.addSource('gibs', { type: 'raster', tiles: [GIBS(p.imageryDate)], tileSize: 256, maxzoom: 9, attribution: 'Imagery: NASA EOSDIS GIBS / Worldview (MODIS Terra)' })
      m.addLayer({ id: 'gibs', type: 'raster', source: 'gibs', paint: { 'raster-opacity': p.layers.imagery_opacity, 'raster-fade-duration': 0 } }, 'coast')
      if (p.imageryDateB) {
        m.addSource('gibsB', { type: 'raster', tiles: [GIBS(p.imageryDateB)], tileSize: 256, maxzoom: 9 })
        m.addLayer({ id: 'gibsB', type: 'raster', source: 'gibsB', paint: { 'raster-opacity': p.layers.imagery_opacity * (p.imageryMix ?? 0), 'raster-fade-duration': 0 } }, 'coast')
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, p.layers.imagery, p.imageryDate, p.imageryDateB])
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    const mix = p.imageryDateB ? (p.imageryMix ?? 0) : 0
    if (m.getLayer('gibs')) m.setPaintProperty('gibs', 'raster-opacity', p.layers.imagery_opacity * (1 - mix))
    if (m.getLayer('gibsB')) m.setPaintProperty('gibsB', 'raster-opacity', p.layers.imagery_opacity * mix)
  }, [ready, p.layers.imagery_opacity, p.imageryMix, p.imageryDateB])

  // fly only on explicit navigation
  useEffect(() => {
    const m = map.current
    if (!m || !ready || !p.flyKey) return
    const g = p.geometry
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (g && g.type === 'bbox') {
      const pad = Math.max(g.east - g.west, g.north - g.south) * 0.35
      m.fitBounds([[g.west - pad, g.south - pad], [g.east + pad, g.north + pad]], { animate: !reduce, duration: 900 })
    } else if (g && g.type === 'point') {
      m.flyTo({ center: [g.lon, g.lat], zoom: 7, animate: !reduce })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, p.flyKey])

  // highlight footprint briefly on trace
  useEffect(() => {
    const m = map.current
    if (!m || !ready || !p.highlight || !m.getLayer('footprint-line')) return
    m.setPaintProperty('footprint-line', 'line-width', 5)
    const t = setTimeout(() => m.getLayer('footprint-line') && m.setPaintProperty('footprint-line', 'line-width', 2), 400)
    return () => clearTimeout(t)
  }, [ready, p.highlight])

  return (
    <>
      <div ref={el} style={{ position: 'absolute', inset: 0 }} aria-label="Investigation map" role="region" />
      {err && <div className="map-fallback"><div><b>Map unavailable</b><p>{err}</p></div></div>}
      {tileErr && <div className="map-status" role="status">{tileErr}</div>}
      {!err && (
        <div className="map-legend" aria-label="Map legend">
          {p.layers.footprint && p.geometry && <div className="li"><span className="swatch" style={{ borderColor: 'var(--amber)' }} />Requested analysis footprint</div>}
          {p.layers.grid && p.support && <div className="li"><span className="swatch" style={{ borderColor: 'var(--teal)', borderStyle: 'dashed' }} />POWER grid cells used ({p.support.cell_count} × {p.support.cell_size_deg.lat}°×{p.support.cell_size_deg.lon}°)</div>}
          {p.layers.event && (p.eventPoint || p.extraPoints?.length) && <div className="li"><span className="swatch" style={{ borderColor: 'var(--red)', borderRadius: 6 }} />Event reference point (not a hazard extent)</div>}
          {p.layers.imagery && p.imageryDate && <div className="li"><span className="swatch" style={{ borderColor: '#9aa5ad' }} /><span>MODIS true colour {p.imageryDateB
            ? <><b style={{ color: (p.imageryMix ?? 0) < 0.5 ? 'var(--text)' : 'var(--text-3)' }}>A {p.imageryDate}</b> ↔ <b style={{ color: (p.imageryMix ?? 0) >= 0.5 ? 'var(--text)' : 'var(--text-3)' }}>B {p.imageryDateB}</b> · {Math.round((p.imageryMix ?? 0) * 100)}% B</>
            : p.imageryDate} · visual context only</span></div>}
        </div>
      )}
    </>
  )
}

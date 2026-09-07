import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type StyleSpecification,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { GeoJsonProperties } from 'geojson'
import type { Bounds, MapData } from './map-data'
import 'maplibre-gl/dist/maplibre-gl.css'

setWorkerUrl(workerUrl)

const STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'night-background', type: 'background', paint: { 'background-color': '#07111c' } }],
}

function createReferenceGrid(): MapData {
  const features: MapData['features'] = []
  for (let longitude = -180; longitude <= 180; longitude += 30) {
    features.push({ type: 'Feature', properties: {}, geometry: {
      type: 'LineString', coordinates: Array.from({ length: 121 }, (_, i) => [longitude, -60 + i]),
    } })
  }
  for (let latitude = -60; latitude <= 60; latitude += 20) {
    features.push({ type: 'Feature', properties: {}, geometry: {
      type: 'LineString', coordinates: Array.from({ length: 361 }, (_, i) => [-180 + i, latitude]),
    } })
  }
  return { type: 'FeatureCollection', features }
}

type Props = {
  features: MapData
  procedure: MapData
  focus: [number, number] | null
  onFeature: (properties: NonNullable<GeoJsonProperties>) => void
  onBounds: (bounds: Bounds) => void
}

export function AviationMap({ features, procedure, focus, onFeature, onBounds }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const latest = useRef({ features, procedure, onFeature, onBounds })
  const [error, setError] = useState('')
  useLayoutEffect(() => { latest.current = { features, procedure, onFeature, onBounds } }, [features, procedure, onFeature, onBounds])

  useEffect(() => {
    if (!containerRef.current) return
    let map: MapLibreMap
    try {
      map = new MapLibreMap({
        container: containerRef.current, style: STYLE, center: [-98, 39], zoom: 3.25,
        minZoom: 1.5, maxZoom: 14, attributionControl: false,
      })
    } catch {
      // External WebGL initialization has failed; report it to the surrounding UI.
      // eslint-disable-next-line react/set-state-in-effect
      setError('地图图形初始化失败；搜索、程序记录和官方航图仍可使用。')
      return
    }
    mapRef.current = map
    map.addControl(new NavigationControl({ showCompass: true }), 'bottom-right')
    map.addControl(new ScaleControl({ unit: 'nautical' }), 'bottom-left')
    const emitBounds = () => {
      const b = map.getBounds()
      latest.current.onBounds([
        Math.max(-180, b.getWest()), Math.max(-90, b.getSouth()),
        Math.min(180, b.getEast()), Math.min(90, b.getNorth()),
      ])
    }
    map.on('load', () => {
      map.addSource('reference-grid', { type: 'geojson', data: createReferenceGrid() })
      map.addLayer({ id: 'reference-grid-lines', type: 'line', source: 'reference-grid',
        paint: { 'line-color': '#28506a', 'line-width': 0.65, 'line-opacity': 0.38 } })
      map.addSource('aviation', { type: 'geojson', data: latest.current.features })
      map.addSource('procedure', { type: 'geojson', data: latest.current.procedure })
      map.addLayer({ id: 'aviation-lines', type: 'line', source: 'aviation',
        filter: ['==', ['geometry-type'], 'LineString'],
        paint: { 'line-color': '#779dcc', 'line-width': 1.7, 'line-opacity': 0.8 } })
      map.addLayer({ id: 'aviation-points', type: 'circle', source: 'aviation',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-color': '#61d8df', 'circle-radius': 4, 'circle-stroke-color': '#082635', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'procedure-lines', type: 'line', source: 'procedure',
        filter: ['==', ['geometry-type'], 'LineString'],
        paint: { 'line-color': '#f5bc70', 'line-width': 3 } })
      map.addLayer({ id: 'procedure-points', type: 'circle', source: 'procedure',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-color': '#f5bc70', 'circle-radius': 5, 'circle-stroke-width': 2, 'circle-stroke-color': '#13222b' } })
      for (const layer of ['aviation-points', 'aviation-lines']) {
        map.on('click', layer, (event) => {
          const properties = event.features?.[0]?.properties
          if (properties) latest.current.onFeature(properties)
        })
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      emitBounds()
    })
    map.on('moveend', emitBounds)
    return () => { mapRef.current = null; map.remove() }
  }, [])

  useEffect(() => {
    const source = mapRef.current?.getSource('aviation') as GeoJSONSource | undefined
    source?.setData(features)
  }, [features])
  useEffect(() => {
    const source = mapRef.current?.getSource('procedure') as GeoJSONSource | undefined
    source?.setData(procedure)
  }, [procedure])
  useEffect(() => {
    if (focus) mapRef.current?.flyTo({ center: focus, zoom: 10, duration: 800 })
  }, [focus])

  return <>
    <div ref={containerRef} className="map-canvas" aria-label="航空资料地图" />
    {error && <div className="map-error" role="status">{error}</div>}
  </>
}

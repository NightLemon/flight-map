import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  AttributionControl,
  Map as MapLibreMap,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  type GeoJSONSource,
  type MapLayerMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { GeoJsonProperties } from 'geojson'
import { AIRPORT_MIN_ZOOM, EMPTY_MAP, normalizeMapBounds, type MapData, type MapViewport } from './map-data'
import 'maplibre-gl/dist/maplibre-gl.css'
import './AviationMap.css'

setWorkerUrl(workerUrl)

const BASEMAP_SOURCE = 'openstreetmap'
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    [BASEMAP_SOURCE]: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>',
    },
  },
  layers: [
    { id: 'night-background', type: 'background', paint: { 'background-color': '#07111c' } },
    { id: 'openstreetmap-raster', type: 'raster', source: BASEMAP_SOURCE },
  ],
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

function splitAviationFeatures(data: MapData) {
  const airports: MapData['features'] = []
  const other: MapData['features'] = []
  for (const feature of data.features) {
    if (feature.geometry?.type === 'Point' && feature.properties?.kind === 'airport') airports.push(feature)
    else other.push(feature)
  }
  return {
    airports: { type: 'FeatureCollection', features: airports } satisfies MapData,
    other: { type: 'FeatureCollection', features: other } satisfies MapData,
  }
}

function selectedPoint(coordinates: [number, number] | null): MapData {
  if (!coordinates) return EMPTY_MAP
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates } }] }
}

type Props = {
  features: MapData
  procedure: MapData
  focus: [number, number] | null
  highlight?: [number, number] | null
  onFeature: (properties: NonNullable<GeoJsonProperties>) => void
  onViewport: (viewport: MapViewport | null) => void
}

export function AviationMap({ features, procedure, focus, highlight = focus, onFeature, onViewport }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const latest = useRef({ features, procedure, focus, highlight, onFeature, onViewport })
  const [error, setError] = useState('')
  const [basemapState, setBasemapState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [clusterCount, setClusterCount] = useState(0)
  const [position, setPosition] = useState({ longitude: -98, latitude: 39, zoom: 3.25 })
  useLayoutEffect(() => { latest.current = { features, procedure, focus, highlight, onFeature, onViewport } }, [features, procedure, focus, highlight, onFeature, onViewport])

  useEffect(() => {
    if (!containerRef.current) return
    let map: MapLibreMap
    let alive = true
    let movementEpoch = 0
    try {
      map = new MapLibreMap({
        container: containerRef.current, style: STYLE, center: [-98, 39], zoom: 3.25,
        minZoom: 1.5, maxZoom: 19, attributionControl: false, localIdeographFontFamily: 'Arial, sans-serif',
        locale: {
          'CooperativeGesturesHandler.WindowsHelpText': '按住 Ctrl 并滚动鼠标来缩放地图，或使用右下角 ＋ / −',
          'CooperativeGesturesHandler.MacHelpText': '按住 ⌘ 并滚动来缩放地图，或使用右下角 ＋ / −',
          'CooperativeGesturesHandler.MobileHelpText': '使用双指移动或缩放地图',
        },
      })
    } catch {
      // External WebGL initialization has failed; report it to the surrounding UI.
      // eslint-disable-next-line react/set-state-in-effect
      setError('地图图形初始化失败；请使用搜索查看资料。')
      return
    }
    mapRef.current = map
    const narrow = window.matchMedia('(max-width: 760px)')
    // Narrow layouts must remain page-scrollable without disabling map zoom entirely.
    const updateWheel = () => { if (narrow.matches) map.cooperativeGestures.enable(); else map.cooperativeGestures.disable() }
    const updateClusterCount = () => {
      if (!alive || !map.getLayer('airport-clusters')) return
      setClusterCount(map.queryRenderedFeatures({ layers: ['airport-clusters'] }).length)
    }
    const emitViewport = () => {
      const bounds = map.getBounds()
      const center = map.getCenter()
      const zoom = map.getZoom()
      setPosition({ longitude: center.lng, latitude: center.lat, zoom })
      latest.current.onViewport({ bounds: normalizeMapBounds([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()]), zoom })
      updateClusterCount()
    }
    const revealCluster = async (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      const clusterId = feature?.properties?.cluster_id
      if (feature?.geometry.type !== 'Point' || typeof clusterId !== 'number') return
      const source = map.getSource('airports') as GeoJSONSource | undefined
      if (!source) return
      const clickedFeatures = latest.current.features
      const clickedEpoch = movementEpoch
      try {
        const zoom = await source.getClusterExpansionZoom(clusterId)
        if (!alive || mapRef.current !== map || map.getSource('airports') !== source
          || latest.current.features !== clickedFeatures || movementEpoch !== clickedEpoch) return
        map.easeTo({ center: feature.geometry.coordinates as [number, number], zoom })
      } catch {
        // The map can unmount or receive new data before the worker replies.
      }
    }
    updateWheel()
    narrow.addEventListener('change', updateWheel)
    map.addControl(new AttributionControl({ compact: false }), 'bottom-right')
    map.addControl(new NavigationControl({ showCompass: true }), 'bottom-right')
    map.addControl(new ScaleControl({ unit: 'nautical' }), 'bottom-left')
    map.once('style.load', () => {
      if (!alive) return
      map.addSource('reference-grid', { type: 'geojson', data: createReferenceGrid() })
      map.addLayer({ id: 'reference-grid-lines', type: 'line', source: 'reference-grid',
        paint: { 'line-color': '#28506a', 'line-width': 0.65, 'line-opacity': 0.38 } }, 'openstreetmap-raster')
      const current = splitAviationFeatures(latest.current.features)
      map.addSource('airports', { type: 'geojson', data: current.airports, cluster: true, clusterRadius: 40, clusterMaxZoom: 9 })
      map.addSource('aviation', { type: 'geojson', data: current.other })
      map.addSource('procedure', { type: 'geojson', data: latest.current.procedure })
      map.addSource('selected-point', { type: 'geojson', data: selectedPoint(latest.current.highlight) })
      map.addLayer({ id: 'aviation-lines', type: 'line', source: 'aviation',
        filter: ['all', ['==', ['geometry-type'], 'LineString'], ['!=', ['get', 'kind'], 'runway']],
        paint: { 'line-color': '#8154bc', 'line-width': 2.4, 'line-opacity': 0.85, 'line-dasharray': [4, 2] } })
      map.addLayer({ id: 'runway-lines', type: 'line', source: 'aviation',
        filter: ['==', ['get', 'kind'], 'runway'], layout: { 'line-cap': 'round' },
        paint: { 'line-color': '#df6e19', 'line-width': ['interpolate', ['linear'], ['zoom'], 10, 3, 14, 7], 'line-opacity': 0.95 } })
      map.addLayer({ id: 'aviation-points', type: 'circle', source: 'aviation',
        filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-color': ['match', ['get', 'kind'], 'navaid', '#247fc1', '#d33779'], 'circle-radius': ['match', ['get', 'kind'], 'navaid', 6, 3.5], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'navaid-rings', type: 'circle', source: 'aviation', filter: ['==', ['get', 'kind'], 'navaid'],
        paint: { 'circle-color': '#00000000', 'circle-radius': 9, 'circle-stroke-color': '#247fc1', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'aviation-identifiers', type: 'symbol', source: 'aviation', minzoom: 10,
        filter: ['==', ['geometry-type'], 'Point'],
        layout: { 'text-field': ['get', 'identifier'], 'text-font': ['Arial'], 'text-size': 11, 'text-offset': [0, 1], 'text-anchor': 'top' },
        paint: { 'text-color': '#192333', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 } })
      map.addLayer({ id: 'aviation-line-labels', type: 'symbol', source: 'aviation', minzoom: 10,
        filter: ['==', ['geometry-type'], 'LineString'],
        layout: { 'symbol-placement': 'line', 'text-field': ['get', 'identifier'], 'text-font': ['Arial'], 'text-size': 11 },
        paint: { 'text-color': '#4f286e', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 } })
      map.addLayer({ id: 'airport-clusters', type: 'circle', source: 'airports', minzoom: AIRPORT_MIN_ZOOM, filter: ['has', 'point_count'],
        paint: { 'circle-color': '#147b91', 'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'], 2, 13, 50, 19, 250, 25], 'circle-stroke-color': '#d9f8fa', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'airport-cluster-count', type: 'symbol', source: 'airports', minzoom: AIRPORT_MIN_ZOOM, filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Arial'], 'text-size': 11 }, paint: { 'text-color': '#f6ffff' } })
      map.addLayer({ id: 'airport-points', type: 'circle', source: 'airports', minzoom: AIRPORT_MIN_ZOOM, filter: ['!', ['has', 'point_count']],
        paint: { 'circle-color': '#73e5ec', 'circle-radius': 4.5, 'circle-stroke-color': '#06222e', 'circle-stroke-width': 1.5 } })
      map.addLayer({ id: 'airport-identifiers', type: 'symbol', source: 'airports', minzoom: 10, filter: ['!', ['has', 'point_count']],
        layout: { 'text-field': ['get', 'identifier'], 'text-font': ['Arial'], 'text-size': 11, 'text-offset': [0, 1], 'text-anchor': 'top', 'text-allow-overlap': false },
        paint: { 'text-color': '#e3fbfc', 'text-halo-color': '#06222e', 'text-halo-width': 1.3 } })
      map.addLayer({ id: 'procedure-lines', type: 'line', source: 'procedure',
        filter: ['==', ['geometry-type'], 'LineString'], paint: { 'line-color': '#f5bc70', 'line-width': 3 } })
      map.addLayer({ id: 'procedure-points', type: 'circle', source: 'procedure',
        filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-color': '#f5bc70', 'circle-radius': 5, 'circle-stroke-width': 2, 'circle-stroke-color': '#13222b' } })
      map.addLayer({ id: 'selected-point-ring', type: 'circle', source: 'selected-point',
        paint: { 'circle-radius': 11, 'circle-color': '#00000000', 'circle-stroke-color': '#fff5aa', 'circle-stroke-width': 2.5, 'circle-stroke-opacity': 0.95 } })
      map.on('click', 'airport-clusters', (event) => { void revealCluster(event) })
      map.on('mouseenter', 'airport-clusters', () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', 'airport-clusters', () => { map.getCanvas().style.cursor = '' })
      for (const layer of ['aviation-points', 'aviation-lines', 'runway-lines', 'airport-points']) {
        map.on('click', layer, (event) => {
          const properties = event.features?.[0]?.properties
          if (properties) latest.current.onFeature(properties)
        })
        map.on('mouseenter', layer, () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', layer, () => { map.getCanvas().style.cursor = '' })
      }
      emitViewport()
    })
    map.on('sourcedata', (event) => {
      if (event.sourceId === BASEMAP_SOURCE && event.tile) setBasemapState('ready')
    })
    map.on('error', (event) => {
      if ((event as typeof event & { sourceId?: string }).sourceId === BASEMAP_SOURCE) setBasemapState('error')
    })
    map.on('movestart', () => { movementEpoch += 1; latest.current.onViewport(null) })
    map.on('moveend', emitViewport)
    map.on('idle', updateClusterCount)
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(containerRef.current)
    return () => {
      alive = false
      narrow.removeEventListener('change', updateWheel)
      observer.disconnect()
      mapRef.current = null
      map.remove()
    }
  }, [])

  useEffect(() => {
    const current = splitAviationFeatures(features)
    ;(mapRef.current?.getSource('airports') as GeoJSONSource | undefined)?.setData(current.airports)
    ;(mapRef.current?.getSource('aviation') as GeoJSONSource | undefined)?.setData(current.other)
  }, [features])
  useEffect(() => { (mapRef.current?.getSource('procedure') as GeoJSONSource | undefined)?.setData(procedure) }, [procedure])
  useEffect(() => {
    ;(mapRef.current?.getSource('selected-point') as GeoJSONSource | undefined)?.setData(selectedPoint(highlight))
  }, [highlight])
  useEffect(() => {
    if (focus) mapRef.current?.flyTo({ center: focus, zoom: 10, duration: 800 })
  }, [focus])

  return <>
    <div ref={containerRef} className="map-canvas" aria-label="航空资料地图" data-feature-count={features.features.length} data-longitude={position.longitude} data-latitude={position.latitude} data-zoom={position.zoom} data-basemap-state={basemapState} data-cluster-count={clusterCount} />
    <output className="map-position" aria-label="地图中心">{position.latitude.toFixed(4)}°, {position.longitude.toFixed(4)}° · Z{position.zoom.toFixed(1)}</output>
    {basemapState === 'error' && <div className="map-error map-basemap-notice" role="status">底图瓦片暂时无法加载；仍可搜索和查看已加载的航空资料。</div>}
    {error && <div className="map-error" role="status">{error}</div>}
  </>
}

import type { FeatureCollection, GeoJsonProperties, Geometry } from 'geojson'

export type MapData = FeatureCollection<Geometry, GeoJsonProperties>
export const EMPTY_MAP: MapData = { type: 'FeatureCollection', features: [] }
export type Bounds = [number, number, number, number]

export function normalizeMapBounds([west, south, east, north]: Bounds): Bounds {
  const clampLatitude = (latitude: number) => Math.max(-90, Math.min(90, latitude))
  if (east - west >= 360) return [-180, clampLatitude(south), 180, clampLatitude(north)]
  const wrapLongitude = (longitude: number) => ((longitude + 180) % 360 + 360) % 360 - 180
  return [wrapLongitude(west), clampLatitude(south), wrapLongitude(east), clampLatitude(north)]
}

import type { FeatureCollection, GeoJsonProperties, Geometry } from 'geojson'

export type MapData = FeatureCollection<Geometry, GeoJsonProperties>
export const EMPTY_MAP: MapData = { type: 'FeatureCollection', features: [] }
export type Bounds = [number, number, number, number]

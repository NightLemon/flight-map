import { describe, expect, it } from 'vitest'
import { normalizeMapBounds, type Bounds } from '../src/map-data'

describe('map viewport bounds', () => {
  it.each<{ name: string; input: Bounds; expected: Bounds }>([
    { name: 'ordinary continental viewport', input: [-125, 25, -65, 50], expected: [-125, 25, -65, 50] },
    { name: 'eastward crossing of the date line', input: [170, -30, 190, 30], expected: [170, -30, -170, 30] },
    { name: 'westward crossing of the date line', input: [-190, -30, -170, 30], expected: [170, -30, -170, 30] },
    { name: 'full world', input: [-180, -90, 180, 90], expected: [-180, -90, 180, 90] },
    { name: 'full world after horizontal panning', input: [170, -90, 530, 90], expected: [-180, -90, 180, 90] },
    { name: 'multiple visible worlds', input: [-540, -100, 540, 100], expected: [-180, -90, 180, 90] },
    { name: 'viewport inside an eastern world copy', input: [190, 20, 200, 40], expected: [-170, 20, -160, 40] },
    { name: 'viewport inside a western world copy', input: [-200, 20, -190, 40], expected: [160, 20, 170, 40] },
  ])('$name', ({ input, expected }) => {
    expect(normalizeMapBounds(input)).toEqual(expected)
  })
})

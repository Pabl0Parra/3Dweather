// The 12 regional maps (mirrors pipeline/regions.py; tests/test_regions.py keeps them in step).
/** `bounds` is the map's extent: west, south, east, north in degrees. */
export type RegionInfo = { slug: string; title: string; description: string; tz: string; bounds: [number, number, number, number] };

export const REGIONS: RegionInfo[] = [
  { slug: "united-states", title: "United States", tz: "America/New_York", bounds: [-127, 23.5, -65, 50],
    description: "Wind, rain and clouds over the United States and its coasts." },
  { slug: "united-kingdom", title: "United Kingdom", tz: "Europe/London", bounds: [-11.5, 49.3, 3, 61],
    description: "Wind, rain and clouds over Britain, Ireland and the seas around them." },
  { slug: "scotland", title: "Scotland", tz: "Europe/London", bounds: [-11, 54, 1, 61.3],
    description: "Wind, rain and clouds over Scotland, the Hebrides, Orkney and Shetland." },
  { slug: "ireland", title: "Ireland", tz: "Europe/Dublin", bounds: [-14, 50.5, -3, 56.5],
    description: "Wind, rain and clouds over the island of Ireland and its coasts." },
  { slug: "europe", title: "Europe", tz: "Europe/London", bounds: [-39.9609375, 33.09469096091206, 41.8359375, 71.9882746742671],
    description: "Wind, rain and clouds over Europe and the North Atlantic, from Iceland to the Mediterranean." },
  { slug: "india", title: "India", tz: "Asia/Kolkata", bounds: [66, 5, 93, 25],
    description: "Wind, rain and clouds over India, Sri Lanka, the Arabian Sea and the Bay of Bengal." },
  { slug: "west-pacific", title: "East Asia and the West Pacific", tz: "Asia/Tokyo", bounds: [100, 0, 150, 46],
    description: "Wind, rain and clouds from the South China Sea to Japan and Guam." },
  { slug: "philippines", title: "Philippines", tz: "Asia/Manila", bounds: [115, 4, 128, 21.5],
    description: "Wind, rain and clouds over the Philippine islands and the seas around them." },
  { slug: "australia", title: "Australia", tz: "Australia/Sydney", bounds: [110, -45, 156, -9],
    description: "Wind, rain and clouds over Australia and its coasts, from Darwin to Hobart." },
  { slug: "new-zealand", title: "New Zealand", tz: "Pacific/Auckland", bounds: [165, -48, 179.5, -33.5],
    description: "Wind, rain and clouds over New Zealand and the Tasman Sea's eastern side." },
  { slug: "canada", title: "Canada", tz: "America/Toronto", bounds: [-140, 41.5, -52, 61],
    description: "Wind, rain and clouds over southern Canada, from the Pacific coast to Newfoundland." },
  { slug: "south-africa", title: "South Africa", tz: "Africa/Johannesburg", bounds: [14, -36.5, 34, -26],
    description: "Wind, rain and clouds over South Africa's coasts, from the Atlantic to the Indian Ocean." },
];

export const regionBySlug = (slug: string): RegionInfo | undefined => REGIONS.find((r) => r.slug === slug);

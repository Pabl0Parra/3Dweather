// The 12 regional maps (mirrors pipeline/regions.py; tests/test_regions.py keeps them in step).
export type RegionInfo = { slug: string; title: string; description: string; tz: string };

export const REGIONS: RegionInfo[] = [
  { slug: "united-states", title: "United States", tz: "America/New_York",
    description: "Wind, rain and clouds over the United States and its coasts." },
  { slug: "united-kingdom", title: "United Kingdom", tz: "Europe/London",
    description: "Wind, rain and clouds over Britain, Ireland and the seas around them." },
  { slug: "scotland", title: "Scotland", tz: "Europe/London",
    description: "Wind, rain and clouds over Scotland, the Hebrides, Orkney and Shetland." },
  { slug: "ireland", title: "Ireland", tz: "Europe/Dublin",
    description: "Wind, rain and clouds over the island of Ireland and its coasts." },
  { slug: "europe", title: "Europe", tz: "Europe/London",
    description: "Wind, rain and clouds over Europe and the North Atlantic, from Iceland to the Mediterranean." },
  { slug: "india", title: "India", tz: "Asia/Kolkata",
    description: "Wind, rain and clouds over India, Sri Lanka, the Arabian Sea and the Bay of Bengal." },
  { slug: "west-pacific", title: "East Asia and the West Pacific", tz: "Asia/Tokyo",
    description: "Wind, rain and clouds from the South China Sea to Japan and Guam." },
  { slug: "philippines", title: "Philippines", tz: "Asia/Manila",
    description: "Wind, rain and clouds over the Philippine islands and the seas around them." },
  { slug: "australia", title: "Australia", tz: "Australia/Sydney",
    description: "Wind, rain and clouds over Australia and its coasts, from Darwin to Hobart." },
  { slug: "new-zealand", title: "New Zealand", tz: "Pacific/Auckland",
    description: "Wind, rain and clouds over New Zealand and the Tasman Sea's eastern side." },
  { slug: "canada", title: "Canada", tz: "America/Toronto",
    description: "Wind, rain and clouds over southern Canada, from the Pacific coast to Newfoundland." },
  { slug: "south-africa", title: "South Africa", tz: "Africa/Johannesburg",
    description: "Wind, rain and clouds over South Africa's coasts, from the Atlantic to the Indian Ocean." },
];

export const regionBySlug = (slug: string): RegionInfo | undefined => REGIONS.find((r) => r.slug === slug);

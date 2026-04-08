---
name: web-images
description: >-
  Search and download royalty-free images from Unsplash and Pixabay.

  Use this skill when the user wants to find, browse, or download images
  from stock photo services. Supports searching by keyword, filtering by
  orientation, and downloading in various sizes.

  Common scenarios:
  - searching for stock photos by keyword
  - downloading images for a project
  - browsing image results from multiple sources
  - finding images with specific dimensions or orientation
user-invocable: true
---

# Web Images — Search & Download from Unsplash and Pixabay

## API Keys

```
UNSPLASH_ACCESS_KEY=G2TF5IdgvZL1-BS64VVvK10Y0VRgTWDC1ZqGCOhYI3s
PIXABAY_API_KEY=55299736-186f0b347fac0e18813599db9
```

## Workflow

When the user asks to search for images:

1. **Parse the request** — extract the search query, optional orientation (`landscape`, `portrait`, `squarish`), desired count (default 5 per source), and preferred source (`unsplash`, `pixabay`, or `both` — default `both`).

2. **Search both sources in parallel** using the commands below.

3. **Present results** in a clean table per source with: index number, description/tags, photographer, dimensions, and preview URL.

4. **If the user wants to download**, ask which image(s) by index and desired size, then download to the specified directory (default `./images/`).

## Search Commands

### Unsplash

```bash
curl -s "https://api.unsplash.com/search/photos?query=QUERY&per_page=COUNT&orientation=ORIENTATION" \
  -H "Authorization: Client-ID G2TF5IdgvZL1-BS64VVvK10Y0VRgTWDC1ZqGCOhYI3s"
```

**Parameters:**
- `query` (required): search terms, URL-encoded
- `per_page`: 1-30 (default 5)
- `orientation`: `landscape`, `portrait`, `squarish` (optional)
- `page`: page number for pagination

**Response fields to extract from `results[]`:**
- `id` — unique photo ID
- `alt_description` — image description
- `width`, `height` — original dimensions
- `user.name` — photographer name
- `urls.small` — 400px preview
- `urls.regular` — 1080px download
- `urls.full` — full resolution download
- `urls.raw` — raw (append `&w=WIDTH` to resize)
- `links.download_location` — **must trigger this** to comply with Unsplash API guidelines

### Pixabay

```bash
curl -s "https://pixabay.com/api/?key=55299736-186f0b347fac0e18813599db9&q=QUERY&per_page=COUNT&orientation=ORIENTATION&image_type=photo"
```

**Parameters:**
- `q` (required): search terms, URL-encoded (spaces as `+`)
- `per_page`: 3-200 (default 5)
- `orientation`: `all`, `horizontal`, `vertical` (optional)
- `image_type`: `photo`, `illustration`, `vector` (default `photo`)
- `page`: page number for pagination

**Response fields to extract from `hits[]`:**
- `id` — unique image ID
- `tags` — comma-separated tags
- `user` — photographer name
- `imageWidth`, `imageHeight` — original dimensions
- `previewURL` — 150px preview
- `webformatURL` — 640px download
- `largeImageURL` — 1280px download

## Download Commands

### Downloading from Unsplash

**Important:** Before downloading, trigger the download event to comply with Unsplash guidelines:

```bash
curl -s "DOWNLOAD_LOCATION_URL" \
  -H "Authorization: Client-ID G2TF5IdgvZL1-BS64VVvK10Y0VRgTWDC1ZqGCOhYI3s" > /dev/null
```

Then download the actual image:

```bash
mkdir -p ./images
curl -sL "IMAGE_URL" -o "./images/unsplash-PHOTO_ID.jpg"
```

**Size options:**
- `urls.small` — 400px wide (fast preview)
- `urls.regular` — 1080px wide (good for most uses)
- `urls.full` — full resolution (large file)
- `urls.raw&w=WIDTH` — custom width

### Downloading from Pixabay

```bash
mkdir -p ./images
curl -sL "IMAGE_URL" -o "./images/pixabay-IMAGE_ID.jpg"
```

**Size options:**
- `webformatURL` — 640px wide (good for most uses)
- `largeImageURL` — 1280px wide (high quality)

## Presenting Results

Format search results as a table like this:

```
### Unsplash Results (query: "mountain")

| # | Description          | Photographer | Size       | Preview |
|---|----------------------|------------- |------------|---------|
| 1 | Snow-capped mountain | John Doe     | 6000x4000  | [link]  |
| 2 | Mountain lake        | Jane Smith   | 4000x3000  | [link]  |

### Pixabay Results (query: "mountain")

| # | Tags                 | Photographer | Size       | Preview |
|---|----------------------|------------- |------------|---------|
| 3 | mountain, nature     | PhotoUser    | 5000x3500  | [link]  |
| 4 | alps, snow, peak     | NatureShots  | 4200x2800  | [link]  |
```

Use continuous numbering across both sources so the user can refer to any image by a single index number.

## Attribution

- **Unsplash**: Photos are free to use. Attribution is appreciated but not required. Always trigger the `download_location` endpoint.
- **Pixabay**: Photos are free for commercial and non-commercial use. No attribution required.

## Rate Limits

- **Unsplash**: 50 requests/hour (free/demo tier)
- **Pixabay**: 100 requests/minute (free tier)

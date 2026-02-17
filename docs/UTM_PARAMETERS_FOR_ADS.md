# UTM Parameters for Ad URLs (Tracker & Backend)

Your tracker script and `capture_visit` backend read these URL parameters from the landing page. Use them in **Facebook Ads**, **TikTok Ads**, and **Google Ads** so visits and orders are attributed correctly.

---

## Parameters the script reads (in order of priority)

| URL parameter   | Backend field    | Used for                          |
|-----------------|------------------|------------------------------------|
| `utm_campaign` or `campaign_id` | `utm_campaign` | Campaign name in dashboard         |
| `utm_source` or `source`       | `utm_source`   | Platform (facebook, tiktok, google) |
| `utm_medium` or `placement`    | `utm_medium`   | Placement (feed, story, reels, cpc) |
| `ad_id` or `utm_content`       | `ad_id`       | Ad-level reporting & matching       |
| `adset_id`                      | `ad_adset_name` | Ad set / ad group name            |

- **Click IDs** (`fbclid`, `ttclid`, `gclid`) are captured for reference but attribution is done via the UTM/custom params above.
- **Last-touch attribution**: if the user lands without params (e.g. direct link), the script reuses the last stored params from the first click.

---

## 1. Facebook / Meta Ads

**Where to set:**  
Ad level → **Destination** → **Website URL** → add parameters to the landing URL (or use “URL parameters” in the ad).

**Recommended URL parameters:**

```
utm_campaign={{campaign.name}}
utm_source=facebook
utm_medium={{placement}}
ad_id={{ad.id}}
adset_id={{adset.name}}
```

- `{{campaign.name}}`, `{{adset.name}}`, `{{ad.id}}` are **Facebook’s dynamic parameters** (replace with your campaign/adset/ad names and IDs when the ad is served).
- Use **utm_medium** for placement if you don’t use dynamic `{{placement}}`, e.g. `utm_medium=feed`, `utm_medium=story`, `utm_medium=reels`.

**Example final URL:**

```
https://yoursite.com/landing?utm_campaign=Winter_Sale&utm_source=facebook&utm_medium=feed&ad_id=123456789&adset_id=Winter_AdSet_1
```

---

## 2. TikTok Ads

**Where to set:**  
Campaign / Ad Group / Ad → **Destination** → **Website** → **URL parameters** (or append to landing URL).

**Recommended URL parameters:**

```
utm_campaign={campaign_name}
utm_source=tiktok
utm_medium={placement}
ad_id={ad_id}
adset_id={adset_name}
```

- TikTok supports **URL parameters** in the dashboard; use their placeholders where available (e.g. `{campaign_name}`, `{ad_id}`, `{placement}`).
- If placeholders aren’t available, use fixed values: e.g. `utm_source=tiktok`, `utm_medium=feed`, and set `ad_id` / `adset_id` per ad if possible.

**Example final URL:**

```
https://yoursite.com/landing?utm_campaign=Winter_Sale&utm_source=tiktok&utm_medium=feed&ad_id=789012&adset_id=AdSet_1
```

---

## 3. Google Ads

**Where to set:**  
Campaign or account level: **Goals** → **Conversions** → or in the **Final URL** / **Final URL suffix** (or use the “Value track” / custom parameters in the URL).

**Recommended URL parameters:**

```
utm_campaign={campaignid}
utm_source=google
utm_medium=cpc
utm_content={creative}
ad_id={creative}
adset_id={adgroupid}
```

- **Value track (optional):**  
  `utm_campaign={campaignid}`, `utm_content={creative}` (or `{creative}` as `ad_id`), `adset_id={adgroupid}`.
- **utm_medium** is often `cpc` for Search; for Display/YouTube you can use `utm_medium=display` or `utm_medium=youtube`.
- The tracker accepts **utm_content** as a fallback for **ad_id**, so you can use `utm_content={creative}` and not duplicate with `ad_id` if you prefer.

**Example final URL:**

```
https://yoursite.com/landing?utm_campaign=12345&utm_source=google&utm_medium=cpc&utm_content=67890&ad_id=67890&adset_id=11111
```

---

## Quick reference: minimal set per platform

| Platform   | Minimum to set for campaign/ad reporting                          |
|-----------|--------------------------------------------------------------------|
| **Facebook** | `utm_campaign`, `utm_source=facebook`, `utm_medium`, `ad_id`, `adset_id` (use dynamic params when possible) |
| **TikTok**   | `utm_campaign`, `utm_source=tiktok`, `utm_medium`, `ad_id`, `adset_id` |
| **Google**   | `utm_campaign`, `utm_source=google`, `utm_medium`, `ad_id` or `utm_content` (and `adset_id` / ad group if you want ad set level) |

Use the **same parameter names** in the table at the top so the script and backend can attribute visits and match orders to the right campaign/ad set/ad.

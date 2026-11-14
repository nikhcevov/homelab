# HDD price research

[Repository overview](../README.md)

Sources: [snapshots](hdd-prices/2026-11-09.csv), [validator and aggregator](../scripts/hdd-price-index.py), [Proxmox migration](proxmox-migration.md).

Run commands from the repository root.

This document is the method behind the storage decision in the
[Proxmox migration](proxmox-migration.md#drive-price-per-terabyte). It records
what was measured, how, and how to repeat it later so the numbers stay
comparable. Snapshots are append-only: never rewrite an existing file.

## Question

Which capacities offered the lowest cost per terabyte, how did that change over
time, and what should be bought next given the growth rate of the data set?
Reliability is a separate input: the cheapest drive is worthless if the model
fails often.

## Definitions

- **$/TB** = total price divided by capacity in decimal terabytes, exactly as the
  label counts them (1 TB = 1 000 GB). No binary GiB conversion.
- **Snapshot** = one CSV file per collection date, `docs/hdd-prices/<date>.csv`.
- **Series** = a fixed product class. One series never mixes new and non-new stock.
- **Row** = the cheapest qualifying in-stock listing for one capacity in one
  series on one date. Not every listing, only the minimum.
- **Condition**: `new`, `refurb`, `used`. `renewed`, `recertified`, and
  `seller-refurbished` all map to `refurb`; the exact label goes in `drive` if it
  matters.
- **Recording**: `cmr`, `smr`, `unknown`. Only CMR belongs in a parity array.

## Snapshot protocol

1. The snapshot date is the collection date and equals the file name.
2. Collect one row per capacity: 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 28, 32 TB.
   Add a capacity only from a full snapshot onward; gaps are allowed, invented
   values are not.
3. Record the cheapest in-stock unit, its total price, and its $/TB. If the source
   publishes only $/TB, leave `price_usd` empty; the validator checks consistency
   when both are present.
4. Exclude SMR, pre-orders, and listings priced more than 1.5 times the next
   cheapest unit of the same capacity (usually a third-party marketplace seller).
   If such a listing was the only option, record it and say so in `drive`.
5. Never mix channels in one series. New retail, eBay used, and refurbished
   resellers are separate series.
6. USD only, US region, excluding tax and shipping.
7. One row per `(date, series, capacity)`; the validator rejects duplicates.
8. Keep every snapshot. Corrections get a new file and a note here; history is not
   edited.

## Series

| Series | Meaning |
| --- | --- |
| `new-cmr` | cheapest new CMR SATA drive per capacity, NAS or enterprise class |
| `new-sata` | cheapest new SATA drive of any recording technology |
| `refurb-sata` | cheapest refurbished SATA drive |
| `refurb-sas` | cheapest refurbished SAS drive, needs an HBA |
| `blended` | new and non-new together, for a market median |

The collection uses `new-cmr`: the tracker badges every listing with condition and
recording, and the per-capacity minimum sometimes lands on an enterprise model.
That is deliberate — the series measures the cheapest new CMR terabyte, not a
marketing class.

## Snapshot format

The schema is fixed by the script, not by this prose. Header:

```text
date,series,capacity_tb,condition,recording,price_usd,price_per_tb,drive,url
```

Example row:

```text
2026-11-09,new-cmr,18,new,cmr,689.00,38.28,Seagate Exos X18 ST18000NM000J,https://terabytewise.com/price-per-tb-history
```

`price_usd` may be empty; `price_per_tb` is required. When both are present they
must agree within 1%. The file name must equal the `date` column.

```bash
scripts/hdd-price-index.py                       # validate every snapshot
scripts/hdd-price-index.py --date 2026-11-09     # per-capacity table
scripts/hdd-price-index.py --date 2026-11-09 --format md
scripts/hdd-price-index.py --compare 2026-09-01 --date 2026-11-09
```

The validator refuses a snapshot with fewer than 8 capacities, which catches a
half-finished collection. Pass `--min-capacities` only for a deliberately partial
series.

### diskprices.com source

```bash
scripts/hdd-price-index.py --fetch-diskprices
scripts/hdd-price-index.py --date <today> --series new-sata
```

One request fetches the whole US table; the script keeps new, single-unit,
non-SAS rows from the internal 3.5" HDD category at the protocol capacities and
takes the lowest published $/TB per capacity. The page does not state recording
technology, so every row is `recording=unknown` in series `new-sata`; it cannot
feed `new-cmr`. The cheapest rows are therefore often SMR, surveillance, or
white-label drives (e.g. 8 TB BarraCuda, 18 TB MDD). Total price is rounded to
whole dollars by the site, so it can differ from a retailer price by under $1.
The URL is the plain Amazon `/dp/<ASIN>` link without the affiliate tag. The
command writes `<today>.csv` and refuses to run if that file exists; two
sources on one date need separate dates because snapshots are never edited.

## Aggregation

- **Sweet spot** = the capacity with the lowest $/TB in the series. Computed as
  `argmin`, not smoothed.
- **Median and mean** are taken across capacities, one value per capacity, so a
  capacity with many listings cannot outweigh another.
- **Change** = `(after - before) / before` per capacity and for the median.
- Percentages and medians are recomputed from the CSV by the script; figures in
  prose are copies of that output, not independent calculations.

## Reliability method

Reliability comes from Backblaze Drive Stats, not from the price trackers:

- Use the annual report for the year in question and its model-level table.
- Inclusion thresholds: more than 250 drives and more than 50 000 drive days per
  year (quarterly and lifetime tables use lower thresholds).
- AFR = failures divided by drive-days, annualized. Read it per model.
- Compare models, never brands: the spread within one manufacturer is larger than
  the spread between manufacturers.
- The fleet is nearline 8 TB and up, running continuously. AFR from that fleet is
  not a prediction for a consumer 5400 rpm drive, but it is the best public
  model-level signal.

## Known pitfalls

- **Trackers measure different markets.** In September 2026 a 24-drive cohort had a
  blended median of $29.86/TB while a live SATA catalogue had a median near
  $45/TB. Both are correct for their method. Always name the method and the date.
- **New retail and secondhand diverge.** In the same period new retail rose 36.5%
  while the marketplace rose 21.7%; the gap widened to roughly $8/TB.
- **The sweet spot drifts.** 8 TB in 2016, 14 TB in 2020, 18 TB in 2023, 16–22 TB
  in 2026. A remembered number describes a past market.
- **The flagship and the smallest are both bad value.** Fixed cost per drive
  punishes small capacities; the launch premium punishes the largest.
- **Bulk contract prices are not retail.** Backblaze's $/GB series is a purchase
  price for thousands of drives, useful as a trend anchor only.
- **Condition labels are not interchangeable.** Manufacturer-recertified, seller-
  refurbished, renewed, and used carry different warranty and testing.
- **Capacity mix changes the median.** A catalogue that adds 30 TB drives moves
  its median with no price change at all.

## Reproducing the 2026-11-09 result

```bash
scripts/hdd-price-index.py --date 2026-11-09
```

Expected output for the recorded snapshot:

```text
series new-cmr · 13 capacities
    4 TB  $  47.32/TB     $189.27
    6 TB  $  54.76/TB     $328.57
    8 TB  $  47.52/TB     $380.17
   10 TB  $  39.99/TB     $399.95
   12 TB  $  39.17/TB     $469.99
   14 TB  $  40.55/TB     $567.75
   16 TB  $  39.16/TB     $626.49
   18 TB  $  38.28/TB     $689.00  <- sweet spot
   20 TB  $  41.50/TB     $829.99
   22 TB  $  38.59/TB     $849.00
   24 TB  $  44.17/TB    $1059.99
   28 TB  $  43.93/TB    $1229.99
   32 TB  $  43.75/TB    $1399.99
median $41.50/TB · mean $42.98/TB
```

## Historical results

Approximate, new retail where possible; early figures are Backblaze bulk
purchase prices and are marked as such. Treat them as trend, not as quotes.

| Era | Volume sweet spot | Approx $/TB | Note |
| --- | --- | --- | --- |
| 2009 | 1–2 TB | ~114 | Backblaze purchase price, $0.114/GB |
| 2011–2012 | 2–3 TB | spike | Thailand floods |
| 2014–2015 | 3–4 TB | ~30–40 | |
| 2016–2017 | 8 TB | ~30 | 8 TB was the volume drive; $0.033/GB bulk |
| 2018–2019 | 10–12 TB | ~22–28 | shucked externals undercut internals |
| 2020 | 14 TB | ~18–22 | |
| 2021–2022 | 16 TB | ~14–17 | Chia crash flooded the used market; $0.0144/GB bulk |
| 2023 | 18 TB | ~14–16 | |
| 2024 | 20 TB | ~14–16 | local low before the AI squeeze |
| 2025 | 20–24 TB | rising | demand turns in late 2025 |
| 2026 | 16–22 TB | ~38–42 | new, higher floor; not a blip |

Current snapshot table, generated by the script:

| Capacity | $/TB | Unit price |
| --- | --- | --- |
| 4 TB | $47.32 | $189.27 |
| 6 TB | $54.76 | $328.57 |
| 8 TB | $47.52 | $380.17 |
| 10 TB | $39.99 | $399.95 |
| 12 TB | $39.17 | $469.99 |
| 14 TB | $40.55 | $567.75 |
| 16 TB | $39.16 | $626.49 |
| 18 TB | $38.28 | $689.00 |
| 20 TB | $41.50 | $829.99 |
| 22 TB | $38.59 | $849.00 |
| 24 TB | $44.17 | $1059.99 |
| 28 TB | $43.93 | $1229.99 |
| 32 TB | $43.75 | $1399.99 |

## Rules that survived every cycle

1. The sweet spot sits one notch below the flagship: the top capacity carries a
   launch premium, the tier below is in volume production.
2. Small is never the best $/TB: controller, motor, heads, and enclosure cost
   roughly the same at any capacity.
3. Model beats brand for reliability, and the model-level spread is larger than
   the brand-level spread.
4. CMR only in a parity array.
5. Recertified enterprise is the cheapest capacity, at the cost of warranty and
   prior hours.
6. Buy the capacity you need when you need it; supply shocks are the worst time
   to stockpile.

## Market context, 2026-11-09

- A 24-drive cohort rose from $24.46 to $29.86 per terabyte between March and
  August 2026; new retail rose 36.5%, the marketplace 21.7%.
- Average retail HDD prices were reported up about 46% since September 2025.
- Nearline capacity is allocated through 2028 at Seagate; WD reported being sold
  out for 2026. Analysts expect the shortage to persist, not to reverse.
- Reliability: Backblaze 2025 ran 1.36% annualized failure rate across 344 196
  drives, the lowest since 2022. 14–16 TB is 52% of the fleet, 20 TB+ is 22.8%.
  The quarter's red flags were model-specific, not brand-wide.

## Sources

- [TerabyteWise price per TB history](https://terabytewise.com/price-per-tb-history) —
  per-capacity new NAS CMR minimum, daily, Amazon US. Snapshot source.
- [DatacenterDisk price benchmarks](https://datacenterdisk.com/good-price-per-tb) —
  live floors and medians by interface and condition.
- [DiskDojo H1 2026 price report](https://diskdojo.com/articles/hdd-price-report-2026-h1) —
  fixed 24-drive cohort, new versus marketplace.
- [NASdisks capacity sweet spot](https://www.nasdisks.com/articles/nas-drive-capacity-sweet-spot/) —
  sweet-spot reasoning and current medians.
- [Backblaze Drive Stats 2025](https://www.backblaze.com/blog/backblaze-drive-stats-for-2025) —
  model-level AFR.
- [Backblaze cost per gigabyte](https://www.backblaze.com/blog/hard-drive-cost-per-gigabyte) —
  bulk purchase history 2009–2022.
- [24-year cost-per-gigabyte study](https://freedom251.com/hard-drive-cost-per-gigabyte-over-24-years-a-statistical-study/) —
  long-run context.
- [diskprices.com](https://diskprices.com/) — Amazon US listings via the Product
  Advertising API, refreshed every four hours. Snapshot source for `new-sata`
  ([FAQ](https://diskprices.com/faq.html)).
- [Tom's Hardware, 46% since September](https://www.tomshardware.com/pc-components/hdds/hard-drive-prices-have-surged-by-an-average-of-46-percent-since-september-iconic-24tb-seagate-barracuda-now-usd500-as-ai-claims-another-victim)
- [The Register on Seagate allocation](https://www.theregister.com/storage/2026/07/29/ai-storage-boom-is-keeping-seagates-hard-drives-spinning/5280437)

## Revision history

- 2026-11-09: initial method, first snapshot, validator script.
- 2026-11-11: added diskprices.com as a `new-sata` source (`--fetch-diskprices`);
  validator now pins condition per series, rejects short rows, and requires
  `--date` with `--compare`.

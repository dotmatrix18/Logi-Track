# LogiTrack: Business Insights & Recommendations

**Project:** LogiTrack, Supply Chain & Logistics Performance Analytics  
**Author:** Adrish Manna · HCL GUVI Data Science (batch DSGA-C-WE-E-B15)  
**Data:** official GUVI `logitrack_*_expanded.csv` files: 15 warehouses, 75 drivers, 45 vehicles, 150 routes, and 3,000 shipments, deliveries and feedback records (shipments Jan 2024 to Dec 2025)  
**Method:** Python/Pandas cleaning and feature engineering → SQLite (PK/FK) → SQL analysis → EDA → 5 hypothesis tests (+3 supporting) → Streamlit dashboard

---

## 1. Executive summary

| KPI | Value | Rule |
|---|---|---|
| Total shipments | **3,000** | COUNT(shipment_id) |
| Total deliveries (completed) | **2,712** (90.4%) | status ∈ {Delivered, Delayed} |
| Delivery success rate | **74.4%** | Delivered / all shipments |
| Delayed / In-Transit / Cancelled | 16.0% / 4.9% / 4.7% | share of shipments |
| Average delay | **7.08 h** (median 3.18 h) | AVG(delay_hours), completed only |
| Zero-delay share | 28.6% of completed | delay_hours = 0 |
| Average customer rating | **3.89 / 5**, significantly below the 4.0 target | AVG(rating 1-5) |
| Average transit time | 1.11 days | actual_dt − shipment_dt |

**Bottom line:** delays and failed orders are the single biggest threat to customer satisfaction. Rating falls from **4.58★ for on-time deliveries to 2.84★ when an order is more than 24 h late**, and cancelled or in-transit orders average about 2★. Distance, route type and driver tenure explain almost none of the delay. The problems sit in **specific lanes, specific hubs (Jaipur, Nagpur), Monday dispatches and peak months**, all of which can be acted on.

---

## 2. Answers to the key business questions

| # | Question | Answer |
|---|---|---|
| 1 | Overall delivery success rate? | **74.4%** Delivered; 90.4% completed; only 28.6% of completed orders have zero delay. |
| 2 | Which routes have the most delays? | Lanes, not route types: **Ahmedabad→Delhi (14.1 h avg)**, Kolkata→Ahmedabad (13.2 h), Delhi→Hyderabad (12.8 h, 47% Delayed), Chennai→Kochi (11.9 h). By type: Express 7.4 h ≈ Economy 7.3 h > Standard 6.9 h. |
| 3 | Does driver experience affect performance? | Slightly: delay falls from 7.7 h (Junior) to 6.8 h (Expert) and the Delayed-status rate from 18.9% to 16.6%. Experience has **no significant link to rating** (Spearman ρ = 0.03, p = 0.10). |
| 4 | Which vehicle types are most efficient? | **Bikes**: lowest delay (6.5 h), highest success (76.9%) and highest load factor (54%). **Trucks**: highest delay (7.5 h) and only 45% utilisation, while moving 82% of total weight. |
| 5 | What influences customer satisfaction? | **Delay** (r = −0.59, r² = 35%; on-time 4.58★ vs delayed 3.91★, Cohen's d = 0.93) and **order failure** (Cancelled 1.91★, In-Transit 2.02★). Distance, weight, driver experience and warehouse capacity all have \|r\| < 0.07. |
| 6 | Seasonal patterns in delays? | No strong quarterly cycle (6.8-7.4 h), but there are **spikes in Mar-2024 (9.2 h), Dec-2024 (8.8 h) and Apr/May-2025 (8.3-8.8 h)**, with success rates dropping to 63-68%. **Monday** dispatches are the slowest (8.1 h vs about 6.8 h). |
| 7 | Which warehouses perform best? | **Delhi WH2 (78.0%)**, Patna WH15, Lucknow WH10 and Chandigarh WH11 (about 78%). Weakest: **Jaipur WH9 (67.1%, 8.3 h)** and **Nagpur WH14 (68.8%, 8.5 h)**. The spread is not statistically significant overall (χ² p = 0.42), so these are watch-list hubs. |

---

## 3. Statistical validation (α = 0.05)

| Test | Result | Decision | Business meaning |
|---|---|---|---|
| 1. Paired t-test: delivery time Q1 vs Q2 (75 drivers) | 26.63 h → 26.00 h, t = −0.58, p = 0.563 (Wilcoxon p = 0.51) | Fail to reject H₀ | Driver performance is stable; improvement will not happen without intervention. |
| 2. One-sample t-test: rating vs 4.0 | mean 3.893 (95% CI 3.856-3.931), t = −5.53, p < 0.001 | **Reject H₀** | Satisfaction is below target. Completed orders alone average 4.10, so failed and late orders cause the gap. |
| 3. Pearson: distance vs delay | r = −0.031, p = 0.106 | Fail to reject H₀ | Longer routes are not proportionally later. |
| 4. Spearman: experience vs rating | ρ = 0.030, p = 0.100 | Fail to reject H₀ | Tenure alone does not earn better ratings. |
| 5. Z-score on delay hours | μ = 7.08 h, σ = 10.68 h; 90 shipments (3.3%) above 39.1 h | 90 outliers | Extreme delays average 2.8★ and are concentrated at the Kochi (1.9× lift) and Ahmedabad (1.6×) hubs, on trucks, and on Monday/Thursday dispatches. |
| A. Welch t: rating on-time vs delayed | 4.58 vs 3.91, t = 25.0, p < 0.001, d = 0.93 | Reject H₀ | Large, practically important effect. |
| B. Pearson: delay vs rating | r = −0.59, p < 0.001 | Reject H₀ | Delay explains 35% of rating variance. |
| C. χ²: success × warehouse | χ² = 14.4, dof 14, p = 0.42 | Fail to reject H₀ | Hub differences may be noise, so monitor before restructuring. |

---

## 4. Insights (Observation → Interpretation → Business impact)

### 4.1 Delivery performance
1. **Observation:** 74.4% Delivered, 16.0% Delayed, 9.6% never completed. 71% of completed orders carry some delay.
   **Interpretation:** the "Delivered" label hides frequent small delays (up to about 20 h), so the real on-promise rate is much lower than it looks.
   **Business impact:** report two KPIs (success rate and zero-delay rate), and set a target of ≥ 80% success and ≥ 40% zero-delay within two quarters.
2. **Observation:** the 10 worst lanes average 11-14 h of delay against 7.1 h overall. Delhi→Hyderabad has 47% Delayed status.
   **Interpretation:** delay is caused by lane-specific bottlenecks (hand-offs, congestion, scheduling), not by distance (r = −0.03).
   **Business impact:** run root-cause reviews on the top 10 lanes, re-time departures, add buffer to the promised delivery date, and consider alternative carriers or hubs for these lanes.
3. **Observation:** delay spikes in Mar-2024, Dec-2024 and Apr/May-2025, and Monday dispatches are the slowest.
   **Interpretation:** peak-season load and weekend backlog put pressure on capacity.
   **Business impact:** use seasonal staffing and fleet plans and add extra Monday capacity. Expect about a 1 h improvement in delay on those days.

### 4.2 Driver efficiency
4. **Observation:** Junior drivers average 7.7 h of delay against 6.8 h for Senior/Expert drivers, but ratings are almost identical, and two Juniors are in the top-10 by rating.
   **Interpretation:** experience helps punctuality modestly. Behaviour matters more than tenure.
   **Business impact:** **training for junior drivers** on route planning and customer communication, buddy them with Experts on the worst lanes, and **recognise top performers** (for example Kiran Pillai at 4.33★ and 87.9% success, and Amit Kumar at 93.8% success) with performance-based incentives.
5. **Observation:** workload is fairly even (about 40 shipments per driver at every level), and the busiest drivers handle up to 57.
   **Business impact:** keep the balanced allocation, and watch high-load drivers with above-average delay (for example #61 and #56) for fatigue.

### 4.3 Vehicle optimisation
6. **Observation:** trucks run at 45% of capacity and have the highest delay. Bikes reach 54% and have the lowest delay. 4 of 45 vehicles are idle (maintenance/retired).
   **Interpretation:** truck capacity is under-used, and small parcels may be travelling on trucks.
   **Business impact:** **consolidate loads** (target ≥ 60% truck utilisation), move light parcels (< 50 kg) to bikes and vans, right-size the truck fleet, and **schedule maintenance in low-volume months** (Feb, Jun, Sep) so vehicles are available in peak months.
7. **Observation:** electric vehicles show slightly higher average delay (7.7 h vs 6.8 h diesel).
   **Business impact:** check charging downtime and route assignment for EVs before expanding the EV fleet.

### 4.4 Customer satisfaction
8. **Observation:** rating falls as delay grows (on time 4.58, ≤ 6 h 4.23, 6-24 h 3.81, > 24 h 2.84), and cancelled or in-transit orders get about 2★.
   **Interpretation:** punctuality and order completion drive satisfaction. Feedback comments line up exactly with rating bands (for example "Delayed delivery" is always 2★).
   **Business impact:** send proactive delay notifications, compensate customers for delays over 24 h, and cut cancellations. Bringing the 288 failed orders up to the completed-order average would lift the overall rating above 4.0.
9. **Observation:** 90 extreme delays (> 39 h) average 2.8★.
   **Business impact:** make an automatic escalation at 24 h of delay, and review each extreme case with the hub involved, starting with Kochi and Ahmedabad.

### 4.5 Operational recommendations
| Area | Recommendation | Expected effect |
|---|---|---|
| Route optimisation | Lane-level root-cause fixes on the top 10 delayed lanes; realistic Express SLAs | Lower average delay and a higher zero-delay rate |
| Resource allocation | Monday and peak-month capacity; juniors paired with experts; load-based vehicle assignment | Fewer severe delays |
| Hub management | Scorecards for Jaipur and Nagpur; share best practices from Delhi, Patna and Lucknow | Narrower spread in success rates |
| Cost reduction | Truck load consolidation, fleet right-sizing, maintenance in off-peak months | Lower cost per kg and fewer idle assets |
| Customer experience | Delay alerts, > 24 h compensation, reduced cancellations | Average rating at or above 4.0 |

---

## 5. Data quality notes
* The official files had no missing values, duplicates or orphan keys.
* **288 In-Transit/Cancelled deliveries carried a delivery timestamp and 0 delay.** These were set to NULL so the delay KPIs are not understated.
* **1,457 "Delivered" records have delay > 0.** Following the brief, `is_delayed = delay_hours > 0` (which is why the zero-delay share is reported separately).
* **252 shipments are dated before the assigned driver's join date.** They are flagged (`driver_join_conflict`) and kept.

*Charts: `reports/figures/`, test outputs: `reports/statistical_test_results.csv`, outlier list: `reports/delay_outliers_zscore.csv`, dashboard screenshots: `reports/dashboard_screenshots/`.*

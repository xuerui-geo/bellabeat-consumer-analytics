"""Build the Bellabeat Tableau workbook.

1. Rebuilds the clean `daily` table with the same SQL as the analysis (sql/02_clean_and_join.sql)
   and exports small, tidy CSVs to tableau/Data/tableau/.
2. Writes tableau/bellabeat_dashboard.twb and packages tableau/bellabeat_dashboard.twbx
   (workbook + CSVs + Hyper extracts), which opens directly in Tableau Public.

Usage:  python src/build_tableau.py
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tableau_xml as tx  # noqa: E402
from tableau_xml import DS, TITLES, dashboard, dash_keys, escape, make_twb, package, worksheet, write_hyper, ws_window  # noqa: E402

ROOT = tx.ROOT
RAW = ROOT / "data" / "raw"
DATA = tx.DATA
PINK, GREY, DARK, TEAL = "#d9577e", "#b9b9b9", "#5b5b5b", "#3a9e98"

# =====================================================================  1. data
con = duckdb.connect()
con.execute(f"""
CREATE VIEW raw_daily_activity AS
SELECT *, strptime(ActivityDate, '%m/%d/%Y')::DATE AS activity_date
FROM read_csv_auto('{RAW / 'dailyActivity_merged.csv'}', types={{'ActivityDate': 'VARCHAR'}});
CREATE VIEW raw_sleep_day AS
SELECT *, strptime(SleepDay, '%m/%d/%Y %I:%M:%S %p')::DATE AS sleep_date
FROM read_csv_auto('{RAW / 'sleepDay_merged.csv'}', types={{'SleepDay': 'VARCHAR'}});
CREATE VIEW raw_hourly_steps AS
SELECT *, strptime(ActivityHour, '%m/%d/%Y %I:%M:%S %p') AS activity_hour
FROM read_csv_auto('{RAW / 'hourlySteps_merged.csv'}', types={{'ActivityHour': 'VARCHAR'}});
""")
con.execute((ROOT / "sql" / "02_clean_and_join.sql").read_text().split(";")[0])


def export(name, sql):
    con.sql(sql).df().to_csv(DATA / name, index=False)


export("step_band.csv", """
    SELECT CASE WHEN steps < 5000 THEN '1 · <5k' WHEN steps < 7500 THEN '2 · 5k–7.5k'
                WHEN steps < 10000 THEN '3 · 7.5k–10k' ELSE '4 · 10k+' END AS step_band,
           COUNT(*) AS user_days, ROUND(AVG(calories)) AS avg_calories,
           ROUND(AVG(very_active_min), 1) AS avg_very_active_min
    FROM daily GROUP BY 1 ORDER BY 1""")

export("calorie_drivers.csv", """
    WITH w AS (SELECT *,
        calories - AVG(calories) OVER (PARTITION BY Id) AS cal_dev,
        steps - AVG(steps) OVER (PARTITION BY Id) AS steps_dev,
        very_active_min - AVG(very_active_min) OVER (PARTITION BY Id) AS very_dev,
        lightly_active_min - AVG(lightly_active_min) OVER (PARTITION BY Id) AS light_dev,
        sedentary_min - AVG(sedentary_min) OVER (PARTITION BY Id) AS sed_dev
      FROM daily)
    SELECT 'Steps' AS measure, ROUND(CORR(steps, calories), 2) AS r_across_users,
           ROUND(CORR(steps_dev, cal_dev), 2) AS r_within_user FROM w
    UNION ALL SELECT 'Very active minutes', ROUND(CORR(very_active_min, calories), 2), ROUND(CORR(very_dev, cal_dev), 2) FROM w
    UNION ALL SELECT 'Lightly active minutes', ROUND(CORR(lightly_active_min, calories), 2), ROUND(CORR(light_dev, cal_dev), 2) FROM w
    UNION ALL SELECT 'Sedentary minutes', ROUND(CORR(sedentary_min, calories), 2), ROUND(CORR(sed_dev, cal_dev), 2) FROM w""")

export("steps_by_hour.csv", """
    WITH h AS (SELECT hour(activity_hour) AS hr, ROUND(AVG(StepTotal)) AS avg_steps
               FROM raw_hourly_steps GROUP BY 1)
    SELECT lpad(CAST(hr AS VARCHAR), 2, '0') || ':00' AS hour_of_day,
           CASE WHEN avg_steps >= 530 THEN 'Peak (530+ steps)' ELSE 'Other' END AS period,
           avg_steps
    FROM h ORDER BY 1""")

export("steps_by_weekday.csv", """
    SELECT isodow(activity_date) || ' · ' || strftime(activity_date, '%a') AS weekday,
           ROUND(AVG(steps)) AS avg_steps
    FROM daily GROUP BY 1 ORDER BY 1""")

export("sleep_by_sedentary_share.csv", """
    SELECT CASE WHEN sedentary_min / tracked_min < 0.6 THEN '1 · <60%'
                WHEN sedentary_min / tracked_min < 0.7 THEN '2 · 60–70%'
                WHEN sedentary_min / tracked_min < 0.8 THEN '3 · 70–80%'
                ELSE '4 · 80%+' END AS sedentary_share,
           COUNT(*) AS nights,
           ROUND(AVG(CASE WHEN minutes_asleep >= 420 THEN 1.0 ELSE 0 END), 3) AS pct_7h_plus
    FROM daily WHERE has_sleep GROUP BY 1 ORDER BY 1""")

export("sleep_logging.csv", """
    WITH u AS (SELECT Id, COUNT(*) AS days_worn, SUM(CASE WHEN has_sleep THEN 1 ELSE 0 END) AS nights
               FROM daily GROUP BY Id)
    SELECT CASE WHEN nights = 0 THEN '1 · Never'
                WHEN nights * 2 < days_worn THEN '2 · Under half of days worn'
                ELSE '3 · Half or more' END AS sleep_logging,
           COUNT(*) AS users
    FROM u GROUP BY 1 ORDER BY 1""")

export("wear_days.csv", """
    WITH u AS (SELECT Id, COUNT(*) AS days_worn FROM daily GROUP BY Id)
    SELECT CASE WHEN days_worn >= 25 THEN '1 · 25+ days' WHEN days_worn >= 15 THEN '2 · 15–24 days'
                ELSE '3 · Under 15 days' END AS days_worn_group,
           COUNT(*) AS users
    FROM u GROUP BY 1 ORDER BY 1""")

# =====================================================================  2. workbook
ds_band = DS("stepband", "step_band.csv", "Calories by Step Band",
             formats={"avg_calories": "n#,##0", "avg_very_active_min": "n#,##0"})
ds_drv = DS("drivers", "calorie_drivers.csv", "Calorie Drivers",
            formats={"r_within_user": "n0.00", "r_across_users": "n0.00"})
ds_hour = DS("hour", "steps_by_hour.csv", "Steps by Hour", formats={"avg_steps": "n#,##0"},
             colors={"period": {"Peak (530+ steps)": PINK, "Other": GREY}})
ds_wd = DS("weekday", "steps_by_weekday.csv", "Steps by Weekday", formats={"avg_steps": "n#,##0"})
ds_sleep = DS("sleep", "sleep_by_sedentary_share.csv", "Sleep by Sedentary Share", formats={"pct_7h_plus": "p0%"})
ds_log = DS("sleeplog", "sleep_logging.csv", "Sleep Logging",
            colors={"sleep_logging": {"1 · Never": PINK, "2 · Under half of days worn": GREY,
                                      "3 · Half or more": TEAL}})
ds_wear = DS("wear", "wear_days.csv", "Days Worn")
ALL_DS = [ds_band, ds_drv, ds_hour, ds_wd, ds_sleep, ds_log, ds_wear]
for d in ALL_DS:
    write_hyper(d.file, d.types)

WS = {
    "Band": worksheet("Avg calories burned per day, by daily steps", ds_band, ["none:step_band"],
                      ["sum:avg_calories"], "Bar", label="sum:avg_calories"),
    "Intensity": worksheet("Avg very active minutes per day, by daily steps", ds_band, ["none:step_band"],
                           ["sum:avg_very_active_min"], "Bar", label="sum:avg_very_active_min"),
    "Drivers": worksheet("Correlation with calories, within the same user (r)", ds_drv, ["sum:r_within_user"],
                         ["none:measure"], "Bar", label="sum:r_within_user",
                         sort_desc=("none:measure", "sum:r_within_user")),
    "Hour": worksheet("Avg steps by hour of day: peaks at lunch and after work", ds_hour, ["none:hour_of_day"],
                      ["sum:avg_steps"], "Bar", color="none:period"),
    "Weekday": worksheet("Avg steps by weekday: Sunday is lowest", ds_wd, ["none:weekday"], ["sum:avg_steps"],
                         "Bar", label="sum:avg_steps"),
    "Sleep": worksheet("Nights with 7h+ sleep, by sedentary share of awake time", ds_sleep,
                       ["none:sedentary_share"], ["sum:pct_7h_plus"], "Bar", label="sum:pct_7h_plus"),
    "SleepLog": worksheet("Users by how often they logged sleep (of 33)", ds_log, ["sum:users"],
                          ["none:sleep_logging"], "Bar", label="sum:users"),
    "Wear": worksheet("Users by days the tracker was worn (of 31)", ds_wear, ["sum:users"],
                      ["none:days_worn_group"], "Bar", label="sum:users"),
}
TITLES.update({k: v.split("name='", 1)[1].split("'", 1)[0] for k, v in WS.items()})

DASHBOARDS = [
    ("1 Activity and Calories", "Bellabeat: what drives calories burned?",
     "33 Fitbit users, Apr 12 - May 12 2016 (850 clean user-days). Intensity matters more than step count: "
     "10k+ step days burn 44% more calories than <5k days, with ~50 very active minutes vs 3.",
     [[("Band", 34000), ("Intensity", 33000), ("Drivers", 33000)], [("Hour", 60000), ("Weekday", 40000)]]),
    ("2 Sleep and Engagement", "Bellabeat: sleep and device engagement",
     "24 users logged 398 nights; only 55% reached 7h. 9 of 33 users never logged sleep. "
     "Sedentary share of awake time is used because raw sedentary minutes shrink mechanically with time in bed.",
     [[("Sleep", 100000)], [("SleepLog", 50000), ("Wear", 50000)]]),
]
dash_xml = [dashboard(n, t, sb, z) for n, t, sb, z in DASHBOARDS]
windows = []
for n, _, _, z in DASHBOARDS:
    vps = "\n".join(f"        <viewpoint name='{escape(TITLES[k])}'>\n          <zoom type='entire-view' />\n"
                    f"        </viewpoint>" for k in dash_keys(z))
    windows.append(f"    <window class='dashboard' maximized='true' name='{escape(n)}'>\n      <viewpoints>\n{vps}\n"
                   f"      </viewpoints>\n      <active id='-1' />\n    </window>")

twb = make_twb(ALL_DS, list(WS.values()), dash_xml, windows + [ws_window(k) for k in WS])
# readable axis titles: Tableau uses the column caption
CAPTIONS = {"avg_calories": "Avg calories / day", "avg_very_active_min": "Very active minutes / day",
            "r_within_user": "Correlation (r)", "avg_steps": "Avg steps", "pct_7h_plus": "% of nights with 7h+ sleep",
            "users": "Users", "step_band": "Daily steps", "measure": "Activity measure", "hour_of_day": "Hour",
            "weekday": "Weekday", "sedentary_share": "Sedentary share of awake time",
            "sleep_logging": "Nights with sleep logged", "days_worn_group": "Days worn", "period": "Hour type"}
for field, cap in CAPTIONS.items():
    twb = twb.replace(f"name='[{field}]' role=", f"caption='{escape(cap)}' name='[{field}]' role=")
twb_path, twbx_path = package("bellabeat_dashboard", twb, [d.file for d in ALL_DS])
print("wrote", twb_path.relative_to(ROOT), "and", twbx_path.relative_to(ROOT))
for d in ALL_DS:
    print(f"  {d.file:32s} {len(d.df):>3} rows")

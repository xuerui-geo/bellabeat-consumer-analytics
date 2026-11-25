-- 01 · Data quality checks on the raw Fitbit exports
-- Run order: this file reads the raw_* views created by src/run_analysis.py

-- 1a. Coverage: how many users and days does each table have?
SELECT 'daily_activity' AS table_name, COUNT(*) AS n_rows, COUNT(DISTINCT Id) AS n_users,
       MIN(activity_date) AS first_day, MAX(activity_date) AS last_day
FROM raw_daily_activity
UNION ALL
SELECT 'sleep_day', COUNT(*), COUNT(DISTINCT Id), MIN(sleep_date), MAX(sleep_date)
FROM raw_sleep_day
UNION ALL
SELECT 'hourly_steps', COUNT(*), COUNT(DISTINCT Id), MIN(CAST(activity_hour AS DATE)), MAX(CAST(activity_hour AS DATE))
FROM raw_hourly_steps
UNION ALL
SELECT 'weight_log', COUNT(*), COUNT(DISTINCT Id), NULL, NULL
FROM raw_weight_log;

-- 1b. Exact duplicate rows
SELECT 'daily_activity' AS table_name, COUNT(*) - COUNT(DISTINCT (Id, activity_date)) AS duplicate_rows FROM raw_daily_activity
UNION ALL
SELECT 'sleep_day', COUNT(*) - COUNT(DISTINCT (Id, sleep_date)) FROM raw_sleep_day;

-- 1c. Suspicious days: zero steps, or the tracker logged a full 1,440 sedentary minutes
--     (usually means the device was not worn, not that the user sat all day)
SELECT
    SUM(CASE WHEN TotalSteps = 0 THEN 1 ELSE 0 END)                      AS zero_step_days,
    SUM(CASE WHEN SedentaryMinutes >= 1440 THEN 1 ELSE 0 END)            AS full_day_sedentary,
    SUM(CASE WHEN VeryActiveMinutes + FairlyActiveMinutes + LightlyActiveMinutes
                  + SedentaryMinutes < 600 THEN 1 ELSE 0 END)            AS under_10h_logged
FROM raw_daily_activity;

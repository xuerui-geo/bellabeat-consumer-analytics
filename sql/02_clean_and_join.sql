-- 02 · Clean and join activity + sleep into one analysis table
-- Rules:
--   * drop exact duplicate sleep rows
--   * drop "not worn" days: 0 steps, or fewer than 10 hours of tracked minutes
--   * sleep is attached when the user logged sleep for that day (left join)

CREATE OR REPLACE TABLE daily AS
WITH sleep_clean AS (
    SELECT DISTINCT Id, sleep_date, TotalSleepRecords, TotalMinutesAsleep, TotalTimeInBed
    FROM raw_sleep_day
),
activity_clean AS (
    SELECT
        Id,
        activity_date,
        TotalSteps            AS steps,
        TotalDistance         AS distance_km,
        VeryActiveMinutes     AS very_active_min,
        FairlyActiveMinutes   AS fairly_active_min,
        LightlyActiveMinutes  AS lightly_active_min,
        SedentaryMinutes      AS sedentary_min,
        VeryActiveMinutes + FairlyActiveMinutes                    AS mvpa_min,      -- moderate-to-vigorous
        VeryActiveMinutes + FairlyActiveMinutes + LightlyActiveMinutes
            + SedentaryMinutes                                     AS tracked_min,
        Calories              AS calories,
        dayname(activity_date) AS weekday,
        isodow(activity_date)  AS weekday_num
    FROM raw_daily_activity
    WHERE TotalSteps > 0
      AND VeryActiveMinutes + FairlyActiveMinutes + LightlyActiveMinutes + SedentaryMinutes >= 600
)
SELECT
    a.*,
    s.TotalMinutesAsleep                       AS minutes_asleep,
    s.TotalTimeInBed                           AS minutes_in_bed,
    s.TotalTimeInBed - s.TotalMinutesAsleep    AS minutes_awake_in_bed,
    s.TotalMinutesAsleep IS NOT NULL           AS has_sleep
FROM activity_clean a
LEFT JOIN sleep_clean s
  ON a.Id = s.Id AND a.activity_date = s.sleep_date;

-- Validation: the join must not create extra rows
SELECT COUNT(*) AS rows_after_join,
       COUNT(DISTINCT (Id, activity_date)) AS unique_user_days,
       COUNT(DISTINCT Id) AS users,
       SUM(CASE WHEN has_sleep THEN 1 ELSE 0 END) AS days_with_sleep,
       COUNT(DISTINCT CASE WHEN has_sleep THEN Id END) AS users_with_sleep
FROM daily;

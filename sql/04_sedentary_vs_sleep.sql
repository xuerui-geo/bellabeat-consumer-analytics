-- 04 · How do sedentary time and activity relate to sleep?
-- Only days where the user logged sleep.
--
-- Caveat found during analysis: on nights with sleep logged, the tracker's daily minutes
-- (sedentary + active) cover only the AWAKE part of the day: tracked_min + minutes_in_bed ≈ 1,440.
-- So "more sedentary minutes" partly just means "fewer minutes in bed", a mechanical link.
-- The fair measure is sedentary SHARE of awake (tracked) time.

-- 4a. Evidence for the caveat
SELECT
    COUNT(*)                                                                            AS user_days_with_sleep,
    COUNT(DISTINCT Id)                                                                  AS users_with_sleep,
    ROUND(100.0 * AVG(CASE WHEN tracked_min + minutes_in_bed BETWEEN 1380 AND 1500 THEN 1 ELSE 0 END), 1)
                                                                                        AS pct_days_tracked_plus_bed_eq_24h
FROM daily
WHERE has_sleep;

-- 4b. Naive vs fair correlation with minutes asleep
WITH s AS (
    SELECT *,
        sedentary_min / tracked_min                                                 AS sedentary_share,
        sedentary_min / tracked_min - AVG(sedentary_min / tracked_min) OVER (PARTITION BY Id) AS share_dev,
        minutes_asleep - AVG(minutes_asleep) OVER (PARTITION BY Id)                 AS sleep_dev
    FROM daily
    WHERE has_sleep
)
SELECT
    ROUND(CORR(sedentary_min, minutes_asleep), 2)     AS naive_r_sedentary_minutes,
    ROUND(CORR(sedentary_share, minutes_asleep), 2)   AS r_sedentary_share,
    ROUND(CORR(share_dev, sleep_dev), 2)              AS within_user_r_sedentary_share,
    ROUND(CORR(mvpa_min, minutes_asleep), 2)          AS r_mvpa
FROM s;

-- 4c. Sleep by sedentary share of awake time
SELECT
    CASE WHEN sedentary_min / tracked_min < 0.6 THEN '1 · <60%'
         WHEN sedentary_min / tracked_min < 0.7 THEN '2 · 60–70%'
         WHEN sedentary_min / tracked_min < 0.8 THEN '3 · 70–80%'
         ELSE                                        '4 · 80%+' END     AS sedentary_share_band,
    COUNT(*)                                                           AS user_days,
    COUNT(DISTINCT Id)                                                 AS users,
    ROUND(AVG(minutes_asleep) / 60, 2)                                 AS avg_hours_asleep,
    ROUND(100.0 * AVG(CASE WHEN minutes_asleep >= 420 THEN 1 ELSE 0 END), 1) AS pct_7h_plus
FROM daily
WHERE has_sleep
GROUP BY 1
ORDER BY 1;

-- 4d. Share of logged nights that reach the recommended 7 hours
SELECT
    ROUND(AVG(minutes_asleep) / 60, 2)                                        AS avg_hours_asleep,
    ROUND(100.0 * AVG(CASE WHEN minutes_asleep >= 420 THEN 1 ELSE 0 END), 1)  AS pct_nights_7h_plus,
    ROUND(AVG(minutes_awake_in_bed))                                          AS avg_min_awake_in_bed
FROM daily
WHERE has_sleep;

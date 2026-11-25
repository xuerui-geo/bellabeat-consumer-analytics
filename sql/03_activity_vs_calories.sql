-- 03 · How do activity intensity and sedentary time relate to calories burned?

-- 3a. Correlation of each activity measure with daily calories
--     (pooled over all user-days, and within-user, which removes body-size differences between people)
WITH within_user AS (
    SELECT *,
        calories        - AVG(calories)        OVER (PARTITION BY Id) AS cal_dev,
        steps           - AVG(steps)           OVER (PARTITION BY Id) AS steps_dev,
        very_active_min - AVG(very_active_min) OVER (PARTITION BY Id) AS very_dev,
        lightly_active_min - AVG(lightly_active_min) OVER (PARTITION BY Id) AS light_dev,
        sedentary_min   - AVG(sedentary_min)   OVER (PARTITION BY Id) AS sed_dev
    FROM daily
)
SELECT 'steps' AS measure,              ROUND(CORR(steps, calories), 2) AS pooled_r,              ROUND(CORR(steps_dev, cal_dev), 2) AS within_user_r FROM within_user
UNION ALL SELECT 'very_active_min',     ROUND(CORR(very_active_min, calories), 2),                ROUND(CORR(very_dev, cal_dev), 2) FROM within_user
UNION ALL SELECT 'lightly_active_min',  ROUND(CORR(lightly_active_min, calories), 2),             ROUND(CORR(light_dev, cal_dev), 2) FROM within_user
UNION ALL SELECT 'sedentary_min',       ROUND(CORR(sedentary_min, calories), 2),                  ROUND(CORR(sed_dev, cal_dev), 2) FROM within_user;

-- 3b. Calories by daily step band (the 7,500 and 10,000-step thresholds are common public-health cut-offs)
SELECT
    CASE WHEN steps < 5000  THEN '1 · <5k'
         WHEN steps < 7500  THEN '2 · 5k–7.5k'
         WHEN steps < 10000 THEN '3 · 7.5k–10k'
         ELSE                    '4 · 10k+' END       AS step_band,
    COUNT(*)                                          AS user_days,
    ROUND(AVG(calories))                              AS avg_calories,
    ROUND(AVG(very_active_min), 1)                    AS avg_very_active_min,
    ROUND(AVG(sedentary_min) / 60, 1)                 AS avg_sedentary_hours
FROM daily
GROUP BY 1
ORDER BY 1;

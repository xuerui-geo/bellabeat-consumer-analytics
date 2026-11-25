-- 05 · Usage patterns that point to product opportunities

-- 5a. Engagement: how many of the 31 days did each user wear the tracker, and log sleep?
CREATE OR REPLACE TABLE user_engagement AS
SELECT
    Id,
    COUNT(*)                                          AS days_worn,
    SUM(CASE WHEN has_sleep THEN 1 ELSE 0 END)        AS nights_sleep_logged,
    ROUND(AVG(steps))                                 AS avg_steps,
    CASE WHEN COUNT(*) >= 25 THEN 'High (25+ days)'
         WHEN COUNT(*) >= 15 THEN 'Medium (15–24)'
         ELSE                     'Low (<15)' END     AS wear_group
FROM daily
GROUP BY Id;

SELECT wear_group, COUNT(*) AS users, ROUND(AVG(avg_steps)) AS avg_steps,
       ROUND(AVG(nights_sleep_logged), 1) AS avg_nights_sleep_logged
FROM user_engagement
GROUP BY 1 ORDER BY 1;

SELECT
    COUNT(*)                                                     AS users,
    SUM(CASE WHEN nights_sleep_logged = 0 THEN 1 ELSE 0 END)     AS never_logged_sleep,
    SUM(CASE WHEN nights_sleep_logged >= 15 THEN 1 ELSE 0 END)   AS logged_sleep_15plus
FROM user_engagement;

-- 5b. Steps by hour of day (when are users active?)
SELECT
    hour(activity_hour)          AS hour_of_day,
    ROUND(AVG(StepTotal))        AS avg_steps
FROM raw_hourly_steps
GROUP BY 1
ORDER BY 1;

-- 5c. Activity by weekday
SELECT weekday, weekday_num,
       ROUND(AVG(steps))                  AS avg_steps,
       ROUND(AVG(sedentary_min) / 60, 1)  AS avg_sedentary_hours
FROM daily
GROUP BY 1, 2
ORDER BY 2;
